from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from core.mcp import process_user_request
from pathlib import Path
from datetime import datetime
import uuid
import time
import json
import logging
import os

app = FastAPI()

# Enable CORS for local testing (optional)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup basic logging
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "logs"
LOG_PATH.mkdir(exist_ok=True)

@app.post("/process")
async def handle_process(request: Request):
    request_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        payload = await request.json()
        session_id = payload.get("session_id") or str(uuid.uuid4())
        if "session_id" not in payload:
            logging.info(f"🆕 New session created: {session_id}")

        response = process_user_request(payload, session_id)
        response["session_id"] = session_id

        log_entry = {
            "id": request_id,
            "timestamp": datetime.now().isoformat(),
            "duration": round(time.time() - start_time, 3),
            "input": payload,
            "output": response,
            "session_id": session_id
        }

        with open(LOG_PATH / "mcp_requests.jsonl", "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        return response

    except Exception as e:
        logging.error(f"❌ Error processing request {request_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Internal processing error",
                "error": str(e),
                "request_id": request_id
            }
        )
