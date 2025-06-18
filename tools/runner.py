import json
import requests
from pathlib import Path
from datetime import datetime
from config.config import TEMENOS_BASE_URL, build_auth_headers

TOOL_CONTRACT_DIR = Path("schema/tool_contract")

def load_json_contract(contract_dir, tool_name):
    path = contract_dir / f"{tool_name}.json"
    if not path.exists():
        return None
    with path.open("r") as f:
        return json.load(f)

def build_url(base_url, endpoint_template, params):
    # Replace path params (e.g., {accountId})
    for key, val in params.items():
        if f"{{{key}}}" in endpoint_template:
            endpoint_template = endpoint_template.replace(f"{{{key}}}", str(val))
    # URL without query params, add query params later
    return f"{base_url}{endpoint_template}"

def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%d %b %Y")
    except Exception:
        return None

def apply_filters(response_data, tool_contract, inputs):
    filtering_rules = tool_contract.get("filtering_rules", [])
    data_list = response_data.get("body", [])
    if not isinstance(data_list, list):
        # Defensive fallback
        print("[WARN] Response body is not a list, skipping filtering.")
        return response_data

    for rule in filtering_rules:
        param = rule["input_param"]
        if param not in inputs:
            continue
        filter_value = inputs[param]
        field = rule["response_field"]
        ftype = rule["filter_type"]

        if ftype == "date_from":
            filter_date = parse_date(filter_value)
            if filter_date is None:
                print(f"[WARN] Could not parse date_from filter value '{filter_value}'")
                continue
            data_list = [
                item for item in data_list
                if item.get(field) and parse_date(item.get(field)) and parse_date(item.get(field)) >= filter_date
            ]
        elif ftype == "date_to":
            filter_date = parse_date(filter_value)
            if filter_date is None:
                print(f"[WARN] Could not parse date_to filter value '{filter_value}'")
                continue
            data_list = [
                item for item in data_list
                if item.get(field) and parse_date(item.get(field)) and parse_date(item.get(field)) <= filter_date
            ]
        elif ftype == "substring":
            data_list = [
                item for item in data_list
                if filter_value.lower() in (item.get(field, "").lower())
            ]

    return {"body": data_list}

def run_tool(tool_name, inputs):
    tool_contract = load_json_contract(TOOL_CONTRACT_DIR, tool_name)
    if not tool_contract:
        return {"error": f"❌ Tool contract not found for '{tool_name}'"}

    required = tool_contract.get("required_inputs", [])
    missing = [r for r in required if r not in inputs or inputs[r] in (None, "")]
    if missing:
        return {"error": f"Missing required params: {', '.join(missing)}"}

    endpoint = tool_contract.get("endpoint")
    base_url = tool_contract.get("base_url", TEMENOS_BASE_URL)
    url = build_url(base_url, endpoint, inputs)
    headers = build_auth_headers()

    try:
        print(f"🌍 [DEBUG] Calling URL: {url}")
        # We do NOT send optional filters as query params (API doesn't accept them)
        # Filters are applied locally on response JSON below.
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"📦 [DEBUG] Response received.")
    except Exception as e:
        return {"error": f"API call failed: {e}"}

    # Apply filtering locally on response
    filtered_data = apply_filters(data, tool_contract, inputs)
    return {"result": filtered_data.get("body", [])}
