# encryption.py
# ============================================================================
# Lightweight Blockchain Framework — Hybrid AES + ECC Encryption Module
# ============================================================================
# Implements the full security pipeline for IoT data:
#   1. AES-256-CBC for fast symmetric payload encryption.
#   2. ECC (secp256k1 via eciespy) for asymmetric AES-key exchange.
#   3. ECDSA digital signatures for PBFT message authentication.
# ============================================================================

import os
import base64
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from ecies import encrypt as ecc_encrypt_raw, decrypt as ecc_decrypt_raw
from ecies.utils import generate_eth_key
from coincurve import PrivateKey as CoinPrivateKey

from config import AES_KEY_SIZE
from utils import get_logger, hash_data

logger = get_logger("encryption")


# ---------------------------------------------------------------------------
# AES-256-CBC Symmetric Cipher
# ---------------------------------------------------------------------------

class AESCipher:
    """
    AES-256-CBC cipher with PKCS7 padding.

    Each call to ``encrypt()`` generates a fresh random IV, which is
    prepended to the ciphertext.  The entire blob is base64-encoded for
    safe transport over JSON / sockets.
    """

    def __init__(self, key: bytes | None = None):
        self.key = key if key else os.urandom(AES_KEY_SIZE)

    def encrypt(self, plaintext: str) -> str:
        iv = os.urandom(AES.block_size)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
        return base64.b64encode(iv + ciphertext).decode("utf-8")

    def decrypt(self, encoded_ciphertext: str) -> str:
        raw = base64.b64decode(encoded_ciphertext)
        iv, ciphertext = raw[: AES.block_size], raw[AES.block_size :]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ciphertext), AES.block_size).decode("utf-8")


# ---------------------------------------------------------------------------
# ECC Key Manager (secp256k1 via eciespy / coincurve)
# ---------------------------------------------------------------------------

class ECCManager:
    """
    Manages an ECC keypair on the secp256k1 curve.

    Capabilities:
      - Encrypt / decrypt AES session keys (ECIES).
      - Sign / verify arbitrary data (ECDSA).
    """

    def __init__(self, private_key_hex: str | None = None):
        if private_key_hex:
            # Strip '0x' prefix if present
            clean_hex = private_key_hex.replace("0x", "")
            self._privkey = CoinPrivateKey(bytes.fromhex(clean_hex))
        else:
            eth_k = generate_eth_key()
            # eth_k.to_hex() returns '0x'-prefixed hex; strip it for coincurve
            raw_hex = eth_k.to_hex().replace("0x", "")
            self._privkey = CoinPrivateKey(bytes.fromhex(raw_hex))

        self.private_key_hex: str = self._privkey.secret.hex()
        self.public_key_hex: str = self._privkey.public_key.format(True).hex()

    # -- Key accessors ------------------------------------------------------

    def get_public_key(self) -> str:
        return self.public_key_hex

    def get_private_key(self) -> str:
        return self.private_key_hex

    # -- ECIES encrypt / decrypt AES key ------------------------------------

    @staticmethod
    def encrypt_aes_key(public_key_hex: str, aes_key: bytes) -> str:
        """Encrypts *aes_key* under the recipient's ECC public key (ECIES)."""
        encrypted = ecc_encrypt_raw(public_key_hex, aes_key)
        return base64.b64encode(encrypted).decode("utf-8")

    def decrypt_aes_key(self, encrypted_aes_key_b64: str) -> bytes:
        """Decrypts an ECIES-encrypted AES key using this node's private key."""
        encrypted = base64.b64decode(encrypted_aes_key_b64)
        return ecc_decrypt_raw(self.private_key_hex, encrypted)

    # -- ECDSA sign / verify ------------------------------------------------

    def sign(self, data: str) -> str:
        """Returns a hex-encoded ECDSA signature over SHA-256(data)."""
        digest = bytes.fromhex(hash_data(data))
        sig = self._privkey.sign_recoverable(digest, hasher=None)
        return sig.hex()

    @staticmethod
    def verify(public_key_hex: str, data: str, signature_hex: str) -> bool:
        """Verifies an ECDSA signature against the signer's public key."""
        try:
            from coincurve import PublicKey as CoinPublicKey

            digest = bytes.fromhex(hash_data(data))
            sig = bytes.fromhex(signature_hex)
            pubkey = CoinPublicKey.from_signature_and_message(sig, digest, hasher=None)
            return pubkey.format(True).hex() == public_key_hex
        except Exception:
            return False


# ---------------------------------------------------------------------------
# High-level encryption / decryption pipeline (IoT data flow)
# ---------------------------------------------------------------------------

def process_iot_data_encryption(data: str, recipient_pub_key_hex: str) -> dict:
    """
    Full encryption pipeline (Steps 1–4 of the security model):

    1. Generate a fresh AES-256 session key.
    2. Encrypt the IoT payload with AES-CBC.
    3. Encrypt the AES key with the recipient's ECC public key.
    4. Bundle both for network transmission.
    """
    aes = AESCipher()
    encrypted_data = aes.encrypt(data)
    encrypted_aes_key = ECCManager.encrypt_aes_key(recipient_pub_key_hex, aes.key)
    logger.debug("Encrypted IoT payload (%d bytes plaintext)", len(data))
    return {
        "encrypted_data": encrypted_data,
        "encrypted_aes_key": encrypted_aes_key,
    }


def process_iot_data_decryption(
    encrypted_data: str,
    encrypted_aes_key: str,
    ecc_manager: ECCManager,
) -> str:
    """
    Decryption pipeline (Step 5 of the security model):

    1. Decrypt AES session key using ECC private key.
    2. Decrypt the IoT payload using the recovered AES key.
    """
    aes_key = ecc_manager.decrypt_aes_key(encrypted_aes_key)
    aes = AESCipher(aes_key)
    return aes.decrypt(encrypted_data)
