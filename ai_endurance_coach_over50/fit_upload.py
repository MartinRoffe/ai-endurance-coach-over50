"""Bounded, validated FIT uploads for POST /upload-fit.

The body is read in chunks so a huge request is rejected before it is buffered
past the limit. The client filename is never used as a path.
"""
from __future__ import annotations

import os
import uuid
from pathlib import PurePath

# Default 20 MiB. Override with FIT_MAX_UPLOAD_BYTES (integer bytes).
DEFAULT_FIT_MAX_BYTES = 20 * 1024 * 1024
_CHUNK = 64 * 1024
_FIT_MAGIC = b".FIT"


class FitUploadRejected(Exception):
    """Client error. ``status_code`` is a 4xx."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def max_fit_upload_bytes() -> int:
    """Positive byte cap from FIT_MAX_UPLOAD_BYTES, else 20 MiB."""
    raw = os.getenv("FIT_MAX_UPLOAD_BYTES", "").strip()
    if not raw:
        return DEFAULT_FIT_MAX_BYTES
    try:
        n = int(raw)
    except ValueError:
        return DEFAULT_FIT_MAX_BYTES
    if n <= 0:
        return DEFAULT_FIT_MAX_BYTES
    return n


def fit_extension_ok(filename: str | None) -> bool:
    """True when the basename ends in .fit (any case). Paths are not trusted."""
    base = PurePath((filename or "").replace("\\", "/")).name
    return base.lower().endswith(".fit") and len(base) > 4


def safe_fit_filename() -> str:
    """Server-generated name. Never derived from the client filename."""
    return f"{uuid.uuid4().hex}.fit"


def fit_header_ok(raw: bytes) -> bool:
    """FIT header magic is the ASCII string ``.FIT`` at bytes 8–11."""
    return len(raw) >= 12 and raw[8:12] == _FIT_MAGIC


async def read_fit_bytes(upload, max_bytes: int, chunk_size: int = _CHUNK) -> bytes:
    """Stream ``upload.read`` and stop once the cap or a bad header is clear.

    Raises FitUploadRejected (413 oversize, 422 empty or bad magic). Does not
    keep reading after the rejection.
    """
    if max_bytes <= 0:
        raise FitUploadRejected("FIT upload limit is not configured", 422)
    buf = bytearray()
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        if len(buf) + len(chunk) > max_bytes:
            raise FitUploadRejected(
                f"FIT file exceeds the {max_bytes} byte limit",
                413,
            )
        buf.extend(chunk)
        if len(buf) >= 12 and buf[8:12] != _FIT_MAGIC:
            raise FitUploadRejected(
                "Not a FIT file: missing .FIT header at bytes 8–11",
                422,
            )
    if not buf:
        raise FitUploadRejected("empty file", 422)
    if not fit_header_ok(bytes(buf)):
        raise FitUploadRejected(
            "Not a FIT file: missing .FIT header at bytes 8–11",
            422,
        )
    return bytes(buf)
