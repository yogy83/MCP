import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://127.0.0.1:8000/ws/mcp"
    async with websockets.connect(uri) as ws:
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "goal": "get account transactions for account 105929",
                "objective": "retrieve the transaction history for account id 105929",
                "expected_outcome": "show the transaction history for account 105929"
            },
            "id": 1
        }
        await ws.send(json.dumps(payload))
        resp = await ws.recv()
        print("WebSocket Response:", resp)

asyncio.run(test_ws())
