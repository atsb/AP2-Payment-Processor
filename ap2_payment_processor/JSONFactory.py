"""
Module JSONFactory.py

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
from pathlib import Path
from typing import Any, Dict

from pyld import jsonld


CONTEXT_DIR = Path("../contexts")


def json_load_context_schema_file(filename: str) -> dict:
    """Loads local contexts for validation of schema"""
    return json.loads((CONTEXT_DIR / filename).read_text(encoding="utf-8"))


LOCAL_CONTEXTS = {
    "https://www.w3.org/2018/credentials/v1": json_load_context_schema_file("credentials_v1.json"),
    "https://w3id.org/security/v2": json_load_context_schema_file("security_v2.json"),
    "https://w3id.org/security/v1": json_load_context_schema_file("security-v1.json"),

    "https://ap2-protocol.org/contexts/mandates/v1": {
        "@context": {
            "@version": 1.1,
            "IntentMandate": "https://ap2-protocol.org/mandates#IntentMandate",
            "CartMandate": "https://ap2-protocol.org/mandates#CartMandate",
            "PaymentMandate": "https://ap2-protocol.org/mandates#PaymentMandate",
            "RefundMandate": "https://ap2-protocol.org/mandates#RefundMandate",
            "FraudFlag": "https://ap2-protocol.org/mandates#FraudFlag",
            "NettingMandate": "https://ap2-protocol.org/mandates#NettingMandate",

            "mandate_id": "https://ap2-protocol.org/mandates#mandate_id",
            "prev_mandate_id": "https://ap2-protocol.org/mandates#prev_mandate_id",
            "prev_mandate_ids": {
                "@id": "https://ap2-protocol.org/mandates#prev_mandate_ids",
                "@container": "@set"
            },

            "merchant_id": "https://ap2-protocol.org/mandates#merchant_id",
            "payer_info": {"@id": "https://ap2-protocol.org/mandates#payer_info", "@type": "@json"},
            "payee_info": {"@id": "https://ap2-protocol.org/mandates#payee_info", "@type": "@json"},
            "payment_details": {"@id": "https://ap2-protocol.org/mandates#payment_details", "@type": "@json"},

            "refund_id": "https://ap2-protocol.org/mandates#refund_id",
            "original_payment_id": "https://ap2-protocol.org/mandates#original_payment_id",
            "refund_amount": "https://ap2-protocol.org/mandates#refund_amount",
            "refund_reason": "https://ap2-protocol.org/mandates#refund_reason",

            "flag_id": "https://ap2-protocol.org/mandates#flag_id",
            "flagged_mandate_id": "https://ap2-protocol.org/mandates#flagged_mandate_id",
            "fraud_reason": "https://ap2-protocol.org/mandates#fraud_reason",
            "evidence": {"@id": "https://ap2-protocol.org/mandates#evidence", "@type": "@json"},

            "counterparty": "https://ap2-protocol.org/mandates#counterparty",
            "currency": "https://ap2-protocol.org/mandates#currency",
            "amount": "https://ap2-protocol.org/mandates#amount",
            "settlement_run": "https://ap2-protocol.org/mandates#settlement_run",
            "timestamp": "https://ap2-protocol.org/mandates#timestamp"
        }
    }
}


def json_local_loader(url: str, options=None):
    """Loads the hardcoded schema"""
    doc = LOCAL_CONTEXTS.get(url)
    if doc is None:
        raise Exception(f"No local context for {url}")
    return {
        "contextUrl": None,
        "documentUrl": url,
        "document": doc
    }


def json_canonicalize_vc_for_signing(vc: Dict[str, Any]) -> bytes:
    """Initiate canonicalisation"""
    body = dict(vc)
    body.pop("proof", None)
    nquads = jsonld.normalize(
        body,
        options={
            "algorithm": "URDNA2015",
            "format": "application/n-quads",
            "documentLoader": json_local_loader,
        },
    )
    return nquads.encode("utf-8")
