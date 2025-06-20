from typing import Dict, Any, List
from core.executioner import execute_plan
from core.aggregator import aggregate
from core import planner
import json
import copy

SESSION_STORE: Dict[str, Dict[str, Any]] = {}

def extract_values_from_result(result: Dict[str, Any], key: str) -> List[Any]:
    extracted = []
    data_list = []

    if isinstance(result, dict) and "result" in result:
        value = result["result"]
        if isinstance(value, list):
            data_list = value
        elif isinstance(value, dict):
            data_list = [value]  # ✅ wrap single dict
        else:
            print(f"⚠️ Unexpected format inside 'result': {type(value)}")
    elif isinstance(result, list):
        data_list = result
    elif isinstance(result, dict):  # fallback if 'result' missing but structure exists
        data_list = [result]
    else:
        print(f"⚠️ Unexpected top-level result format: {type(result)}")

    for item in data_list:
        if isinstance(item, dict):
            for candidate_key in ["account", "accountId", "arrangementId"]:
                if candidate_key in item:
                    extracted.append(item[candidate_key])
                    break
        else:
            print(f"⚠️ Skipping non-dict item in result list: {item}")

    return extracted

def replace_placeholders(inputs: Dict[str, Any], replacements: Dict[str, Any]) -> Dict[str, Any]:
    new_inputs = copy.deepcopy(inputs)
    for k, v in new_inputs.items():
        if isinstance(v, str) and v.strip().startswith("<") and v.strip().endswith(">"):
            key = v.strip("<>").replace(" ", "")
            if key in replacements:
                new_inputs[k] = replacements[key]
    return new_inputs

def process_user_request(input_contract: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    session_context = SESSION_STORE.setdefault(session_id, {
        "memory": {},
        "last_response": {},
        "original_goal": None,
        "original_objective": None,
        "original_expected_outcome": None,
    })

    last_response = session_context.get("last_response", {})
    memory = session_context.get("memory", {})

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
        plan_steps, missing = planner.plan(goal, objective, expected_outcome, memory)

        for step in plan_steps:
            for key, val in memory.items():
                step.setdefault("inputs", {}).setdefault(key, val)

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
                        print(f"❌ Failed to parse string JSON from {step_key}")
                        prev_step_result = {}

                replacements = {}
                extracted_accounts = extract_values_from_result(prev_step_result, "accountId")
                if extracted_accounts:
                    replacements["willbepopulated"] = extracted_accounts[0]
                print(f"🔄 Placeholder replacements for {step_key}: {replacements}")
                step["inputs"] = replace_placeholders(step.get("inputs", {}), replacements)

            print(f"⚙️ Running {step_key}: {step['tool']} with inputs {step['inputs']}")
            result = execute_plan([step])

            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    print(f"❌ Failed to parse result from execute_plan at {step_key}")
                    result = {}

            print(f"📦 Raw result of {step_key}: {result}")
            print(f"📦 Type of result: {type(result)}")

            if isinstance(result, dict):
                all_results[step_key] = result.get(step_key, result)
            else:
                print(f"❗ Unexpected result format at {step_key}. Defaulting to empty.")
                all_results[step_key] = {}

        enriched_steps = [
            {**step, "result": all_results.get(f"step{i+1}", {})}
            for i, step in enumerate(plan_steps)
        ]

        summary_obj = aggregate(tool_outputs=enriched_steps, expected_outcome=expected_outcome)

        print(f"✅ [MCP] Final Summary:\n{summary_obj.get('summary')}")

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
        print(f"❌ [MCP ERROR] Planner failure: {e}")
        return {
            "status": "error",
            "message": f"Planner failure: {e}",
            "session_id": session_id
        }

    session_context["last_response"] = response
    SESSION_STORE[session_id] = session_context

    return response
