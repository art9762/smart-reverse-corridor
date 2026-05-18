"""Smoke test for the FastAPI app (engine disabled)."""

from __future__ import annotations

import os

os.environ["CONTROLLER_SKIP_ENGINE"] = "1"

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health_responds_when_engine_skipped(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "starting")
    assert "fsm_phase" in body


def test_state_returns_503_when_engine_skipped(client):
    r = client.get("/state")
    # engine intentionally not started in this smoke test
    assert r.status_code == 503
