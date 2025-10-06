"""
Module MandateSigner.py

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

import time
from typing import Dict, Any

import base58
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from JSONFactory import json_canonicalize_vc_for_signing
from KeyManager import KeyManager


class MandateSigner:
    """
    Signs the Mandates with our JSON-LD canonicalisation and base58btc encoding algorithm
    As per spec URDNA2015.
    """
    def __init__(self, key_manager: KeyManager, issuer_id: str):
        self.key_manager = key_manager
        self.issuer_id = issuer_id

    def sign(self, mandate_body: Dict[str, Any]) -> Dict[str, Any]:
        body_bytes = json_canonicalize_vc_for_signing(mandate_body)

        sk = self.key_manager.key_get_signer(self.issuer_id)
        signature = sk.sign(body_bytes).signature
        signature_b58 = base58.b58encode(signature).decode("ascii")

        return {
            "type": "Ed25519Signature2020",
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "verificationMethod": f"{self.issuer_id}#keys-1",
            "proofPurpose": "assertionMethod",
            "proofValue": signature_b58,
        }

    @staticmethod
    def verify(mandate: Dict[str, Any], key_manager: KeyManager) -> bool:
        proof = mandate.get("proof")
        if not proof:
            return False

        mandate_copy = dict(mandate)
        mandate_copy.pop("proof", None)
        body_bytes = json_canonicalize_vc_for_signing(mandate_copy)

        try:
            vm = proof["verificationMethod"]
            pubkey = key_manager.key_resolve_verification_method(vm)
            sig = base58.b58decode(proof["proofValue"])
            vk = VerifyKey(pubkey)
            vk.verify(body_bytes, sig)
            return True
        except KeyError as e:
            print(f"[verify] missing field: {e}")
            return False
        except BadSignatureError:
            print("[verify] bad signature")
            return False
        except Exception as e:
            print(f"[verify] verification error: {e}")
            return False
