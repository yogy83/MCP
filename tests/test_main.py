import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


import pytest
import json
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_and_capabilities():
    resp = client.get("/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert "mcp_version" in data
    assert "tools" in data

def test_rest_process_valid_request():
    payload = {
        "goal": "get account transactions for account 105929",
        "objective": "retrieve the transaction history for account id 105929",
        "expected_outcome": "show the transaction history for account 105929"
    }
    resp = client.post("/process", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data

@pytest.mark.asyncio
async def test_websocket_tools_call():
    import websockets
    uri = "ws://127.0.0.1:8000/ws/mcp"
    async with websockets.connect(uri) as websocket:
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "goal": "get account transactions for account 105929",
                "objective": "retrieve transaction history",
                "expected_outcome": "show transactions"
            },
            "id": 1
        }
        await websocket.send(json.dumps(request))
        response = await websocket.recv()
        data = json.loads(response)
        assert "result" in data

@pytest.mark.asyncio
async def test_websocket_method_not_found():
    import websockets
    uri = "ws://127.0.0.1:8000/ws/mcp"
    async with websockets.connect(uri) as websocket:
        request = {
            "jsonrpc": "2.0",
            "method": "unknown/method",
            "params": {},
            "id": 99
        }
        await websocket.send(json.dumps(request))
        response = await websocket.recv()
        data = json.loads(response)
        assert "error" in data
        assert data["error"]["code"] == -32601

def test_sse_stream_tools_call():
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "goal": "get account transactions for account 105929",
            "objective": "retrieve transaction history",
            "expected_outcome": "show transactions"
        },
        "id": 1
    }
    response = client.post("/mcp/stream", json=payload)
    content = response.content.decode()
    # Check if the SSE data format includes jsonrpc key
    assert "jsonrpc" in content
