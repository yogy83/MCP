from typing import Dict, Any, List
from core.executioner import execute_plan
from core.aggregator import aggregate
from core import planner
import copy

SESSION_STORE: Dict[str, Dict[str, Any]] = {}

def extract_values_from_result(result: Dict[str, Any], key: str) -> List[Any]:
    """
    Extract values from tool result that can be used for next step inputs.
    For example, extract all 'account' or 'accountId' values.
    """
    extracted = []
    # result may contain 'result' key or direct list of dicts
    data_list = []
    if isinstance(result, dict):
        if "result" in result:
            data_list = result["result"]
        elif isinstance(result, list):
            data_list = result
    elif isinstance(result, list):
        data_list = result

    for item in data_list:
        # try common keys
        for candidate_key in ["account", "accountId", "arrangementId"]:
            if candidate_key in item:
                extracted.append(item[candidate_key])
                break
    return extracted

def replace_placeholders(inputs: Dict[str, Any], replacements: Dict[str, Any]) -> Dict[str, Any]:
    """
    Replace placeholders like "<will be populated>" with actual values from replacements.
    """
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
        # Handle user follow-up providing missing input
        missing_param = last_response["missing"][0]
        memory[missing_param] = input_contract.get("goal", "").strip()

        goal = session_context.get("original_goal") or input_contract.get("goal", "")
        objective = session_context.get("original_objective") or input_contract.get("objective", "")
        expected_outcome = session_context.get("original_expected_outcome") or input_contract.get("expected_outcome", "")
    else:
        # First interaction in the session
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

        # Inject known memory values initially
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

        # Now execute plan step by step, chaining outputs to next step inputs
        all_results = {}
        for i, step in enumerate(plan_steps):
            # Before executing, replace placeholders in inputs with previous outputs
            if i > 0:
                prev_step_result = all_results.get(f"step{i}", {})
                # Extract possible keys to replace placeholders
                replacements = {}
                extracted_accounts = extract_values_from_result(prev_step_result, "accountId")
                if extracted_accounts:
                    # If multiple, you may want to loop or pick the first for now
                    replacements["willbepopulated"] = extracted_accounts[0]

                step["inputs"] = replace_placeholders(step.get("inputs", {}), replacements)

            # Execute the step
            result = execute_plan([step])
            all_results[f"step{i+1}"] = result.get("step1", {})

        # Enrich each step with its result
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
