import logging
import json
import copy
from typing import Dict, Any, List
from pathlib import Path

from core.executioner import execute_plan
from core.aggregator import aggregate
from core.planner import plan
from core.llm import call_gemma3
from core.utils import load_tool_contracts_from_folder

logger = logging.getLogger(__name__)

# 🔥 Always load tool contracts at the module level, so it's global and fresh!
TOOL_CONTRACT_DIR = Path("schema/tool_contract")
TOOL_CONTRACTS = load_tool_contracts_from_folder(TOOL_CONTRACT_DIR)

SESSION_STORE: Dict[str, Dict[str, Any]] = {}

def extract_values_from_result(result: Dict[str, Any], key: str) -> List[Any]:
    """Extract values for 'account', 'accountId', or 'arrangementId' from a step result."""
    extracted = []
    data_list = []

    if isinstance(result, dict) and "result" in result:
        value = result["result"]
        if isinstance(value, list):
            data_list = value
        elif isinstance(value, dict):
            data_list = [value]
        else:
            logger.warning(f"Unexpected format inside 'result': {type(value)}")
    elif isinstance(result, list):
        data_list = result
    elif isinstance(result, dict):
        data_list = [result]
    else:
        logger.warning(f"Unexpected top-level result format: {type(result)}")

    for item in data_list:
        if isinstance(item, dict):
            for candidate_key in ["account", "accountId", "arrangementId"]:
                if candidate_key in item:
                    extracted.append(item[candidate_key])
                    break
        else:
            logger.warning(f"Skipping non-dict item in result list: {item}")

    return extracted

def replace_placeholders(inputs: Dict[str, Any], replacements: Dict[str, Any]) -> Dict[str, Any]:
    """Replace placeholder strings in the tool step inputs with extracted values."""
    new_inputs = copy.deepcopy(inputs)
    for k, v in new_inputs.items():
        if isinstance(v, str) and v.strip().startswith("<") and v.strip().endswith(">"):
            key = v.strip("<>").replace(" ", "")
            if key in replacements:
                new_inputs[k] = replacements[key]
    return new_inputs

def process_user_request(input_contract: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    """Main MCP session handler."""
    session_context = SESSION_STORE.setdefault(session_id, {
        "memory": {},
        "last_response": {},
        "original_goal": None,
        "original_objective": None,
        "original_expected_outcome": None,
    })

    last_response = session_context.get("last_response", {})
    memory = session_context.get("memory", {})

    # Parameter completion logic (continue or reset plan)
    if last_response.get("is_final") is False and last_response.get("missing"):
        missing_param = last_response["missing"][0]
        memory[missing_param] = input_contract.get("goal", "").strip()
        goal = session_context.get("original_goal") or input_contract.get("goal", "")
        objective = session_context.get("original_objective") or input_contract.get("objective", "")
        expected_outcome = session_context.get("original_expected_outcome") or input_contract.get("expected_outcome", "")
    else:
        goal = input_contract.get("goal", "")
        objective = input_contract.get("objective", "")
        expected_outcome = input_contract.get("expected_outcome", "")
        memory = input_contract.get("parameters", {})
        session_context["original_goal"] = goal
        session_context["original_objective"] = objective
        session_context["original_expected_outcome"] = expected_outcome

    session_context["memory"] = memory

    try:
        plan_steps, missing = plan(goal, objective, expected_outcome, memory)

        # Populate memory for each step, if any values are already known
        for step in plan_steps:
            for key, val in memory.items():
                step.setdefault("inputs", {}).setdefault(key, val)

        # If required params are missing, ask user for more info
        if missing:
            response = {
                "plan": [],
                "next_action": "ask_user",
                "prompt": f"Please provide {missing[0]}",
                "missing": missing,
                "fallback_response": "Could you help me with the required detail?",
                "is_final": False,
                "memory_passed": memory,
                "session_id": session_id
            }
            session_context["last_response"] = response
            SESSION_STORE[session_id] = session_context
            return response

        all_results = {}
        for i, step in enumerate(plan_steps):
            step_key = f"step{i+1}"

            if i > 0:
                prev_step_result = all_results.get(f"step{i}", {})

                if isinstance(prev_step_result, str):
                    try:
                        prev_step_result = json.loads(prev_step_result)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse string JSON from {step_key}")
                        prev_step_result = {}

                replacements = {}
                extracted_accounts = extract_values_from_result(prev_step_result, "accountId")
                if extracted_accounts:
                    replacements["willbepopulated"] = extracted_accounts[0]
                logger.info(f"🔄 Placeholder replacements for {step_key}: {replacements}")
                step["inputs"] = replace_placeholders(step.get("inputs", {}), replacements)

            logger.info(f"⚙️ Running {step_key}: {step['tool']} with inputs {step['inputs']}")
            result = execute_plan([step])

            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse result from execute_plan at {step_key}")
                    result = {}

            logger.info(f"📦 Raw result of {step_key}: {result}")
            logger.info(f"📦 Type of result: {type(result)}")

            if isinstance(result, dict):
                all_results[step_key] = result.get(step_key, result)
            else:
                logger.warning(f"Unexpected result format at {step_key}. Defaulting to empty.")
                all_results[step_key] = {}

        # Attach results to the steps
        enriched_steps = [
            {**step, "result": all_results.get(f"step{i+1}", {})}
            for i, step in enumerate(plan_steps)
        ]

        # ✅ Pass TOOL_CONTRACTS here!
        summary_obj = aggregate(
            tool_outputs=enriched_steps,
            expected_outcome=expected_outcome,
            llm_call=call_gemma3,
            TOOL_CONTRACTS=TOOL_CONTRACTS
        )

        logger.info(f"✅ [MCP] Final Summary:\n{summary_obj.get('summary')}")

        response = {
            "plan": plan_steps,
            "next_action": "respond_with_result",
            "final_summary": summary_obj.get("summary", "No summary available."),
            "raw_result": summary_obj.get("raw_result", {}),
            "raw_text": summary_obj.get("raw_text", {}),
            "is_final": True,
            "memory_passed": memory,
            "session_id": session_id
        }

    except Exception as e:
        logger.error(f"[MCP ERROR] Planner failure: {e}")
        return {
            "status": "error",
            "message": f"Planner failure: {e}",
            "session_id": session_id
        }

    session_context["last_response"] = response
    SESSION_STORE[session_id] = session_context

    return response
