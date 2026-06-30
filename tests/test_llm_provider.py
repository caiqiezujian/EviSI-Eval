from __future__ import annotations

import http.client

from evisi_eval.config import ProviderConfig
from evisi_eval.llm_provider import HTTPJSONClient


class _FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.headers: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self.payload


def test_incomplete_read_is_retried(monkeypatch) -> None:
    attempts = 0

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise http.client.IncompleteRead(b"", 10)
        return _FakeResponse(b'{"ok": true}')

    monkeypatch.setattr("evisi_eval.llm_provider.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("evisi_eval.llm_provider.time.sleep", lambda _: None)
    client = HTTPJSONClient(ProviderConfig(
        name="test", protocol="openai_compatible", api_key="secret",
        model="fixture", base_url="https://example.invalid", max_retries=1,
    ))

    data, _ = client._post("https://example.invalid", {"x": 1}, {}, "retry_test")
    assert data == {"ok": True}
    assert attempts == 2
