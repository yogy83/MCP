import uuid
import logging
import json
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from core.mcp import process_user_request

logger = logging.getLogger("main")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="MCP API",
    version="1.0.0",
    docs_url="/docs",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Tool registry helper ---
def get_all_tools():
    try:
        with open("./schema/tool_registry_llm.json", "r") as f:
            return json.load(f)
    except Exception as ex:
        logger.warning(f"Could not load tool registry: {ex}")
        return []

# --- REST /process ---
class ProcessRequest(BaseModel):
    goal: str
    objective: str
    expected_outcome: str

@app.post("/process")
async def handle_process(request: ProcessRequest):
    session_id = str(uuid.uuid4())
    response = process_user_request(request.dict(), session_id)
    return {
        "session_id": session_id,
        **response
    }

# --- Capabilities (REST) ---
@app.get("/capabilities")
async def get_capabilities():
    return {
        "mcp_version": "1.0.0",
        "transports": [
            {"type": "REST", "path": "/process"},
            {"type": "JSON-RPC", "path": "/mcp"},
            {"type": "SSE", "path": "/mcp/stream"},
            {"type": "WebSocket", "path": "/ws/mcp"},
        ],
        "tools": get_all_tools(),
    }

# --- JSON-RPC 2.0 Transport ---
@app.post("/mcp")
async def handle_mcp(request: Request):
    payload = await request.json()
    logger.info(f"JSON-RPC Payload: {payload}")
    method = payload.get("method")
    params = payload.get("params", {})
    rpc_id = payload.get("id")
    # 1. tools/call (normal LLM ops)
    if method in ("tools/call", "process", "call"):
        required = ["goal", "objective", "expected_outcome"]
        if not all(k in params for k in required):
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32602, "message": "Invalid params"},
                "id": rpc_id
            }
        session_id = params.get("session_id", str(uuid.uuid4()))
        try:
            response = process_user_request(params, session_id)
            return {
                "jsonrpc": "2.0",
                "result": {
                    "session_id": session_id,
                    **response
                },
                "id": rpc_id
            }
        except Exception as ex:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32000,
                    "message": f"Server error: {str(ex)}"
                },
                "id": rpc_id
            }
    # 2. JSON-RPC initialize: discover everything
    elif method == "initialize":
        tools = get_all_tools()
        return {
            "jsonrpc": "2.0",
            "result": {
                "mcp_version": "1.0.0",
                "transports": [
                    {"type": "REST", "path": "/process"},
                    {"type": "JSON-RPC", "path": "/mcp"},
                    {"type": "SSE", "path": "/mcp/stream"},
                    {"type": "WebSocket", "path": "/ws/mcp"}
                ],
                "tools": tools
            },
            "id": rpc_id
        }
    # 3. JSON-RPC tools/list (just return tools)
    elif method == "tools/list":
        tools = get_all_tools()
        return {
            "jsonrpc": "2.0",
            "result": tools,
            "id": rpc_id
        }
    # 4. Unknown method
    else:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": "Method not found"},
            "id": rpc_id
        }

# --- SSE Transport ---
def sse_format(data: str) -> str:
    return f"data: {data}\n\n"

@app.post("/mcp/stream")
async def handle_mcp_stream(request: Request):
    payload = await request.json()
    method = payload.get("method")
    params = payload.get("params", {})
    rpc_id = payload.get("id")

    async def event_generator():
        if method in ("tools/call", "process", "call"):
            session_id = params.get("session_id", str(uuid.uuid4()))
            response = process_user_request(params, session_id)
            yield sse_format(json.dumps({
                "jsonrpc": "2.0",
                "result": {
                    "session_id": session_id,
                    **response
                },
                "id": rpc_id
            }))
        else:
            yield sse_format(json.dumps({
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": "Method not found"},
                "id": rpc_id
            }))
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- WebSocket Transport ---
@app.websocket("/ws/mcp")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            logger.info(f"WebSocket Payload: {data}")
            method = data.get("method")
            params = data.get("params", {})
            rpc_id = data.get("id")
            if method in ("tools/call", "process", "call"):
                session_id = params.get("session_id", str(uuid.uuid4()))
                response = process_user_request(params, session_id)
                await websocket.send_json({
                    "jsonrpc": "2.0",
                    "result": {
                        "session_id": session_id,
                        **response
                    },
                    "id": rpc_id
                })
            elif method == "initialize":
                tools = get_all_tools()
                await websocket.send_json({
                    "jsonrpc": "2.0",
                    "result": {
                        "mcp_version": "1.0.0",
                        "transports": [
                            {"type": "REST", "path": "/process"},
                            {"type": "JSON-RPC", "path": "/mcp"},
                            {"type": "SSE", "path": "/mcp/stream"},
                            {"type": "WebSocket", "path": "/ws/mcp"}
                        ],
                        "tools": tools
                    },
                    "id": rpc_id
                })
            elif method == "tools/list":
                tools = get_all_tools()
                await websocket.send_json({
                    "jsonrpc": "2.0",
                    "result": tools,
                    "id": rpc_id
                })
            else:
                await websocket.send_json({
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": "Method not found"},
                    "id": rpc_id
                })
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected.")

# --- Health check and admin reload endpoints ---
@app.get("/health")
async def health():
    return {"status": "ok", "initialized": True}

# (Optional) Add admin endpoints as needed...

@app.on_event("startup")
async def on_startup():
    logger.info("=" * 50)
    logger.info("🚀 MCP Multi-Transport Service Ready!")
    logger.info("REST:       POST /process")
    logger.info("JSON-RPC:   POST /mcp")
    logger.info("SSE:        POST /mcp/stream")
    logger.info("WebSocket:  /ws/mcp")
    logger.info("Health:     GET /health")
    logger.info("Capabilities: GET /capabilities")
    logger.info("=" * 50)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
