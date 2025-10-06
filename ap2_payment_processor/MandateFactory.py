"""
Module MandateFactory.py

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

import hashlib
import time
import uuid
from typing import Dict, Any, Optional

import base58


class MandateFactory:
    """
    Designs the various Mandates' as per AP2 0.1-alpha spec
    Implements a few extensions (Netting Mandate)
    Otherwise, 100% per spec.

    Validates against custom local contexts (in JSONFactory.py)
    """
    def __init__(self, user_id: str):
        self.user_id = user_id

    @staticmethod
    def mandate_timestamp() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @staticmethod
    def mandate_expiry(hours: int = 1) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + hours * 3600))

    def mandate_wrap_vc(
            self,
            signer,
            mandate_type: str,
            payload: Dict[str, Any],
            expiration: Optional[str] = None
    ) -> Dict[str, Any]:
        vc = {
            "@context": [
                "https://www.w3.org/2018/credentials/v1",
                "https://ap2-protocol.org/contexts/mandates/v1",
                "https://w3id.org/security/v2"
            ],
            "id": f"urn:uuid:{uuid.uuid4()}",
            "type": ["VerifiableCredential", mandate_type],
            "issuer": signer.issuer_id,
            "issuanceDate": self.mandate_timestamp(),
            "expirationDate": expiration or self.mandate_expiry(1),
            "credentialSchema": {
                "id": "https://ap2-protocol.org/schemas/mandate-schema.json",
                "type": "JsonSchemaValidator2018"
            },
            "credentialStatus": {
                "id": "https://ap2-protocol.org/status/registry#revocation-list-1",
                "type": "RevocationList2020Status"
            },
            "credentialSubject": payload
        }
        vc["proof"] = signer.sign(vc)
        return vc

    def sending(
            self,
            signer,
            receiver: str,
            amount: float,
            currency: str,
            note: str = "",
            raw_intent: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        expiration_override = None

        if raw_intent:
            natural_desc = raw_intent.get("natural_language_description", note or "")
            intent_expiry = raw_intent.get("intent_expiry")
            if intent_expiry:
                expiration_override = intent_expiry

            payload = {
                "label": "User intent to initiate payment",
                "note": natural_desc,
                "mandate_id": str(uuid.uuid4()),
                "prev_mandate_id": None,
                "merchant_id": receiver,
                "payer_info": {
                    "user_id": self.user_id,
                    "credential_provider": "issuer:user-wallet"
                },
                "payee_info": {"merchant_id": receiver},
                "payment_methods": ["card", "wallet"],
                "shopping_intent": {
                    "items": [
                        {"description": natural_desc or "unspecified item", "price": amount, "currency": currency}],
                    "total": amount
                },
                "prompt_playback": f"Send {amount} {currency} to {receiver}",
                "ttl": intent_expiry or self.mandate_expiry(1),
                "details": {
                    "action": "send",
                    "amount": amount,
                    "currency": currency,
                    "destination": receiver,
                    "note": natural_desc
                },
                "user_cart_confirmation_required": raw_intent.get("user_cart_confirmation_required"),
                "natural_language_description": natural_desc,
                "merchants": raw_intent.get("merchants"),
                "skus": raw_intent.get("skus"),
                "required_refundability": raw_intent.get("required_refundability"),
                "intent_expiry": intent_expiry,
            }
        else:
            payload = {
                "label": "User intent to initiate payment",
                "note": note,
                "mandate_id": str(uuid.uuid4()),
                "prev_mandate_id": None,
                "merchant_id": receiver,
                "payer_info": {
                    "user_id": self.user_id,
                    "credential_provider": "issuer:user-wallet"
                },
                "payee_info": {"merchant_id": receiver},
                "payment_methods": ["card", "wallet"],
                "shopping_intent": {
                    "items": [{"description": note or "unspecified item", "price": amount, "currency": currency}],
                    "total": amount
                },
                "prompt_playback": f"Send {amount} {currency} to {receiver}",
                "ttl": self.mandate_expiry(1),
                "details": {
                    "action": "send",
                    "amount": amount,
                    "currency": currency,
                    "destination": receiver,
                    "note": note
                }
            }

        return self.mandate_wrap_vc(signer, "IntentMandate", payload, expiration=expiration_override)

    def checkout(
            self,
            signer,
            receiver: str,
            amount: float,
            currency: str,
            prev_mandate_id: str,
            item_desc: str = "Generic Item"
    ) -> Dict[str, Any]:
        cart_id = str(uuid.uuid4())
        payment_request = {
            "id": cart_id,
            "method_data": [{"supportedMethods": ["basic-card", "https://example.com/pay"]}],
            "details": {
                "displayItems": [{"label": item_desc, "amount": {"currency": currency, "value": amount}}],
                "total": {"label": "Total", "amount": {"currency": currency, "value": amount}}
            }
        }
        payload = {
            "label": "Merchant checkout confirmation",
            "note": item_desc,
            "mandate_id": str(uuid.uuid4()),
            "prev_mandate_id": prev_mandate_id,
            "merchant_id": receiver,
            "contents": {"id": cart_id, "payment_request": payment_request},
            "merchant_signature": f"sig-{uuid.uuid4().hex}",
            "timestamp": self.mandate_timestamp()
        }
        return self.mandate_wrap_vc(signer, "CartMandate", payload)

    def confirmation(
            self,
            signer,
            receiver: str,
            amount: float,
            currency: str,
            txn_id: str,
            prev_mandate_id: str,
            cart_vc: Dict[str, Any]
    ) -> Dict[str, Any]:
        cart_bytes = str(cart_vc).encode("utf-8")
        cart_hash_b58 = base58.b58encode(hashlib.sha256(cart_bytes).digest()).decode("ascii")
        payload = {
            "label": f"Finalized payment for transaction {txn_id}",
            "note": f"Payment of {amount} {currency} to {receiver}",
            "mandate_id": str(uuid.uuid4()),
            "prev_mandate_id": prev_mandate_id,
            "merchant_id": receiver,
            "cart_mandate_hash": cart_hash_b58,
            "payment_details": {
                "transaction_id": txn_id,
                "status": "SUCCESS",
                "amount": amount,
                "currency": currency,
                "settlement_time": self.mandate_timestamp()
            },
            "payment_method": "visa-****1111",
            "risk_info": {"fraud_score": 0.01, "geo_check": "pass"},
            "merchant_agent_card": {"acquirer_id": "bank-xyz", "terminal_id": "term-123"}
        }
        return self.mandate_wrap_vc(signer, "PaymentMandate", payload)

    def refund(
            self,
            signer,
            original_payment_id: str,
            prev_mandate_id: str,
            amount: float,
            currency: str,
            merchant_id: str,
            reason: str
    ) -> Dict[str, Any]:
        payload = {
            "label": f"Refund issued for payment {original_payment_id}",
            "note": reason,
            "refund_id": str(uuid.uuid4()),
            "original_payment_id": original_payment_id,
            "prev_mandate_id": prev_mandate_id,
            "refund_amount": amount,
            "currency": currency,
            "refund_reason": reason,
            "merchant_id": merchant_id,
            "timestamp": self.mandate_timestamp()
        }
        return self.mandate_wrap_vc(signer, "RefundMandate", payload)

    def fraud_flag(
            self,
            signer,
            flagged_mandate_id: str,
            prev_mandate_id: str,
            reason: str,
            evidence: Dict[str, Any],
            merchant_id: str,
            currency: str,
    ) -> Dict[str, Any]:
        payload = {
            "label": f"Fraud flag raised for mandate {flagged_mandate_id}",
            "note": reason,
            "flag_id": str(uuid.uuid4()),
            "flagged_mandate_id": flagged_mandate_id,
            "prev_mandate_id": prev_mandate_id,
            "fraud_reason": reason,
            "evidence": evidence,
            "merchant_id": merchant_id,
            "currency": currency,
            "timestamp": self.mandate_timestamp()
        }
        return self.mandate_wrap_vc(signer, "FraudFlag", payload)

    def netting(
            self,
            signer,
            prev_ids: list[str],
            counterparty: str,
            currency: str,
            amount: float,
            settlement_run: str
    ) -> Dict[str, Any]:
        payload = {
            "label": f"Netting obligation for settlement run {settlement_run}",
            "note": f"Netting {amount}",
            "mandate_id": str(uuid.uuid4()),
            "prev_mandate_id": prev_ids[0],
            "prev_mandate_ids": prev_ids,
            "timestamp": self.mandate_timestamp(),
            "merchant_id": counterparty,
            "payment_details": {
                "amount": amount,
                "currency": currency,
                "counterparty": counterparty,
                "settlement_run": settlement_run,
            }
        }
        return self.mandate_wrap_vc(signer, "NettingMandate", payload)
