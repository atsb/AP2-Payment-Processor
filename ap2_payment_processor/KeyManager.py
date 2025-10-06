"""
Module KeyManager.py

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

from typing import Dict

import base58
from nacl.signing import SigningKey


class KeyManager:
    """
    Manages the signing of Mandate's with base58btc encoding
    """
    def __init__(self):
        self._keys: Dict[str, SigningKey] = {}

    def key_generate_issuer(self, issuer_id: str):
        sk = SigningKey.generate()
        self._keys[issuer_id] = sk

    def key_get_signer(self, issuer_id: str) -> SigningKey:
        """signs issuer"""
        return self._keys[issuer_id]

    def key_get_pubkey_b58(self, issuer_id: str) -> str:
        """Return the issuer's public key encoded in base58btc."""
        return base58.b58encode(bytes(self._keys[issuer_id].verify_key)).decode("ascii")

    def key_export_public_keys(self) -> Dict[str, str]:
        """Export all issuers' public keys as base58btc strings."""
        return {issuer: self.key_get_pubkey_b58(issuer) for issuer in self._keys}

    def key_resolve_verification_method(self, vm_uri: str) -> bytes:
        """
        Mock resolver: uri like 'issuer:merchant#keys-1'.
        Returns raw public key bytes for the issuer.
        """
        try:
            issuer_id, _ = vm_uri.split("#", 1)
        except ValueError:
            raise ValueError(f"Invalid verificationMethod URI: {vm_uri}")
        pub_b58 = self.key_get_pubkey_b58(issuer_id)
        return base58.b58decode(pub_b58)
