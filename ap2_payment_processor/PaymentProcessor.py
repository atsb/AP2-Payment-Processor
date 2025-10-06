"""
Module PaymentProcessor.py

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

import uuid
from typing import Dict, Any

from CryptoLedger import CryptoLedger
from MandateFactory import MandateFactory
from MandateSigner import MandateSigner


class PaymentProcessor:
    """
    Generates AP2 mandates with cryptographic proofs and sends to ledger.
    """
    def __init__(
            self,
            ledger: CryptoLedger,
            sending_signer: MandateSigner,
            checkout_signer: MandateSigner,
            confirmation_signer: MandateSigner,
            netting_signer: MandateSigner,
            ledger_path: str = "ledger.log"
    ):
        self.ledger = ledger
        self.sending_signer = sending_signer
        self.checkout_signer = checkout_signer
        self.confirmation_signer = confirmation_signer
        self.netting_signer = netting_signer
        self.ledger_path = ledger_path

    def process_payment(
            self,
            sender: str,
            receiver: str,
            amount: float,
            currency: str = "EUR",
            note: str = ""
    ) -> Dict[str, Any]:
        """Payment Processing and creation of VC Mandates from Raw Intents"""
        txn_id = "txn-" + str(uuid.uuid4())

        factory = MandateFactory(user_id=sender)

        # IntentMandate VC
        intent_vc = factory.sending(
            self.sending_signer,
            receiver,
            amount,
            currency,
            note
        )

        # CartMandate VC
        cart_vc = factory.checkout(
            self.checkout_signer,
            receiver,
            amount,
            currency,
            intent_vc["id"],
            item_desc=note or "Generic Item"
        )

        # PaymentMandate VC
        payment_vc = factory.confirmation(
            self.confirmation_signer,
            receiver,
            amount,
            currency,
            txn_id,
            cart_vc["id"],
            cart_vc
        )

        # Transaction Records
        txn_record = {
            "transaction_id": txn_id,
            "sender": sender,
            "receiver": receiver,
            "amount": amount,
            "currency": currency,
            "mandates": [intent_vc, cart_vc, payment_vc],
        }

        ok = self.ledger.add_transaction(txn_record)
        if ok:
            self.ledger.save_to_file(self.ledger_path, txn_record)
        else:
            txn_record["error"] = (
                "Ledger rejected transaction (signature, metadata, or chain validation failed)."
            )
        return txn_record

    def process_refund(
            self,
            vc_id: str,
            amount: float,
            currency: str,
            reason: str
    ) -> Dict[str, Any]:
        if not vc_id.startswith("urn:uuid:"):
            raise ValueError("Please provide the full VC id (e.g., urn:uuid:...)")

        original_vc = None
        for txn in self.ledger.transactions:
            for m in txn.get("mandates", []):
                if "PaymentMandate" in m.get("type", []) and m.get("id") == vc_id:
                    original_vc = m
                    break
            if original_vc:
                break

        if not original_vc:
            raise ValueError(f"No PaymentMandate found with VC id {vc_id}")

        merchant_id = original_vc.get("credentialSubject", {}).get("merchant_id", " ")

        factory = MandateFactory(user_id="system")
        refund_vc = factory.refund(
            signer=self.confirmation_signer,
            original_payment_id=original_vc["id"],
            prev_mandate_id=original_vc["id"],
            amount=amount,
            currency=currency,
            reason=reason,
            merchant_id=merchant_id,
        )

        txn_record = {
            "transaction_id": "refund-" + str(uuid.uuid4()),
            "sender": refund_vc["issuer"],
            "receiver": merchant_id,
            "amount": -amount,
            "currency": currency,
            "merchant_id": merchant_id,
            "mandates": [refund_vc],
        }
        return txn_record

    def process_fraud_flag(
            self,
            flagged_vc_id: str,
            reason: str,
            evidence: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not flagged_vc_id.startswith("urn:uuid:"):
            raise ValueError("Please provide the full VC id (urn:uuid:...)")

        flagged_vc = None
        for txn in self.ledger.transactions:
            for m in txn.get("mandates", []):
                if m.get("id") == flagged_vc_id:
                    flagged_vc = m
                    break
            if flagged_vc:
                break
        if not flagged_vc:
            raise ValueError(f"No mandate found with VC id {flagged_vc_id}")

        subject = flagged_vc.get("credentialSubject", {})
        merchant_id = subject.get("merchant_id", " ")
        currency = (
                subject.get("payment_details", {}).get("currency")
                or subject.get("currency", " ")
        )

        factory = MandateFactory(user_id="system")
        fraud_vc = factory.fraud_flag(
            signer=self.confirmation_signer,
            flagged_mandate_id=flagged_vc["id"],
            prev_mandate_id=flagged_vc["id"],
            reason=reason,
            evidence=evidence,
            merchant_id=merchant_id,
            currency=currency,
        )

        txn_record = {
            "transaction_id": "fraud-" + str(uuid.uuid4()),
            "sender": fraud_vc["issuer"],
            "receiver": merchant_id,
            "amount": 0.0,
            "currency": currency,
            "mandates": [fraud_vc],
        }
        return txn_record
