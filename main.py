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

def get_all_tools():
    """
    Load the list of tools from the local JSON registry file.
    
    Returns:
        list: List of tool metadata dictionaries, or empty list on failure.
    """
    try:
        with open("./schema/tool_registry_llm.json", "r") as f:
            return json.load(f)
    except Exception as ex:
        logger.warning(f"Could not load tool registry: {ex}")
        return []

class ProcessRequest(BaseModel):
    """
    Pydantic model for validating REST /process endpoint request body.
    """
    goal: str
    objective: str
    expected_outcome: str

@app.post("/process")
async def handle_process(request: ProcessRequest):
    """
    Handle a classic REST POST /process request.

    Args:
        request (ProcessRequest): JSON body containing goal, objective, expected_outcome.

    Returns:
        dict: The MCP processing result with a generated session_id.
    """
    session_id = str(uuid.uuid4())
    response = process_user_request(request.dict(), session_id)
    return {
        "session_id": session_id,
        **response
    }

@app.get("/capabilities")
async def get_capabilities():
    """
    Return MCP version info, available transports, and tools.

    Returns:
        dict: MCP capabilities including transports and registered tools.
    """
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

@app.post("/mcp")
async def handle_mcp(request: Request):
    """
    Handle JSON-RPC 2.0 POST requests on /mcp endpoint.

    Supports methods:
    - initialize: returns MCP version, tools, transports
    - tools/list: lists registered tools
    - tools/call, process, call: execute a tool call with required params

    Args:
        request (Request): Incoming HTTP request.

    Returns:
        dict: JSON-RPC response object with result or error.
    """
    payload = await request.json()
    logger.info(f"JSON-RPC Payload: {payload}")

    method = payload.get("method")
    params = payload.get("params", {})
    rpc_id = payload.get("id")

    try:
        if method == "initialize":
            tools = await mcp_system.mcp.list_tools()
            tools_json = [t.model_dump() if hasattr(t, "model_dump") else t.dict() for t in tools]
            return {
                "jsonrpc": "2.0",
                "result": {
                    "mcp_version": "1.0.0",
                    "tools": tools_json,
                    "transports": [
                        {"type": "REST", "path": "/process"},
                        {"type": "JSON-RPC", "path": "/mcp"},
                        {"type": "SSE", "path": "/mcp/stream"},
                        {"type": "WebSocket", "path": "/ws/mcp"}
                    ],
                },
                "id": rpc_id
            }

        elif method == "tools/list":
            tools = await mcp_system.mcp.list_tools()
            tools_json = [t.model_dump() if hasattr(t, "model_dump") else t.dict() for t in tools]
            return {
                "jsonrpc": "2.0",
                "result": tools_json,
                "id": rpc_id
            }

        elif method in ("tools/call", "process", "call"):
            required = ["goal", "objective", "expected_outcome"]
            if not all(k in params for k in required):
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": "Invalid params: goal, objective, expected_outcome are required."},
                    "id": rpc_id
                }
            session_id = params.get("session_id", str(uuid.uuid4()))
            result = process_user_request(params, session_id)
            return {
                "jsonrpc": "2.0",
                "result": {
                    "session_id": session_id,
                    **result
                },
                "id": rpc_id
            }

        else:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": "Method not found"},
                "id": rpc_id
            }

    except Exception as ex:
        logger.exception("Exception in JSON-RPC handler")
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32000,
                "message": f"Internal server error: {str(ex)}"
            },
            "id": rpc_id
        }

def sse_format(data: str) -> str:
    """
    Format a string message according to Server-Sent Events protocol.

    Args:
        data (str): Data string to send.

    Returns:
        str: Formatted SSE message string.
    """
    return f"data: {data}\n\n"

