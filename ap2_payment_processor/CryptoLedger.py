"""
Module CryptoLedger.py

AP2 spec: https://ap2-protocol.org/specification/
Google announcement: https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol

# MIT License
#
# Copyright (c) 2025 Adam Bilbrough
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""

import json
from datetime import datetime
from typing import Dict, Any

import base58

from KeyManager import KeyManager
from MandateSigner import MandateSigner


class CryptoLedger:
    """
    - Verifies the signatures of all mandates.
    - Enforces chain integrity: cart.prev == intent.id; payment.prev == cart.id (VC-wrapped paths).
    - Enforces VC metadata: expirationDate (reject expired) and revocation.
    - Stores mandate records only if all checks pass.
    """
    def __init__(self, trusted_issuers: Dict[str, str], key_manager: KeyManager):
        self.trusted_issuers = trusted_issuers
        self.key_manager = key_manager
        self.transactions = []
        self.revoked_ids = set()

    @staticmethod
    def ledger_parse_rfc3339(ts: str) -> datetime:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")

    def ledger_not_expired(self, vc: Dict[str, Any]) -> bool:
        exp = vc.get("expirationDate")
        if not exp:
            return True
        try:
            return datetime.utcnow() < self.ledger_parse_rfc3339(exp)
        except Exception:
            print(f"[expiry] malformed expirationDate: {exp}")
            return False

    def ledger_not_revoked(self, vc: Dict[str, Any]) -> bool:
        vc_id = vc.get("id")
        if not vc_id:
            print("[revocation] missing VC id")
            return False
        return vc_id not in self.revoked_ids

    def ledger_issuer_trusted(self, mandate: Dict[str, Any]) -> bool:
        proof = mandate.get("proof", {})
        issuer = mandate.get("issuer")
        vm = proof.get("verificationMethod")

        if not issuer or not vm:
            print("[issuer] missing issuer or verificationMethod")
            return False

        expected_pub_b58 = self.trusted_issuers.get(issuer)
        if not expected_pub_b58:
            print(f"[issuer] untrusted issuer: {issuer}")
            return False

        try:
            resolved_pub = self.key_manager.key_resolve_verification_method(vm)
            resolved_pub_b58 = base58.b58encode(resolved_pub).decode("ascii")
            if resolved_pub_b58 != expected_pub_b58:
                print("[issuer] verificationMethod key mismatch for issuer")
                print(f"  expected: {expected_pub_b58}")
                print(f"  resolved: {resolved_pub_b58}")
                return False
        except Exception as e:
            print(f"[issuer] failed to resolve verificationMethod: {e}")
            return False

        return True

    def ledger_verify_mandate(self, mandate: Dict[str, Any]) -> bool:
        """
        VC'ing of Mandates (A VC'd Mandate is a verified and signed Mandate)
        :param mandate:
        :return:
        """
        if not self.ledger_issuer_trusted(mandate):
            return False
        if not self.ledger_not_expired(mandate):
            print("[expiry] mandate expired")
            return False
        if not self.ledger_not_revoked(mandate):
            print("[revocation] mandate revoked")
            return False
        ok = MandateSigner.verify(mandate, self.key_manager)
        if not ok:
            print("[signature] verification failed")
        return ok

    def ledger_vc_previous(self, vc: Dict[str, Any]) -> str:
        return vc.get("credentialSubject", {}).get("prev_mandate_id")

    def ledger_vc_id(self, vc: Dict[str, Any]) -> str:
        return vc.get("id")

    def ledger_verify_chain(self, mandates: list[Dict[str, Any]]) -> bool:
        for prev, curr in zip(mandates, mandates[1:]):
            if self.ledger_vc_previous(curr) != self.ledger_vc_id(prev):
                print(f"[chain] mismatch: {curr['type'][-1]}.prev={self.ledger_vc_previous(curr)} "
                      f"vs {prev['type'][-1]}.id={self.ledger_vc_id(prev)}")
                return False
        return True

    def add_transaction(self, txn_record: Dict[str, Any]) -> bool:
        """
        Transaction processing of Mandates

        A complete batch of Mandates (3/4 if Netting is used), constitutes 1 Transaction
        """
        mandates = txn_record.get("mandates", [])
        if not mandates:
            print("Invalid flow: no mandates.")
            return False

        for vc in mandates:
            if not self.ledger_verify_mandate(vc):
                print("Signature/metadata verification failed.")
                return False

        if not self.ledger_verify_chain(mandates):
            print("Chain verification failed.")
            return False

        if len(mandates) >= 3 and mandates[0]["type"][-1] == "IntentMandate":
            intent_vc, cart_vc, payment_vc = mandates[:3]
            try:
                intent_subject = intent_vc["credentialSubject"]
                amount_intent = float(intent_subject["details"]["amount"])
                currency_intent = intent_subject["details"]["currency"]
                receiver_intent = intent_subject["merchant_id"]

                cart_subject = cart_vc["credentialSubject"]
                cart_details = cart_subject["contents"]["payment_request"]["details"]
                total_cart = float(cart_details["total"]["amount"]["value"])
                currency_cart = cart_details["total"]["amount"]["currency"]
                receiver_cart = cart_subject["merchant_id"]

                payment_subject = payment_vc["credentialSubject"]
                payment_details = payment_subject["payment_details"]
                amount_payment = float(payment_details["amount"])
                currency_payment = payment_details["currency"]
                receiver_payment = payment_subject["merchant_id"]

                if not (
                        amount_intent == total_cart == amount_payment
                        and currency_intent == currency_cart == currency_payment
                        and receiver_intent == receiver_cart == receiver_payment
                ):
                    print("Amount/currency/receiver mismatch across mandates.")
                    return False

            except Exception as e:
                print(f"Mandate structure mismatch: {e}")
                return False

        self.transactions.append(txn_record)
        return True

    def transaction_report(self):
        """Handles the Ledger report."""
        green = "\033[92m"
        red = "\033[91m"
        reset = "\033[0m"

        print("\nLedger Report:")
        total = len(self.transactions)
        consistent_count = 0
        inconsistent_count = 0

        for txn in self.transactions:
            print("=" * 70)
            print(
                f"TXN {txn['transaction_id']} | "
                f"{txn['sender']} -> {txn['receiver']} "
                f"{txn['amount']} {txn['currency']}"
            )

            print("Mandate Chain:")
            for idx, m in enumerate(txn['mandates'], start=1):
                mandate_type = m["type"][-1]
                subj = m["credentialSubject"]
                mandate_id = subj.get("mandate_id") or subj.get("refund_id") or subj.get("flag_id")
                merchant_id = subj.get("merchant_id", "n/a")
                vc_id = m.get("id", "n/a")
                exp = m.get("expirationDate", "n/a")
                issuer = m.get("issuer", "n/a")

                arrow = "└─" if idx == len(txn['mandates']) else "├─"
                print(
                    f" {arrow} {mandate_type} "
                    f"(mandate_id={mandate_id}, vc_id={vc_id})"
                )
                print(
                    f"    merchant={merchant_id} issuer={issuer} exp={exp}"
                )

            consistent = self.ledger_check_consistency(txn)
            if consistent:
                verdict = f"{green}✔ Consistent{reset}"
                consistent_count += 1
            else:
                verdict = f"{red}✘ Inconsistent{reset}"
                inconsistent_count += 1
            print(f"Consistency: {verdict}")

        print("\nSummary:")
        print(f" Total transactions: {total}")
        print(f" {green}{consistent_count} consistent{reset}")
        print(f" {red}{inconsistent_count} inconsistent{reset}")

    def ledger_check_consistency(self, txn: Dict[str, Any]) -> bool:
        """Rerun the cross-checking logic for reporting."""
        mandates = txn.get("mandates", [])
        if len(mandates) >= 3 and mandates[0]["type"][-1] == "IntentMandate":
            try:
                intent_vc, cart_vc, payment_vc = mandates[:3]
                intent_subject = intent_vc["credentialSubject"]
                cart_subject = cart_vc["credentialSubject"]
                payment_subject = payment_vc["credentialSubject"]

                amount_intent = float(intent_subject["details"]["amount"])
                currency_intent = intent_subject["details"]["currency"]
                receiver_intent = intent_subject["merchant_id"]

                cart_details = cart_subject["contents"]["payment_request"]["details"]
                total_cart = float(cart_details["total"]["amount"]["value"])
                currency_cart = cart_details["total"]["amount"]["currency"]
                receiver_cart = cart_subject["merchant_id"]

                payment_details = payment_subject["payment_details"]
                amount_payment = float(payment_details["amount"])
                currency_payment = payment_details["currency"]
                receiver_payment = payment_subject["merchant_id"]

                return (
                        amount_intent == total_cart == amount_payment
                        and currency_intent == currency_cart == currency_payment
                        and receiver_intent == receiver_cart == receiver_payment
                )
            except Exception:
                return False
        return True

    def save_to_file(self, path: str, txn_record: Dict[str, Any]) -> None:
        """Append a snapshot of the transaction to a plain text simulated ledger."""
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write("----- TRANSACTION COMPLETED -----\n")
                f.write(json.dumps(txn_record, indent=2))
                f.write("\n\n")
        except Exception as e:
            print(f"[persistence] failed to write ledger entry: {e}")
