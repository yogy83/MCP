import json
import re
import logging
from typing import Any, Callable, Dict, List

# Load your tool contracts however you do in your project
# For this snippet, pass TOOL_CONTRACTS to the aggregate() function
# Example: TOOL_CONTRACTS = load_tool_contracts_from_folder(...)

logger = logging.getLogger(__name__)

def clean(text: str) -> str:
    """Remove code block markers and extra whitespace from LLM output."""
    return re.sub(r"```(?:json|text)?", "", text, flags=re.IGNORECASE).strip()

def extract_error(result: dict) -> str:
    """Extract error message if present."""
    if not isinstance(result, dict):
        return ""
    if 'error' in result:
        if isinstance(result['error'], dict):
            return result['error'].get('message', str(result['error']))
        return str(result['error'])
    # Sometimes error is in header or status
    if result.get("header", {}).get("status", "").lower() == "failed":
        err = result.get("error", {}).get("message") or result.get("error", {})
        return f"Error: {err}"
    return ""

def is_no_data(result: dict, tool_contract: dict = None) -> bool:
    """
    Detect if a tool result contains no data, using tool_contract for the main data key.
    """
    if not isinstance(result, dict) or not result:
        return True

    response_data_key = None
    # Try to get the main data key from the tool contract
    if tool_contract:
        response_data_key = tool_contract.get("response_data_key")
        # Try to infer if not explicitly set (optional)
        if not response_data_key and "response_schema" in tool_contract:
            for k in ("body", "data", "results", "items", "accounts", "transactions"):
                if k in tool_contract["response_schema"].get("properties", {}):
                    response_data_key = k
                    break
    if not response_data_key:
        response_data_key = "body"  # Sensible fallback

    val = result.get(response_data_key)
    if isinstance(val, list) and len(val) == 0:
        return True
    if isinstance(val, dict) and not val:
        return True

    return False

def make_key(tool: str, api_inputs: Dict[str, Any]) -> str:
    # Use tool name and ordered params to make a predictable key
    sanitized = "_".join(
        f"{k}_{str(v).replace(' ', '_')}"
        for k, v in sorted(api_inputs.items())
    )
    key = f"{tool}_{sanitized}".strip("_")
    # Remove duplicate underscores, spaces, and non-alphanum (except _)
    return re.sub(r'[^a-zA-Z0-9_]', '', key)

def summarize_step(
    step_id: str,
    step_result: dict,
    local_filters: dict,
    llm_call: Callable[[str], str],
    tool_contract: dict = None
) -> str:
    """
    Summarize the result of a tool step, handling empty results and errors before calling LLM.
    Pass the tool_contract for correct no-data detection.
    """
    error_msg = extract_error(step_result)
    if error_msg:
        return f"{error_msg}"
    if is_no_data(step_result, tool_contract=tool_contract):
        return "No data found for this query."
    filters_desc = f" Filters applied locally: {json.dumps(local_filters)}." if local_filters else ""
    step_prompt = (
        f"You are a banking assistant. Summarize the result below for step {step_id} in 1-2 lines in plain English."
        f"{filters_desc}\n\n"
        f"{json.dumps(step_result, indent=2)}\n\n"
        "Avoid technical jargon. Keep it simple."
    )
    try:
        response = llm_call(step_prompt)
        return clean(response)
    except Exception as e:
        logger.error(f"Error summarizing step {step_id}: {e}")
        return "Summary unavailable."

def aggregate(
    tool_outputs: List[dict],
    expected_outcome: str,
    llm_call: Callable[[str], str],
    TOOL_CONTRACTS: Dict[str, dict]
) -> dict:
    """
    Aggregate multiple tool outputs and return a summary with details.
    TOOL_CONTRACTS: dict mapping tool name to its contract, must have 'response_data_key'.
    """
    result_summary = {}
    result_texts = {}
    pretty_steps = []

    for i, step in enumerate(tool_outputs):
        tool = step.get("tool", "unknown_tool")
        api_inputs = step.get("api_inputs", {})
        local_filters = step.get("local_filters", {})
        output = step.get("result", {})

        tool_contract = TOOL_CONTRACTS.get(tool)
        key = make_key(tool, api_inputs)
        summary = summarize_step(
            f"Step {i+1}",
            output,
            local_filters,
            llm_call=llm_call,
            tool_contract=tool_contract
        )
        result_summary.setdefault(tool, {})[f"step{i+1}"] = output
        result_texts.setdefault(tool, {})[f"step{i+1}"] = summary
        pretty_steps.append(f"{key}: {summary}")

        logger.info(f"[Aggregator] Step {i+1} - {key}: {summary}")

    # Final summary using LLM, but provide fallback if LLM fails
    full_context = "\n".join(pretty_steps)
    prompt = (
        f"You are an aggregator providing a response to a MCP requestor, who is usually an AI agent.\n"
        f"Based on the following tool outputs:\n\n"
        f"{full_context}\n\n"
        f"Please summarize the information in 2 concise and friendly sentences aligned with this goal: {expected_outcome}.\n"
        f"Focus on being clear and informative, and mention if any local filtering was applied.\n"
        f"Do not ask for further inputs or mention uploading documents."
    )
    try:
        final_summary = llm_call(prompt).strip()
    except Exception as e:
        logger.error(f"Error generating final summary: {e}")
        final_summary = "Summary unavailable."

    return {
        "summary": final_summary,
        "steps": pretty_steps,  # For easy frontend rendering
        "raw_result": result_summary,
        "raw_text": result_texts
    }
