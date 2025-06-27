# tests/test_mcp_server.py
# Pytest suite for MCP JSON-RPC interface in core/mcp_server.py

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path so imports resolve correctly
dir_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if dir_root not in sys.path:
    sys.path.insert(0, dir_root)

from core.mcp_server import mcp

@pytest.fixture(autouse=True)
def mock_processing(monkeypatch):
    """
    Replace the real process_user_request with a dummy that
    returns a predictable dict. This isolates the JSON-RPC layer.
    """
    from core import mcp_server

    def fake_process_user_request(params, session_id):
        return {
            "status": "success",
            "session_id": session_id,
            "input": params
        }

    monkeypatch.setattr(
        mcp_server,
        "process_user_request",
        fake_process_user_request
    )

# Create a TestClient against the raw JSON-RPC sub-app
app = mcp.streamable_http_app()
client = TestClient(app)


def test_initialize_method():
    """Tests that 'initialize' returns a proper capabilities object."""
    payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {},
        "id": 1
    }

    response = client.post("/", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1

    result = data["result"]
    assert isinstance(result, dict)

    # core fields
    assert result["serverName"] == "MCP Server"
    assert isinstance(result["schemaVersion"], str)

    # transports
    transports = result.get("transports")
    assert isinstance(transports, list)
    # should at least support HTTP
    assert "http" in transports or "streamable_http" in transports

    # tools list must include our tools_call
    tools = result.get("tools")
    assert isinstance(tools, list)
    assert any(tool.get("name") == "tools_call" for tool in tools)


def test_tools_call_success():
    """Tests that 'tools_call' returns our mocked result on valid params."""
    inner = {
        "goal": "g",
        "objective": "o",
        "expected_outcome": "e",
        "session_id": "s1"
    }
    payload = {
        "jsonrpc": "2.0",
        "method": "tools_call",
        "params": {
            "method": "tools_call",
            "params": inner
        },
        "id": 2
    }

    response = client.post("/", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 2
    assert "error" not in data

    result = data["result"]
    assert result["status"] == "success"
    assert result["session_id"] == "s1"
    # ensure our fake params made it through
    assert result["input"] == inner


def test_tools_call_invalid_params():
    """Tests that missing 'params' subkey yields a -32602 Invalid Params error."""
    payload = {
        "jsonrpc": "2.0",
        "method": "tools_call",
        "params": {},  # missing both 'method' and 'params'
        "id": 3
    }

    response = client.post("/", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 3

    error = data.get("error")
    assert isinstance(error, dict)
    assert error["code"] == -32602
    assert isinstance(error["message"], str)
