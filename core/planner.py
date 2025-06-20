# core/planner.py

import json
import logging
import re
from pathlib import Path
from uuid import uuid4
from core.utils import load_tool_contracts_from_folder
from core.llm import call_gemma3

logger = logging.getLogger(__name__)

TOOL_CONTRACT_DIR = Path("schema/tool_contract")
tool_contracts = load_tool_contracts_from_folder(TOOL_CONTRACT_DIR)

PLACEHOLDER_PATTERN = re.compile(r"^<([^>]+)>$")

def resolve_placeholders(inputs: dict, memory: dict, user_inputs: dict) -> dict:
    """
    Recursively replace placeholders of the form '<key>' in inputs with actual values
    from memory or user_inputs dictionaries.
    """
    resolved = {}

    for k, v in inputs.items():
        if isinstance(v, str):
            match = PLACEHOLDER_PATTERN.match(v)
            if match:
                key = match.group(1)
                value = memory.get(key)
                if value is None:
                    value = user_inputs.get(key)
                if value is None:
                    logger.warning(f"Placeholder '{v}' for key '{k}' could not be resolved.")
                else:
                    logger.debug(f"Resolved placeholder '{v}' for key '{k}' to '{value}'.")
                resolved[k] = value
            else:
                resolved[k] = v
        elif isinstance(v, dict):
            resolved[k] = resolve_placeholders(v, memory, user_inputs)
        else:
            resolved[k] = v

    return resolved


def generate_reasoned_plan(
    goal: str,
    objective: str,
    expected_outcome: str,
    memory: dict,
    user_inputs: dict = None
) -> dict:
    if user_inputs is None:
        user_inputs = {}

    # 1) Prompt the LLM for a plan
    prompt = f"""
You are a smart planning agent for a banking assistant.

Based on the user's goal and available tools, determine:
- the best tool(s) to use,
- which parameters are required for each,
- which ones come from memory,
- and which are missing.

Tools available:
{json.dumps(tool_contracts, indent=2)}

Goal:
{goal}
Objective:
{objective}
Expected Outcome:
{expected_outcome}

Previously collected parameter values (if any):
{json.dumps(memory, indent=2)}

Respond strictly in JSON:
{{
  "goal": "<restated>",
  "fallback_response": "<fallback>",
  "tool_chain": [
    {{
      "tool": "<tool_name>",
      "inputs": {{ ... }}
    }}
  ]
}}
"""
    raw = call_gemma3(prompt)
    cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
    parsed = json.loads(cleaned)
    plan = parsed.get("tool_chain", [])
    missing = []

    # Build the set of all local-only keys from the current contracts
    local_only_keys = {
        opt["name"]
        for contract in tool_contracts.values()
        for opt in contract.get("optional_inputs", [])
        if not opt.get("send_to_api", False)
    }

    for step in plan:
        tool     = step["tool"]
        contract = tool_contracts.get(tool, {})

        # Required inputs and sendable optional inputs
        required    = contract.get("required_inputs", [])
        api_allowed = set(required) | {
            opt["name"]
            for opt in contract.get("optional_inputs", [])
            if opt.get("send_to_api", False)
        }

        # Ensure we have an inputs dict
        step_inputs = step.setdefault("inputs", {})

        # Inject any user_inputs whose key is a known local-only filter
        for key in local_only_keys:
            if key in user_inputs and key not in step_inputs:
                step_inputs[key] = user_inputs[key]

        # After fully injecting user_inputs into step_inputs

        resolved_inputs = resolve_placeholders(step_inputs, memory, user_inputs)
        step["inputs"] = resolved_inputs  # update inputs in the plan

        # Split into API inputs vs local filters - OUTSIDE loop
        api_inputs    = {k: v for k, v in resolved_inputs.items() if k in api_allowed}
        local_filters = {k: v for k, v in resolved_inputs.items() if k not in api_allowed}

        step["api_inputs"]    = api_inputs
        step["local_filters"] = local_filters

        # Log at debug level
        logger.debug(f"[API INPUTS] tool={tool} → {api_inputs}")
        logger.debug(f"[LOCAL FILTERS] tool={tool} → {local_filters}")

        # Track missing required params
        for req in required:
            if req not in api_inputs or api_inputs.get(req) in (None, ""):
                missing.append(req)

    return {
        "plan": plan,
        "next_action": "ask_user" if missing else "respond_with_result",
        "fallback_response": parsed.get("fallback_response")
                             or "Could you please provide the missing information?",
        "final_summary": None,
        "raw_result": None,
        "is_final": not bool(missing),
        "memory_passed": memory,
        "session_id": str(uuid4()),
        "missing": missing,
    }


def plan(
    goal: str,
    objective: str,
    expected_outcome: str,
    memory: dict,
    user_inputs: dict = None
):
    result = generate_reasoned_plan(
        goal, objective, expected_outcome, memory, user_inputs
    )
    return result["plan"], result["missing"]