@app.post("/mcp/stream")
async def handle_mcp_stream(request: Request):
    """
    Handle JSON-RPC 2.0 requests over Server-Sent Events (SSE).

    Returns a stream of events representing JSON-RPC responses.

    Args:
        request (Request): Incoming HTTP request.

    Returns:
        StreamingResponse: SSE stream of JSON-RPC responses.
    """
    payload = await request.json()
    logger.info(f"SSE JSON-RPC Payload: {payload}")

    method = payload.get("method")
    params = payload.get("params", {})
    rpc_id = payload.get("id")

    async def event_generator():
        try:
            if method == "initialize":
                tools = await mcp_system.mcp.list_tools()
                tools_json = [t.model_dump() if hasattr(t, "model_dump") else t.dict() for t in tools]
                response = {
                    "jsonrpc": "2.0",
                    "result": {
                        "mcp_version": "1.0.0",
                        "tools": tools_json,
                        "transports": [
                            {"type": "REST", "path": "/process"},
                            {"type": "JSON-RPC", "path": "/mcp"},
                            {"type": "SSE", "path": "/mcp/stream"},
                            {"type": "WebSocket", "path": "/ws/mcp"}
                        ],
                    },
                    "id": rpc_id
                }
                yield sse_format(json.dumps(response))

            elif method == "tools/list":
                tools = await mcp_system.mcp.list_tools()
                tools_json = [t.model_dump() if hasattr(t, "model_dump") else t.dict() for t in tools]
                response = {
                    "jsonrpc": "2.0",
                    "result": tools_json,
                    "id": rpc_id
                }
                yield sse_format(json.dumps(response))

            elif method in ("tools/call", "process", "call"):
                required = ["goal", "objective", "expected_outcome"]
                if not all(k in params for k in required):
                    response = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32602, "message": "Invalid params: goal, objective, expected_outcome are required."},
                        "id": rpc_id
                    }
                    yield sse_format(json.dumps(response))
                    return

                session_id = params.get("session_id", str(uuid.uuid4()))
                result = process_user_request(params, session_id)

                response = {
                    "jsonrpc": "2.0",
                    "result": {
                        "session_id": session_id,
                        **result
                    },
                    "id": rpc_id
                }
                yield sse_format(json.dumps(response))

            else:
                response = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": "Method not found"},
                    "id": rpc_id
                }
                yield sse_format(json.dumps(response))

        except Exception as ex:
            logger.exception("Exception in SSE handler")
            response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32000,
                    "message": f"Internal server error: {str(ex)}"
                },
                "id": rpc_id
            }
            yield sse_format(json.dumps(response))

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.websocket("/ws/mcp")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint handling JSON-RPC 2.0 messages.

    Supports:
    - initialize
    - tools/list
    - tools/call, process, call

    Args:
        websocket (WebSocket): The WebSocket connection instance.

    Behavior:
        Continuously receives JSON-RPC requests and sends back JSON-RPC responses.
        Closes on WebSocket disconnect.
    """
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            logger.info(f"WebSocket JSON-RPC Payload: {data}")

            method = data.get("method")
            params = data.get("params", {})
            rpc_id = data.get("id")

            try:
                if method == "initialize":
                    tools = await mcp_system.mcp.list_tools()
                    tools_json = [t.model_dump() if hasattr(t, "model_dump") else t.dict() for t in tools]
                    response = {
                        "jsonrpc": "2.0",
                        "result": {
                            "mcp_version": "1.0.0",
                            "tools": tools_json,
                            "transports": [
                                {"type": "REST", "path": "/process"},
                                {"type": "JSON-RPC", "path": "/mcp"},
                                {"type": "SSE", "path": "/mcp/stream"},
                                {"type": "WebSocket", "path": "/ws/mcp"}
                            ],
                        },
                        "id": rpc_id
                    }
                    await websocket.send_json(response)

                elif method == "tools/list":
                    tools = await mcp_system.mcp.list_tools()
                    tools_json = [t.model_dump() if hasattr(t, "model_dump") else t.dict() for t in tools]
                    response = {
                        "jsonrpc": "2.0",
                        "result": tools_json,
                        "id": rpc_id
                    }
                    await websocket.send_json(response)

                elif method in ("tools/call", "process", "call"):
                    required = ["goal", "objective", "expected_outcome"]
                    if not all(k in params for k in required):
                        response = {
                            "jsonrpc": "2.0",
                            "error": {"code": -32602, "message": "Invalid params: goal, objective, expected_outcome are required."},
                            "id": rpc_id
                        }
                        await websocket.send_json(response)
                        continue

                    session_id = params.get("session_id", str(uuid.uuid4()))
                    result = process_user_request(params, session_id)
                    response = {
                        "jsonrpc": "2.0",
                        "result": {
                            "session_id": session_id,
                            **result
                        },
                        "id": rpc_id
                    }
                    await websocket.send_json(response)

                else:
                    response = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32601, "message": "Method not found"},
                        "id": rpc_id
                    }
                    await websocket.send_json(response)

            except Exception as ex:
                logger.exception("Exception in WebSocket handler")
                response = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32000,
                        "message": f"Internal server error: {str(ex)}"
                    },
                    "id": rpc_id
                }
                await websocket.send_json(response)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")

@app.get("/health")
async def health():
    """
    Health check endpoint.

    Returns:
        dict: Service health status.
    """
    return {"status": "ok", "initialized": True}

@app.on_event("startup")
async def on_startup():
    """
    Log service readiness info at application startup.
    """
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
