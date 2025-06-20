# tests/test_mcp_server.py

import os
import sys
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path so `import core.mcp_server` works
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.mcp_server as server

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def fake_log_path(tmp_path, monkeypatch):
    """
    Redirect the server's LOG_PATH to a temp dir so we can inspect logs.
    """
    monkeypatch.setattr(server, "LOG_PATH", tmp_path)
    return tmp_path


def test_invalid_json_returns_422():
    """
    Sending malformed JSON is rejected by FastAPI/Pydantic → HTTP 422.
    """
    r = client.post(
        "/process",
        data="not-a-json",
        headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 422

    body = r.json()
    # Should be a list of validation errors
    assert isinstance(body.get("detail"), list)
    # Error message should mention JSON decoding
    msgs = [err.get("msg", "") for err in body["detail"]]
    assert any("Expecting value" in m or "JSON" in m for m in msgs)


@pytest.mark.parametrize("missing_field", ["goal", "objective", "expected_outcome"])
def test_missing_required_field_returns_422(missing_field):
    """
    Omitting any required field → HTTP 422 from FastAPI/Pydantic.
    """
    payload = {
        "goal": "g",
        "objective": "o",
        "expected_outcome": "e"
    }
    payload.pop(missing_field)
    r = client.post("/process", json=payload)
    assert r.status_code == 422

    body = r.json()
    # The error detail must mention the missing field
    locs = [err.get("loc", []) for err in body["detail"]]
    assert any(missing_field in loc for loc in locs)


def test_handle_process_success_creates_session_and_logs(monkeypatch, fake_log_path):
    """
    Happy-path: process_user_request returns normally → HTTP 200,
    result includes session_id, and log is written.
    """
    # Stub out process_user_request
    fake_output = {"foo": "bar"}
    monkeypatch.setattr(
        server,
        "process_user_request",
        lambda payload, session_id: fake_output.copy()
    )

    payload = {
        "goal": "anything",
        "objective": "whatever",
        "expected_outcome": "nothing"
    }
    r = client.post("/process", json=payload)
    assert r.status_code == 200

    body = r.json()
    # Check output & session_id
    assert body["foo"] == "bar"
    assert "session_id" in body
    sess = body["session_id"]
    uuid.UUID(sess)

    # Verify log entry
    log_file = fake_log_path / "mcp_requests.jsonl"
    assert log_file.exists()
    lines = log_file.read_text().splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["session_id"] == sess
    assert entry["input"] == payload
    assert entry["output"]["foo"] == "bar"
    assert "timestamp" in entry
    assert "duration" in entry
    uuid.UUID(entry["id"])


def test_handle_process_preserves_client_session_id(monkeypatch):
    """
    If the client supplies session_id, the server echoes it back.
    """
    monkeypatch.setattr(
        server,
        "process_user_request",
        lambda payload, session_id: {"ok": True}
    )
    custom_session = "123e4567-e89b-12d3-a456-426614174000"

    payload = {
        "session_id": custom_session,
        "goal": "x",
        "objective": "y",
        "expected_outcome": "z"
    }
    r = client.post("/process", json=payload)
    assert r.status_code == 200
    assert r.json()["session_id"] == custom_session


def test_handle_process_400_on_value_error(monkeypatch, fake_log_path):
    """
    If process_user_request raises ValueError, return HTTP 400.
    Background logging is scheduled but not executed in TestClient, so no log file.
    """
    def fail_val(payload, session_id):
        raise ValueError("invalid dates")
    monkeypatch.setattr(server, "process_user_request", fail_val)

    payload = {
        "goal": "bad dates",
        "objective": "o",
        "expected_outcome": "e"
    }
    r = client.post("/process", json=payload)
    assert r.status_code == 400

    body = r.json()
    assert "invalid dates" in body["detail"]

    # No log file will exist in this test for a 400
    log_file = fake_log_path / "mcp_requests.jsonl"
    assert not log_file.exists()


def test_handle_process_500_on_exception(monkeypatch, fake_log_path):
    """
    If process_user_request raises an unexpected exception, return HTTP 500 and do NOT log.
    """
    def crash(payload, session_id):
        raise RuntimeError("boom!")
    monkeypatch.setattr(server, "process_user_request", crash)

    payload = {
        "goal": "crash",
        "objective": "",
        "expected_outcome": ""
    }
    r = client.post("/process", json=payload)
    assert r.status_code == 500

    detail = r.json()["detail"]
    assert "boom!" in detail["error"]
    assert "request_id" in detail

    # No log should be created on exception
    log_file = fake_log_path / "mcp_requests.jsonl"
    assert not log_file.exists()
