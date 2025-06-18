import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

LOG_FILE = Path("logs/mcp_requests.jsonl")

def print_divider():
    print("\n" + "-" * 60 + "\n")

def format_timestamp_ist(raw_ts):
    """Convert Unix timestamp (seconds) to IST datetime string."""
    if isinstance(raw_ts, (int, float)):
        # UTC time
        utc_dt = datetime.utcfromtimestamp(raw_ts).replace(tzinfo=timezone.utc)
        # IST offset = UTC + 5:30
        ist_offset = timedelta(hours=5, minutes=30)
        ist_dt = utc_dt + ist_offset
        return ist_dt.strftime("%Y-%m-%d %H:%M:%S IST")
    return "N/A"

def view_logs():
    if not LOG_FILE.exists():
        print("❌ No logs found at:", LOG_FILE)
        return

    with open(LOG_FILE, "r") as f:
        for idx, line in enumerate(f, start=1):
            try:
                entry = json.loads(line)
                raw_ts = entry.get("timestamp")
                timestamp_str = format_timestamp_ist(raw_ts)
                log_id = entry.get("id", f"entry_{idx}")
                duration = entry.get("duration", "N/A")
                input_data = entry.get("input", {})
                output_data = entry.get("output", {})
                session_id = output_data.get("session_id") or input_data.get("session_id")

                print_divider()
                print(f"🧾 Log Entry #{idx}")
                print(f"🆔 ID: {log_id}")
                print(f"📅 Timestamp: {timestamp_str} (raw: {raw_ts})")
                if session_id:
                    print(f"🆔 Session ID: {session_id}")
                print(f"🕒 Duration: {duration}s")

                print("\n📥 Request to MCP:")
                print(json.dumps(input_data, indent=2))

                print("\n📤 Output from MCP:")
                print(json.dumps(output_data, indent=2))

            except json.JSONDecodeError:
                print(f"⚠️ Failed to parse line #{idx}")

if __name__ == "__main__":
    view_logs()
