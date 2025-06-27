import os
import json
import logging
from pathlib import Path
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


def load_json_file(filepath: str):
    """
    Load a JSON file and return its contents, with logging on success or failure.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"✅ Loaded JSON file: {filepath}")
        return data
    except FileNotFoundError:
        logger.error(f"❌ File not found: {filepath}")
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON decode error in {filepath}: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error loading JSON file {filepath}: {e}")
    return None


def normalize_contract_endpoint(contract: dict) -> dict:
    """
    Normalize a tool contract's endpoint into a single leading-slash path and
    compute a full_endpoint joined to TEMENOS_BASE_URL without duplicated segments.
    """
    base_url = os.getenv("TEMENOS_BASE_URL", "").rstrip("/") + "/"
    parsed = urlparse(base_url)
    last_segment = parsed.path.rstrip("/").split("/")[-1]

    raw = contract.get("endpoint", "").lstrip("/")
    # strip duplicate segment if it matches the base_url’s last path
    if raw.startswith(f"{last_segment}/"):
        raw = raw[len(last_segment) + 1:]

    contract["endpoint"] = f"/{raw}"
    contract["full_endpoint"] = urljoin(base_url, raw)
    return contract


def load_tool_contracts_from_folder(contract_folder: str):
    """
    Load all JSON tool-contracts from a folder, normalize their endpoints,
    and attach request/response schemas when available.
    """
    tool_contracts = {}
    contract_folder_path = Path(contract_folder).resolve()
    project_root = contract_folder_path.parent.parent.resolve()

    if not contract_folder_path.is_dir():
        logger.error(f"❌ Contract folder does not exist or is not a directory: {contract_folder_path}")
        return tool_contracts

    for filename in os.listdir(contract_folder_path):
        if not filename.endswith(".json"):
            continue

        # load the contract JSON
        filepath = os.path.join(str(contract_folder_path), filename)
        content = load_json_file(filepath)
        if content is None:
            continue

        # normalize its endpoint
        content = normalize_contract_endpoint(content)

        # attach request/response schemas regardless of os.path.exists
        json_schema = content.get("json_schema")
        if isinstance(json_schema, dict):
            # request schema
            req_path = json_schema.get("request")
            if req_path:
                full_req = os.path.join(str(project_root), req_path)
                req_data = load_json_file(full_req)
                if req_data is not None:
                    content["request_schema"] = req_data
                else:
                    logger.warning(f"⚠️ Request schema not found or invalid: {full_req}")
            # response schema
            resp_path = json_schema.get("response")
            if resp_path:
                full_resp = os.path.join(str(project_root), resp_path)
                resp_data = load_json_file(full_resp)
                if resp_data is not None:
                    content["response_schema"] = resp_data
                else:
                    logger.warning(f"⚠️ Response schema not found or invalid: {full_resp}")

        # honor an in-file "tool_name", else use filename
        tool_name = content.get("tool_name", filename[:-5])
        tool_contracts[tool_name] = content
        logger.info(f"🔌 Loaded tool contract: {tool_name}")

    return tool_contracts
