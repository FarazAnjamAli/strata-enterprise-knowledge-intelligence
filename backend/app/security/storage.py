"""Encryption at rest for uploaded file blobs (Fernet: AES-128-CBC + HMAC).

Every new upload is written encrypted; parsing and download decrypt on the
fly. Files stored before encryption was enabled (no Fernet marker) are read
as plaintext, so nothing breaks on upgrade.

Key management: FILE_ENCRYPTION_KEY in .env (generate with
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
Rotation (documented policy: monthly): MultiFernet decrypts with any listed
key and encrypts with the first, so set FILE_ENCRYPTION_KEY="new,old",
re-upload or re-save files at leisure, then drop the old key.
If the key is unset, files are stored in plaintext (dev fallback).
"""

import logging
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import get_settings

logger = logging.getLogger("strata.storage")

_MAGIC = b"NZENC1\n"  # marker so plaintext legacy files stay readable


class DecryptionError(Exception):
    pass


@lru_cache
def _fernet() -> MultiFernet | None:
    keys = [k.strip() for k in get_settings().file_encryption_key.split(",") if k.strip()]
    if not keys:
        return None
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt_bytes(data: bytes) -> bytes:
    f = _fernet()
    if f is None:
        return data
    return _MAGIC + f.encrypt(data)


def read_decrypted(path: Path) -> bytes:
    """Read a stored blob, decrypting when it carries the encryption marker."""
    raw = path.read_bytes()
    if not raw.startswith(_MAGIC):
        return raw  # legacy plaintext file
    f = _fernet()
    if f is None:
        raise DecryptionError(f"{path.name} is encrypted but FILE_ENCRYPTION_KEY is unset")
    try:
        return f.decrypt(raw[len(_MAGIC) :])
    except InvalidToken as exc:
        raise DecryptionError(f"{path.name}: no configured key can decrypt it") from exc
