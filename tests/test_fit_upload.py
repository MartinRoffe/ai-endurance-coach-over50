"""POST /upload-fit rejects bad files before they are stored under a client name."""
import asyncio
import re

import pytest
from fastapi.testclient import TestClient

from ai_endurance_coach_over50.fit_upload import (
    DEFAULT_FIT_MAX_BYTES,
    FitUploadRejected,
    fit_extension_ok,
    fit_header_ok,
    max_fit_upload_bytes,
    read_fit_bytes,
    safe_fit_filename,
)
from ai_endurance_coach_over50.server import app

_STORED = re.compile(r"^[0-9a-f]{32}\.fit$")


def _fit(payload: bytes = b"") -> bytes:
    """Bytes whose header magic at 8–11 is ``.FIT``."""
    if payload:
        return payload
    return bytes(8) + b".FIT" + b"\x00" * 16


class _Chunks:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.reads = 0

    async def read(self, _n: int = -1) -> bytes:
        self.reads += 1
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


def test_default_limit_is_20_mib():
    assert DEFAULT_FIT_MAX_BYTES == 20 * 1024 * 1024
    assert max_fit_upload_bytes() == DEFAULT_FIT_MAX_BYTES


def test_extension_uses_basename_only():
    assert fit_extension_ok("../../etc/passwd.fit")
    assert fit_extension_ok("RIDE.FIT")
    assert not fit_extension_ok("ride.txt")
    assert not fit_extension_ok("fit")
    assert not fit_extension_ok("")


def test_header_magic_is_bytes_8_to_11():
    assert fit_header_ok(_fit())
    assert not fit_header_ok(b".FIT" + bytes(8))
    assert not fit_header_ok(b"")


def test_safe_filename_is_server_generated():
    name = safe_fit_filename()
    assert _STORED.fullmatch(name)
    assert safe_fit_filename() != name


def test_stream_stops_when_the_second_chunk_crosses_the_cap():
    first = _fit()
    upload = _Chunks([first, b"\x00" * 100, b"\x00" * 100])
    with pytest.raises(FitUploadRejected) as exc:
        asyncio.run(read_fit_bytes(upload, max_bytes=len(first) + 10, chunk_size=64))
    assert exc.value.status_code == 413
    assert upload.reads == 2


def test_stream_stops_on_bad_magic_without_reading_the_rest():
    upload = _Chunks([b"\x00" * 20, b"\x00" * 50])
    with pytest.raises(FitUploadRejected) as exc:
        asyncio.run(read_fit_bytes(upload, max_bytes=10_000, chunk_size=64))
    assert exc.value.status_code == 422
    assert "header" in exc.value.message
    assert upload.reads == 1


def test_empty_upload_is_422():
    upload = _Chunks([b""])
    with pytest.raises(FitUploadRejected) as exc:
        asyncio.run(read_fit_bytes(upload, max_bytes=1000))
    assert exc.value.status_code == 422
    assert "empty" in exc.value.message


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DASHBOARD_USER", raising=False)
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    return TestClient(app)


def test_upload_rejects_missing_file(client):
    res = client.post("/upload-fit", data={})
    assert res.status_code == 422
    assert "no file" in res.json()["error"]


def test_upload_rejects_bad_extension(client):
    res = client.post("/upload-fit", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert res.status_code == 422
    assert ".fit" in res.json()["error"]


def test_upload_rejects_empty_fit(client):
    res = client.post("/upload-fit", files={"file": ("ride.fit", b"", "application/octet-stream")})
    assert res.status_code == 422
    assert "empty" in res.json()["error"]


def test_upload_rejects_bad_magic(client):
    res = client.post(
        "/upload-fit",
        files={"file": ("ride.fit", b"\x00" * 32, "application/octet-stream")},
    )
    assert res.status_code == 422
    assert "8–11" in res.json()["error"] or "8-11" in res.json()["error"]


def test_upload_rejects_oversize_from_env(client, monkeypatch):
    monkeypatch.setenv("FIT_MAX_UPLOAD_BYTES", "32")
    body = _fit() + b"\x00" * 64
    res = client.post(
        "/upload-fit",
        files={"file": ("ride.fit", body, "application/octet-stream")},
    )
    assert res.status_code == 413
    assert "32" in res.json()["error"]


def test_upload_stores_a_generated_name_not_the_client_path(client):
    res = client.post(
        "/upload-fit",
        files={"file": ("../../etc/passwd.fit", _fit(), "application/octet-stream")},
    )
    assert 400 <= res.status_code < 500
    payload = res.json()
    assert _STORED.fullmatch(payload["stored_name"])
    assert "passwd" not in res.text
    assert ".." not in payload["stored_name"]
