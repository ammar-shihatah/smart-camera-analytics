"""
Symmetric encryption for sensitive at-rest values (e.g. camera passwords).

A Fernet key is derived from SECRET_KEY so no extra config is required.
Encrypted values are prefixed with "enc:" so we can transparently support
legacy plaintext values that were stored before encryption was added.
"""
import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_PREFIX = "enc:"


def _fernet() -> Fernet:
    secret = os.getenv("SECRET_KEY", "dev-secret-change-in-production-xyz987")
    # Derive a stable 32-byte urlsafe-base64 key from the app secret
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plain: str | None) -> str | None:
    """Encrypt a plaintext secret. None/empty passes through unchanged."""
    if not plain:
        return plain
    if plain.startswith(_PREFIX):  # already encrypted
        return plain
    try:
        token = _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")
        return _PREFIX + token
    except Exception as exc:  # pragma: no cover - never block on crypto failure
        logger.error(f"Failed to encrypt secret: {exc}")
        return plain


def decrypt_secret(stored: str | None) -> str | None:
    """
    Decrypt a stored secret. Values without the enc: prefix are treated as
    legacy plaintext and returned as-is (backward compatible).
    """
    if not stored:
        return stored
    if not stored.startswith(_PREFIX):
        return stored  # legacy plaintext
    token = stored[len(_PREFIX):]
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.warning("Could not decrypt secret (key changed?) — returning empty")
        return ""
    except Exception as exc:  # pragma: no cover
        logger.error(f"Failed to decrypt secret: {exc}")
        return ""
