"""
Module Main.py

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
import os
import re
import uuid

import MandateFactory
from CryptoLedger import CryptoLedger
from KeyManager import KeyManager
from MandateSigner import MandateSigner
from PaymentProcessor import PaymentProcessor


# global function
def load_ledger_from_file(path: str, ledger: CryptoLedger):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    entries = content.split("----- TRANSACTION COMPLETED -----")
    for entry in entries:
        entry = entry.strip()
        if not entry or not entry.startswith("{"):
            continue
        try:
            txn = json.loads(entry)
            ledger.transactions.append(txn)
        except Exception as e:
            print(f"[load] failed to parse entry: {e}")


class AgentPrompt:
    """
    AgentPrompt class.

    Implementation notes:
    - Purpose: AgentPrompt implements part of the payment processing flow.
    - AP2 alignment: uses 'mandates' and verifiable credentials (VCs) to represent intent/cart/payment as AP2 mandates/VCs.
    - AP2 spec: https://ap2-protocol.org/specification/
    """
    def __init__(self, processor, mandate_factory, ledger, ledger_file="ledger.log"):
        self.processor = processor
        self.mandate_factory = mandate_factory
        self.ledger = ledger
        self.ledger_file = ledger_file

    def run_payment_process(self):
        while True:
            cmd = input("AP2> ").strip()
            if not cmd:
                continue
            if cmd.lower() in ("quit", "exit", "q"):
                break

            action, params = self.agent_parse_command(cmd)

            try:
                if action == "payment":
                    amount = params.get("amount")
                    if amount is None:
                        amount = float(input("Amount: ").strip())

                    currency = params.get("currency")
                    if currency is None:
                        currency = input("Currency (default EUR): ").strip().upper() or "EUR"

                    receiver = params.get("receiver")
                    if receiver is None:
                        receiver = input("Receiver (merchant id): ").strip()

                    note = params.get("note")
                    if not note:
                        note = input("Item description (note): ").strip() or "Generic Item"
                    sender = params.get("sender") or "issuer:user-wallet"

                    settlement_run = params.get("settlement_run")
                    if settlement_run is None and "settlement run" in cmd.lower():
                        settlement_run = input("Settlement run: ").strip().upper()

                    intent_vc = self.mandate_factory.sending(
                        self.processor.sending_signer,
                        receiver=receiver,
                        amount=amount,
                        currency=currency,
                        note=cmd.strip()
                    )
                    cart_vc = self.mandate_factory.checkout(
                        self.processor.checkout_signer,
                        receiver=receiver,
                        amount=amount,
                        currency=currency,
                        prev_mandate_id=intent_vc["id"],
                        item_desc=note
                    )
                    txn_id = f"txn-{uuid.uuid4()}"

                    if settlement_run in ("MISC", "ADD1", None):
                        payment_vc = self.mandate_factory.confirmation(
                            self.processor.confirmation_signer,
                            receiver=receiver,
                            amount=amount,
                            currency=currency,
                            txn_id=txn_id,
                            prev_mandate_id=cart_vc["id"],
                            cart_vc=cart_vc
                        )
                        mandates = [intent_vc, cart_vc, payment_vc]
                    else:
                        netting_vc = self.mandate_factory.netting(
                            self.processor.netting_signer,
                            prev_ids=[cart_vc["id"]],
                            counterparty=receiver,
                            currency=currency,
                            amount=amount,
                            settlement_run=settlement_run
                        )

                        print("[Agent] Netting Finished.")

                        payment_vc = self.mandate_factory.confirmation(
                            self.processor.confirmation_signer,
                            receiver=receiver,
                            amount=amount,
                            currency=currency,
                            txn_id=txn_id,
                            prev_mandate_id=netting_vc["id"],
                            cart_vc=cart_vc
                        )
                        mandates = [intent_vc, cart_vc, netting_vc, payment_vc]

                    txn = {
                        "transaction_id": txn_id,
                        "sender": sender,
                        "receiver": receiver,
                        "amount": amount,
                        "currency": currency,
                        "mandates": mandates
                    }
                    self.transaction_commit(txn)

                elif action == "intent":
                    # Prompt for missing fields if any are missing after the prompt
                    amount = params.get("amount")
                    if amount is None:
                        amount = float(input("Amount: ").strip())
                    currency = params.get("currency")
                    if currency is None:
                        currency = input("Currency (default EUR): ").strip().upper() or "EUR"
                    receiver = params.get("receiver")
                    if receiver is None:
                        receiver = input("Receiver (merchant id): ").strip()
                    note = params.get("note")
                    if not note:
                        note = input("Item description (note): ").strip() or "Generic Item"
                    sender = params.get("sender") or "issuer:user-wallet"
                    raw_intent = {
                        "natural_language_description": note,
                        "intent_expiry": self.mandate_factory.mandate_expiry(1),
                        "user_cart_confirmation_required": True,
                        "merchants": [receiver],
                        "skus": [],
                        "required_refundability": True
                    }
                    intent_vc = self.mandate_factory.sending(
                        self.processor.sending_signer,
                        receiver=receiver,
                        amount=amount,
                        currency=currency,
                        note=cmd.strip(),
                        raw_intent=raw_intent
                    )
                    txn = {
                        "transaction_id": f"txn-{os.urandom(4).hex()}",
                        "sender": sender,
                        "receiver": receiver,
                        "amount": amount,
                        "currency": currency,
                        "mandates": [intent_vc]
                    }
                    self.transaction_commit(txn)

                elif action == "intent_raw":
                    path = params.get("path")
                    if not path:
                        print("[Agent] No JSON file path detected in your command.")
                        return
                    with open(path, "r", encoding="utf-8") as f:
                        raw_msg = json.load(f)
                    try:
                        intent_payload = raw_msg["parts"][0]["data"]["ap2.mandates.IntentMandate"]
                    except Exception as e:
                        print(f"[Agent] Invalid intent message format: {e}")
                        return
                    note = intent_payload.get("natural_language_description", "")
                    if not note:
                        note = input("Item description (note): ").strip() or "Generic Item"
                    expiry = intent_payload.get("intent_expiry")
                    amount = float(input("Amount for this intent: ").strip())
                    currency = input("Currency (default EUR): ").strip().upper() or "EUR"
                    receiver = input("Receiver (merchant id): ").strip()
                    sender = params.get("sender") or "issuer:user-wallet"
                    settlement_run = None

                    # The below wraps Intents into VC Mandates
                    if "settlement run" in cmd.lower():
                        settlement_run = input("Settlement run: ").strip().upper()
                    intent_vc = self.mandate_factory.sending(
                        self.processor.sending_signer,
                        receiver=receiver,
                        amount=amount,
                        currency=currency,
                        note=cmd.strip(),
                        raw_intent=intent_payload
                    )

                    if expiry:
                        intent_vc["expirationDate"] = expiry
                    cart_vc = self.mandate_factory.checkout(
                        self.processor.checkout_signer,
                        receiver=receiver,
                        amount=amount,
                        currency=currency,
                        prev_mandate_id=intent_vc["id"],
                        item_desc=note
                    )

                    txn_id = f"txn-{uuid.uuid4()}"
                    if settlement_run in ("MISC", "ADD1", None):
                        payment_vc = self.mandate_factory.confirmation(
                            self.processor.confirmation_signer,
                            receiver=receiver,
                            amount=amount,
                            currency=currency,
                            txn_id=txn_id,
                            prev_mandate_id=cart_vc["id"],
                            cart_vc=cart_vc
                        )
                        mandates = [intent_vc, cart_vc, payment_vc]
                    else:
                        netting_vc = self.mandate_factory.netting(
                            self.processor.netting_signer,
                            prev_ids=[cart_vc["id"]],
                            counterparty=receiver,
                            currency=currency,
                            amount=amount,
                            settlement_run=settlement_run
                        )

                        print("[Agent] Netting Finished.")

                        payment_vc = self.mandate_factory.confirmation(
                            self.processor.confirmation_signer,
                            receiver=receiver,
                            amount=amount,
                            currency=currency,
                            txn_id=txn_id,
                            prev_mandate_id=netting_vc["id"],
                            cart_vc=cart_vc
                        )
                        mandates = [intent_vc, cart_vc, netting_vc, payment_vc]
                    txn = {
                        "transaction_id": txn_id,
                        "sender": sender,
                        "receiver": receiver,
                        "amount": amount,
                        "currency": currency,
                        "mandates": mandates
                    }
                    self.transaction_commit(txn)

                elif action == "refund":
                    amount = params.get("amount")
                    currency = params.get("currency")
                    payment_id = params.get("payment_id")
                    reason = params.get("reason")
                    if not reason:
                        reason = input("[Agent] Please provide a reason for this refund: ").strip()
                        if not reason:
                            reason = "unspecified"

                    txn = self.processor.process_refund(
                        vc_id=payment_id,
                        amount=amount,
                        currency=currency,
                        reason=reason
                    )
                    self.transaction_commit(txn)

                elif action == "fraud":
                    flagged_id = params.get("flagged_id")
                    evidence_path = params.get("evidence")
                    reason = params.get("reason")
                    if not reason:
                        reason = input("[Agent] Please provide a reason for this fraud initiation: ").strip()
                        if not reason:
                            reason = "unspecified"

                    evidence = {}
                    if evidence_path and os.path.exists(evidence_path):
                        try:
                            with open(evidence_path, "r", encoding="utf-8") as f:
                                evidence = json.load(f)
                        except Exception as e:
                            print(f"[Agent] Failed to load evidence file: {e}")

                    txn = self.processor.process_fraud_flag(
                        flagged_vc_id=flagged_id,
                        reason=reason,
                        evidence=evidence
                    )
                    self.transaction_commit(txn)

                else:
                    print("[Agent] Sorry, I didn’t understand that command.")

            except Exception as e:
                print(f"[runtime] error: {e}")


    def agent_parse_command(self, cmd: str):
        text = cmd.strip()

        # Payment
        if any(word in text.lower() for word in ("payment", "send", "pay")):
            amt, cur = self.agent_extract_amount_currency(text)

            # Extract settlement run
            m_run = re.search(r"settlement\s+run\s+(\w+)", text, re.IGNORECASE)
            settlement_run = m_run.group(1).upper() if m_run else None

            # Extract senders and receivers
            sender = self.agent_extract_sender(text)
            receiver = self.agent_extract_receiver(text)

            # Extract note (for xxx)
            m_note = re.search(r"\bfor\s+([A-Za-z0-9\s\-_,.]+)", text, re.IGNORECASE)
            note = m_note.group(1).strip() if m_note else "Generic Item"

            return "payment", {
                "amount": amt,
                "currency": cur,
                "sender": sender,
                "receiver": receiver,
                "note": note,
                "settlement_run": settlement_run
            }

        # Refund
        if "refund" in text.lower():
            amt, cur = self.agent_extract_amount_currency(text)
            vc_id = self.agent_extract_vc_id(text)
            if not vc_id:
                print("[Agent] Refund requires a valid VC ID (urn:uuid:...).")
                return None, {}
            return "refund", {
                "amount": amt,
                "currency": cur,
                "payment_id": vc_id
            }

        # Fraud
        if "fraud" in text.lower() or "flag" in text.lower():
            vc_id = self.agent_extract_vc_id(text)
            evidence = self.agent_extract_path(text)
            if vc_id:
                return "fraud", {
                    "flagged_id": vc_id,
                    "evidence": evidence
                }

        # Intent
        if any(word in text.lower() for word in ("intent", "buy", "purchase")):
            if any(word in text.lower() for word in ("file", "use", "insert")):
                path = self.agent_extract_path(cmd)
                return "intent_raw", {"path": path}
            amt, cur = self.agent_extract_amount_currency(text)
            receiver = self.agent_extract_receiver(text)
            note = self.agent_extract_note(text)
            return "intent", {"amount": amt, "currency": cur, "receiver": receiver, "note": note}
        return None, {}

    def agent_extract_amount_currency(self, text: str):
        m = re.search(r"(\d+(?:\.\d+)?)\s*(eur|usd|czk|gbp|krw|nzd|aud|chf|cny)", text, re.IGNORECASE)
        if m:
            return float(m.group(1)), m.group(2).upper()
        return None, "EUR"

    def agent_extract_sender(self, text: str):
        m = re.search(r"\bfrom\s+([A-Za-z0-9:_-]+)", text, re.IGNORECASE)
        return m.group(1) if m else "issuer:user-wallet"

    def agent_extract_receiver(self, text: str):
        m = re.search(r"\bto\s+([A-Za-z0-9:_-]+)", text, re.IGNORECASE)
        return m.group(1) if m else "merchant"

    def agent_extract_vc_id(self, text: str):
        m = re.search(r"\burn:uuid:[a-f0-9\-]{36}\b", text, re.IGNORECASE)
        return m.group(0) if m else None

    def agent_extract_path(self, text: str):
        m = re.search(r"(\S+\.json)", text, re.IGNORECASE)
        return m.group(1) if m else None

    def agent_extract_note(self, text: str):
        m = re.search(r"\bfor\s+([A-Za-z0-9\s\-_,.]+)", text, re.IGNORECASE)
        return m.group(1).strip() if m else "Generic Item"

    def transaction_commit(self, txn):
        ok = self.ledger.add_transaction(txn)
        if ok:
            self.ledger.save_to_file(self.ledger_file, txn)
            self.transaction_show_result(txn)
        else:
            print("[Agent] Transaction rejected by ledger.")

    def transaction_show_result(self, txn):
        print("\n[Agent] Transaction Result:")
        print(json.dumps(txn, indent=2))
        self.ledger.transaction_report()


def main():
    """Initiates the AP2 Payment Processor."""
    km = KeyManager()
    km.key_generate_issuer("issuer:user-wallet")
    km.key_generate_issuer("issuer:merchant")
    km.key_generate_issuer("issuer:processor")
    km.key_generate_issuer("issuer:netting")

    trusted = km.key_export_public_keys()

    sending_signer = MandateSigner(km, "issuer:user-wallet")
    checkout_signer = MandateSigner(km, "issuer:merchant")
    confirmation_signer = MandateSigner(km, "issuer:processor")
    netting_signer = MandateSigner(km, "issuer:netting")

    ledger = CryptoLedger(trusted, km)
    load_ledger_from_file("ledger.log", ledger)

    processor = PaymentProcessor(
        ledger,
        sending_signer,
        checkout_signer,
        confirmation_signer,
        netting_signer
    )

    mandate_factory = MandateFactory.MandateFactory("issuer:user-wallet")

    agent = AgentPrompt(processor, mandate_factory, ledger)
    agent.run_payment_process()


if __name__ == "__main__":
    main()
