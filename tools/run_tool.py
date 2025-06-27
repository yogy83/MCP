import logging
from datetime import datetime

import requests
from dateutil.parser import parse as _flexible_parse
from jsonschema import validate, ValidationError
from rapidfuzz import fuzz


from config.config import build_auth_headers, TEMENOS_BASE_URL

logger = logging.getLogger(__name__)
print("🔎 Loaded tools/run_tool.py from:", __file__)
logger.warning("🚨 MCP DEBUG: ACTIVE run_tool.py path = %s", __file__)


def call_api(endpoint: str, path_params: dict, query_params: dict) -> dict:
    """
    endpoint: a relative path like "/v1.0.0/.../{accountId}/transactions"
              or a full URL starting with http(s).
    """
    formatted = endpoint.format(**path_params)

    # always prefix the single source-of-truth base URL
    if formatted.lower().startswith("http"):
        url = formatted
    else:
        url = f"{TEMENOS_BASE_URL.rstrip('/')}{formatted}"

    logger.debug(f"🌍 [DEBUG] Calling URL: {url} with params {query_params}")
    headers = build_auth_headers()
    resp = requests.get(url, params=query_params, headers=headers)
    resp.raise_for_status()
    return resp.json()


def _parse_date(raw: str, fmt: str = None):
    logger.warning("[DIAGNOSTIC] _parse_date: using fallback-aware version ✅")
    raw_str = str(raw).strip()
    logger.debug(f"[DATE PARSE] Attempting: {raw_str!r} with format={fmt!r}")

    if fmt:
        try:
            return datetime.strptime(raw_str, fmt).date()
        except Exception:
            logger.warning("[WARN] strptime failed — falling back")

    return _flexible_parse(raw_str).date()


def get_nested_value(obj, path: str):
    parts = path.replace("[]", "").split(".")
    for part in parts:
        if isinstance(obj, list):
            obj = obj[0] if obj else {}
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def apply_local_filters(response_data: dict, tool_contract: dict, local_filters: dict) -> dict:
    # Step 1: Defensive load of data_list
    data_list = []
    if isinstance(response_data, dict):
        maybe_body = response_data.get("body", [])
        if isinstance(maybe_body, list):
            data_list = [item for item in maybe_body if isinstance(item, dict)]
        elif isinstance(maybe_body, dict):
            data_list = [maybe_body]
        else:
            data_list = []
    elif isinstance(response_data, list):
        data_list = [item for item in response_data if isinstance(item, dict)]

    rules = tool_contract.get("filtering_rules", [])
    filtered = data_list

    for rule in rules:
        param = rule["input_param"]
        if param not in local_filters:
            continue

        raw_value = local_filters[param]
        field     = rule["response_field"]
        ftype     = rule["filter_type"]
        threshold = rule.get("threshold", 70)
        method    = rule.get("method", "partial")
        tolerance = rule.get("tolerance", 0.2)
        date_fmt  = rule.get("date_format")
        case_sens = rule.get("case_sensitive", False)

        def norm(v):
            if v is None:
                return ""
            return v if case_sens else str(v).lower()

        if ftype == "exact":
            filtered = [
                item for item in filtered
                if norm(get_nested_value(item, field)) == norm(raw_value)
            ]

        elif ftype == "substring":
            q = norm(raw_value)
            filtered = [
                item for item in filtered
                if q in norm(get_nested_value(item, field))
            ]

        elif ftype == "fuzzy_substring":
            q = norm(raw_value)
            temp = []
            for item in filtered:
                text = norm(get_nested_value(item, field))
                scorer = {
                    "ratio": fuzz.ratio,
                    "token_sort": fuzz.token_sort_ratio
                }.get(method, fuzz.partial_ratio)
                if scorer(q, text) >= threshold:
                    temp.append(item)
            filtered = temp

        elif ftype == "numerical_fuzzy":
            try:
                target = float(raw_value)
            except Exception:
                continue
            temp = []
            for item in filtered:
                val = get_nested_value(item, field)
                try:
                    num = float(val)
                except Exception:
                    continue
                if abs(num - target) / max(abs(target), 1) <= tolerance:
                    temp.append(item)
            filtered = temp

        elif ftype in ("date_from", "date_to"):
            try:
                cmpd = _parse_date(raw_value, date_fmt)
            except Exception:
                continue
            temp = []
            for item in filtered:
                raw_item = get_nested_value(item, field)
                try:
                    d = _parse_date(raw_item, date_fmt)
                    if (ftype == "date_from" and d >= cmpd) or (ftype == "date_to" and d <= cmpd):
                        temp.append(item)
                except Exception:
                    continue
            filtered = temp

        else:
            logger.warning(f"[WARN] Unknown filter type: {ftype}")

    logger.debug(f"[FILTER] Filtered data count: {len(filtered)}")
    return {"body": filtered}


def run_tool(
    tool_contract: dict,
    inputs: dict,
    request_schema: dict = None,
    response_schema: dict = None
) -> dict:
    # 1) Validate inputs
    if request_schema:
        validate(instance=inputs, schema=request_schema)

    # 2) Path vs. query
    try:
        path_params = {k: inputs[k] for k in tool_contract.get("required_inputs", [])}
    except KeyError as e:
        raise ValueError(f"Required input missing: {e}")

    opt_sendable = {
        p["name"]
        for p in tool_contract.get("optional_inputs", [])
        if p.get("send_to_api", False)
    }
    query_params = {k: v for k, v in inputs.items() if k in opt_sendable}

    # 3) Fetch data
    raw_resp = call_api(tool_contract["endpoint"], path_params, query_params)

    # 4) Validate response
    if response_schema:
        # validate(instance=raw_resp, schema=response_schema)
        pass

    # 5) Apply filters
    filtered = apply_local_filters(raw_resp, tool_contract, inputs)
    return filtered if filtered["body"] else raw_resp
