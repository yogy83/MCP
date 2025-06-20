# core/mcp_server.py

import uuid
import time
import json
import logging
from pathlib import Path
from typing import Optional


from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.mcp import process_user_request
import logging

# Enable DEBUG for our planner module only
logging.getLogger("core.planner").setLevel(logging.DEBUG)


# —— App & CORS setup —————————————————————————————————————————————
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)


# —— Logging path ———————————————————————————————————————————————————
BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "logs"


# —— Request & Error models ———————————————————————————————————————
class ProcessRequest(BaseModel):
    session_id: Optional[str] = Field(
        None, description="Client-provided session identifier"
    )
    goal: str = Field(..., description="User’s high-level goal")
    objective: str = Field(..., description="Tool + filter specification")
    expected_outcome: str = Field(..., description="What the user expects back")


class ErrorDetail(BaseModel):
    error: str
    request_id: str


# —— Background log writer ————————————————————————————————————————
def _write_log(entry: dict):
    try:
        LOG_PATH.mkdir(parents=True, exist_ok=True)
        path = LOG_PATH / "mcp_requests.jsonl"
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        logging.exception("Failed to write request log")


# —— /process endpoint —————————————————————————————————————————————
@app.post("/process")
async def handle_process(
    payload: ProcessRequest,
    bg: BackgroundTasks,
):
    # 1) IDs & timing
    request_id = str(uuid.uuid4())
    session_id = payload.session_id or str(uuid.uuid4())
    if payload.session_id is None:
        logging.info(f"🆕 New session created: {session_id}")
    start_ts = time.time()

    # 2) Prepare dict for planner
    req_dict = payload.model_dump(exclude_none=True)

    # 3) Execute
    log_enabled = True
    result = None
    try:
        result = process_user_request(req_dict, session_id)
        result["session_id"] = session_id

    except ValueError as ve:
        # Domain validation error → 400, but still logged
        logging.warning(f"Validation error: {ve}")
        result = {}
        raise HTTPException(status_code=400, detail=str(ve))

    except Exception as exc:
        # Unexpected crash → 500, no log
        logging.exception(f"❌ Error processing request {request_id}")
        log_enabled = False
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                error=str(exc),
                request_id=request_id
            ).model_dump()
        )

    finally:
        if log_enabled:
            duration = round(time.time() - start_ts, 3)
            log_entry = {
                "id": request_id,
                "session_id": session_id,
                "timestamp": time.time(),
                "duration": duration,
                "input": req_dict,
                "output": result,
            }
            bg.add_task(_write_log, log_entry)

    # 4) Return result
    return result
