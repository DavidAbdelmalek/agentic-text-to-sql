"""API tests for the guarded /ask endpoint. No warehouse: every case here short-circuits
before run_agent (auth/redirect/health), so they run on the offline CI path."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentic_text_to_sql.api import app

client = TestClient(app)


def test_health_ok() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root_redirects_to_docs() -> None:
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/docs"


def test_ask_requires_api_key_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """With API_KEY set, a request without the header is rejected before run_agent runs."""
    monkeypatch.setenv("API_KEY", "secret123")
    r = client.post("/ask", json={"question": "anything"})
    assert r.status_code == 401


def test_ask_rejects_wrong_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "secret123")
    r = client.post("/ask", json={"question": "anything"}, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_ask_validates_body() -> None:
    """Missing question -> 422 from pydantic, never reaching the agent."""
    r = client.post("/ask", json={})
    assert r.status_code == 422
