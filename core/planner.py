import json
import logging
import re
from pathlib import Path
from uuid import uuid4

from core.utils import load_tool_contracts_from_folder
from core.llm import call_gemma3
from core.executioner import resolve_tool_name

logger = logging.getLogger(__name__)

TOOL_REGISTRY_PATH = Path("schema/tool_registry_llm.json")
with open(TOOL_REGISTRY_PATH, "r") as f:
    tool_registry_llm = json.load(f)

TOOL_CONTRACT_DIR = Path("schema/tool_contract")
tool_contracts = load_tool_contracts_from_folder(TOOL_CONTRACT_DIR)

PLACEHOLDER_PATTERN = re.compile(r"^<([^>]+)>$")


def resolve_placeholders(inputs: dict, memory: dict, user_inputs: dict) -> dict:
    resolved = {}
    for k, v in inputs.items():
        if isinstance(v, str):
            m = PLACEHOLDER_PATTERN.match(v)
            if m:
                key = m.group(1)
            elif v.isupper() and v in memory:
                key = v
            else:
                key = None

            if key:
                value = memory.get(key, user_inputs.get(key))
                if value is None:
                    logger.warning(f"Placeholder '{v}' for '{k}' could not be resolved.")
                else:
                    logger.debug(f"Resolved placeholder '{v}' for '{k}' → '{value}'")
                resolved[k] = value
            else:
                resolved[k] = v

        elif isinstance(v, dict):
            resolved[k] = resolve_placeholders(v, memory, user_inputs)
        else:
            resolved[k] = v
    return resolved


def is_param_filled(val):
    """True if parameter is present and not a placeholder/blank value."""
    if val is None:
        return False
    if isinstance(val, str):
        v = val.strip()
        return bool(
            v
            and v not in ("...", "", "ACCOUNT_ID", "<ACCOUNT_ID>")
            and not PLACEHOLDER_PATTERN.fullmatch(v)
        )
    return True


def extract_missing_from_plan(plan_steps, tool_contracts):
    """
    Contract-driven: For each plan step, check all required params.
    Return a list of missing params.
    """
    missing = []
    for step in plan_steps:
        tool_name = step.get("tool") or step.get("tool_name")
        normalized = resolve_tool_name(tool_name) or tool_name
        if not normalized or normalized not in tool_contracts:
            continue
        contract = tool_contracts[normalized]
        required = contract.get("required_inputs", [])
        inputs = step.get("inputs", {}) or step.get("api_inputs", {}) or {}
        for param in required:
            val = inputs.get(param)
            if not is_param_filled(val):
                missing.append(param)
    return sorted(set(missing))


def generate_reasoned_plan(
    goal: str,
    objective: str,
    expected_outcome: str,
    memory: dict,
    user_inputs: dict = None
) -> dict:
    if user_inputs is None:
        user_inputs = {}

    prompt = f"""
You are an intelligent planning agent for a banking assistant.

**Your task:** From the tools listed below, select the tool (or sequence) whose *description* and *parameters* best fulfill the user's goal and expected outcome. Use the 'name' exactly as shown.

**Tools:**
{json.dumps(tool_registry_llm, indent=2)}

**User Request Context**
Goal: {goal}
Objective: {objective}
Expected Outcome: {expected_outcome}

**Previously collected parameter values:**  
{json.dumps(memory, indent=2)}

**Instructions:**
- Review all tools. Do NOT assume or hallucinate tool names.
- Match the user's request to the tool whose description and required parameters most closely fit the GOAL and OUTCOME.
- Use available parameter values from memory; do not ask for values that are already present.
- If NO tool fits the user's goal, reply with an appropriate 'fallback_response' explaining why.
- **Output ONLY valid JSON, matching this exact structure:**

{{
  "goal": "<Restate user's goal in your own words>",
  "fallback_response": "<Fallback message if no suitable tool exists, otherwise leave blank>",
  "tool_chain": [
    {{
      "tool": "<EXACT tool name from the list>",
      "inputs": {{ "param1": "...", ... }}
    }}
  ]
}}

Return ONLY the JSON response. Do not add any explanation or non-JSON text.
"""
    logger.debug("[LLM PLANNER PROMPT] >>>\n%s", prompt)
    raw = call_gemma3(prompt)
    print("\n--- LLM RESPONSE ---\n", raw, "\n--- END RESPONSE ---\n")
    cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
    if not cleaned or not cleaned.startswith("{"):
        raise ValueError(f"LLM did not return JSON! Output was: {repr(raw)}")
    parsed = json.loads(cleaned)

    # Normalize the plan and resolve placeholders if needed
    plan_steps = []
    for step in parsed.get("tool_chain", []):
        raw_tool = step.get("tool")
        normalized = resolve_tool_name(raw_tool) or raw_tool
        if normalized == raw_tool:
            logger.warning(f"No normalization found for tool: {raw_tool}, using raw name")

        # Start with stubbed inputs, then inject all user_inputs
        stub_inputs = step.get("inputs", {}) or {}
        for k, v in user_inputs.items():
            stub_inputs.setdefault(k, v)
        resolved_inputs = resolve_placeholders(stub_inputs, memory, user_inputs)

        plan_steps.append({
            "tool": normalized,
            "inputs": resolved_inputs
        })

    # Validate missing params strictly using contract
    missing = extract_missing_from_plan(plan_steps, tool_contracts)

    # If LLM returned no steps or everything is missing, ask user for missing params
    if not plan_steps or missing:
        # Aggregate all missing from all steps if any
        return {
            "plan": plan_steps,
            "next_action": "ask_user",
            "fallback_response": parsed.get("fallback_response")
                                 or "Could you please provide the missing information?",
            "missing": missing,
            "memory_passed": memory,
            "session_id": str(uuid4()),
            "is_final": False,
            "final_summary": None,
            "raw_result": None,
        }

    return {
        "plan": plan_steps,
        "next_action": "respond_with_result",
        "fallback_response": parsed.get("fallback_response") or "",
        "missing": [],
        "memory_passed": memory,
        "session_id": str(uuid4()),
        "is_final": True,
        "final_summary": None,
        "raw_result": None,
    }


def plan(
    goal: str,
    objective: str,
    expected_outcome: str,
    memory: dict,
    user_inputs: dict = None
):
    result = generate_reasoned_plan(goal, objective, expected_outcome, memory, user_inputs)
    # Flatten api_inputs + local_filters into a single 'inputs' dict if present
    final_plan = []
    for step in result["plan"]:
        merged = step.get("inputs", {})
        final_plan.append({
            "tool": step["tool"],
            "inputs": merged
        })
    return final_plan, result["missing"]
