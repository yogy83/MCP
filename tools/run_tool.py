import requests
from datetime import datetime
from dateutil.parser import parse as parse_date
from rapidfuzz import fuzz
import logging

try:
    from config.config import BASE_URL
except ImportError:
    BASE_URL = ""


# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def call_api(endpoint: str, path_params: dict, query_params: dict) -> dict:
    """
    Invoke the external API and return the parsed JSON response.
    """
    url = BASE_URL + endpoint.format(**path_params)
    logger.debug(f"Calling API: {url} with params {query_params}")
    response = requests.get(url, params=query_params)
    response.raise_for_status()
    return response.json()


def apply_local_filters(response_data: dict, tool_contract: dict, local_filters: dict) -> dict:
    """
    Apply data-driven filters defined in the JSON tool contract to the API response.
    """
    rules = tool_contract.get("filtering_rules", [])
    filtered = response_data.get("body", [])
    logger.info(f"Starting filtering: {len(filtered)} records")

    for rule in rules:
        param = rule.get("input_param")
        if param not in local_filters:
            continue

        field = rule.get("response_field")
        ftype = rule.get("filter_type")
        value = local_filters[param]
        threshold = rule.get("threshold")
        tolerance = rule.get("tolerance")
        method = rule.get("method", "partial")
        date_format = rule.get("date_format")

        temp = []

        if ftype in ("date_from", "date_to"):
            try:
                cmp_date = datetime.strptime(value, date_format).date() if date_format else parse_date(value).date()
            except Exception as e:
                logger.warning(f"Unable to parse filter date '{value}': {e}")
                continue

            def keep_date(item):
                raw = item.get(field, "")
                try:
                    d = datetime.strptime(raw, date_format).date() if date_format else parse_date(raw).date()
                except Exception:
                    return False
                return (d >= cmp_date) if ftype == "date_from" else (d <= cmp_date)

            temp = [itm for itm in filtered if keep_date(itm)]

        elif ftype == "exact":
            case_sensitive = rule.get("case_sensitive", False)
            for itm in filtered:
                target = itm.get(field)
                if target is None:
                    continue
                if case_sensitive:
                    match = str(target) == str(value)
                else:
                    match = str(target).lower() == str(value).lower()
                if match:
                    temp.append(itm)

        elif ftype == "substring":
            q = str(value or "").lower()
            for itm in filtered:
                txt = str(itm.get(field, "") or "").lower()
                if q in txt:
                    temp.append(itm)

        elif ftype == "fuzzy_substring":
            thr = threshold if threshold is not None else 70
            q = str(value or "").lower()
            for itm in filtered:
                txt = str(itm.get(field, "") or "").lower()
                if method == "ratio":
                    score = fuzz.ratio(q, txt)
                elif method == "token_sort":
                    score = fuzz.token_sort_ratio(q, txt)
                else:
                    score = fuzz.partial_ratio(q, txt)
                logger.debug(f"[FUZZY] {field}: '{q}' vs '{txt}' -> {score}")
                if score >= thr:
                    temp.append(itm)

        elif ftype == "numerical_fuzzy":
            tol = tolerance if tolerance is not None else 0.2
            try:
                target = float(value)
            except Exception:
                continue
            for itm in filtered:
                try:
                    val = float(itm.get(field, 0))
                except Exception:
                    continue
                rel = abs(val - target) / max(abs(target), 1)
                if rel <= tol:
                    temp.append(itm)

        else:
            logger.warning(f"Unknown filter type: {ftype}")
            temp = filtered

        filtered = temp
        logger.info(f"After '{ftype}', {len(filtered)} records remain")

    return {"body": filtered}


def run_tool(tool_contract: dict, inputs: dict) -> dict:
    """
    Main entry: calls the API based on required_inputs, applies optional local filters, and returns filtered data.
    """
    api_params = {}
    local_filters = {}

    for inp in tool_contract.get("optional_inputs", []):
        name = inp.get("name")
        if name in inputs:
            if inp.get("send_to_api", False):
                api_params[name] = inputs[name]
            else:
                local_filters[name] = inputs[name]

    for name in tool_contract.get("required_inputs", []):
        api_params[name] = inputs[name]

    raw = call_api(tool_contract.get("endpoint"), api_params, api_params)
    return apply_local_filters(raw, tool_contract, local_filters)
