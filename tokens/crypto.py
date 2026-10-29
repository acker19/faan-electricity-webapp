import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    configured_key = settings.TOKEN_ENCRYPTION_KEY
    if configured_key:
        return Fernet(configured_key.encode("ascii"))
    if not settings.DEBUG:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY must be configured outside DEBUG mode.")
    derived_key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    )
    return Fernet(derived_key)


def encrypt_token(token: str) -> bytes:
    return _fernet().encrypt(token.encode("utf-8"))


def decrypt_token(value: bytes) -> str:
    return _fernet().decrypt(value).decode("utf-8")
