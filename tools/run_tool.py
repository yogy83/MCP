# tools/run_tool.py

import requests
import logging
from datetime import datetime
from dateutil.parser import parse as _flexible_parse
from rapidfuzz import fuzz
from config.config import TEMENOS_BASE_URL, build_auth_headers

logger = logging.getLogger(__name__)
print("🔎 Loaded tools/run_tool.py from:", __file__)
logger.warning("🚨 MCP DEBUG: ACTIVE run_tool.py path = %s", __file__)


def call_api(endpoint: str, path_params: dict, query_params: dict) -> dict:
    url = TEMENOS_BASE_URL + endpoint.format(**path_params)
    logger.debug(f"🌍 [DEBUG] Calling URL: {url} with params {query_params}")
    headers = build_auth_headers()
    resp = requests.get(url, params=query_params, headers=headers)
    resp.raise_for_status()
    return resp.json()


def _parse_date(raw: str, fmt: str = None):
    logger.warning("[DIAGNOSTIC] _parse_date: using fallback-aware version ✅")
    try:
        raw_str = str(raw).strip()
        logger.debug(f"[DATE PARSE] Attempting: {raw_str!r} (type={type(raw).__name__}) with format={fmt!r}")

        if fmt:
            try:
                parsed = datetime.strptime(raw_str, fmt).date()
                logger.debug(f"[DATE PARSE] strptime success → {parsed}")
                return parsed
            except Exception as e1:
                logger.warning(f"[WARN] strptime failed: {e1} — falling back to flexible parse")

        parsed = _flexible_parse(raw_str).date()
        logger.debug(f"[DATE PARSE] dateutil success → {parsed}")
        return parsed
    except Exception as final_err:
        logger.error(f"[ERROR] Final date parsing failure: {final_err}")
        raise


def apply_local_filters(response_data: dict, tool_contract: dict, local_filters: dict) -> dict:
    logger.warning("🔥 DIAGNOSTIC: apply_local_filters() executing at runtime ✅")
    logger.warning("🧪 response_data.body type = %s", type(response_data.get("body")))
    logger.warning("🧪 body preview = %r", response_data.get("body"))

    data_list = response_data.get("body", []) or []
    if not isinstance(data_list, list):
        raise TypeError("Expected 'body' in response_data to be a list.")

    rules = tool_contract.get("filtering_rules", [])

    for rule in rules:
        param = rule["input_param"]
        if param not in local_filters:
            continue

        field = rule["response_field"]
        ftype = rule["filter_type"]
        raw_value = local_filters[param]
        threshold = rule.get("threshold", 70)
        method = rule.get("method", "partial")
        tolerance = rule.get("tolerance", 0.2)
        date_fmt = rule.get("date_format")

        if ftype == "exact":
            data_list = [
                item for item in data_list
                if str(item.get(field, "") or "").lower() == str(raw_value).lower()
            ]

        elif ftype == "substring":
            data_list = [
                item for item in data_list
                if str(raw_value).lower() in str(item.get(field, "") or "").lower()
            ]

        elif ftype == "fuzzy_substring":
            q = str(raw_value or "").lower()
            filtered = []
            for item in data_list:
                text = str(item.get(field, "") or "").lower()
                score = (
                    fuzz.ratio(q, text) if method == "ratio"
                    else fuzz.token_sort_ratio(q, text) if method == "token_sort"
                    else fuzz.partial_ratio(q, text)
                )
                if score >= threshold:
                    filtered.append(item)
            data_list = filtered

        elif ftype == "numerical_fuzzy":
            try:
                target = float(raw_value)
            except Exception:
                continue

            data_list = [
                item for item in data_list
                if isinstance(item.get(field), (int, float, str)) and
                abs(float(item[field]) - target) / max(abs(target), 1) <= tolerance
            ]

        elif ftype in ("date_from", "date_to"):
            try:
                cmp_date = _parse_date(raw_value, date_fmt)
            except Exception:
                continue

            filtered = []
            for item in data_list:
                raw_item = item.get(field, "")
                try:
                    d = _parse_date(raw_item, date_fmt)
                    if (ftype == "date_from" and d >= cmp_date) or \
                       (ftype == "date_to" and d <= cmp_date):
                        filtered.append(item)
                except Exception:
                    continue
            data_list = filtered

        else:
            logger.warning(f"[WARN] Unknown filter type: {ftype}")

    return {"body": data_list}


def run_tool(tool_contract: dict, inputs: dict) -> dict:
    try:
        path_params = {k: inputs[k] for k in tool_contract["required_inputs"]}
    except KeyError as e:
        raise ValueError(f"Required input missing: {e}")

    opt_sendable = {
        p["name"]
        for p in tool_contract.get("optional_inputs", [])
        if p.get("send_to_api", False)
    }
    query_params = {k: v for k, v in inputs.items() if k in opt_sendable}

    raw = call_api(tool_contract["endpoint"], path_params, query_params)
    return apply_local_filters(raw, tool_contract, inputs)
