import json
from pathlib import Path
from uuid import uuid4
from core.utils import load_tool_contracts_from_folder
from core.llm import call_gemma3

TOOL_CONTRACT_DIR = Path("schema/tool_contract")
tool_contracts = load_tool_contracts_from_folder(TOOL_CONTRACT_DIR)

def generate_reasoned_plan(goal, objective, expected_outcome, memory):
    session_id = str(uuid4())
    prompt = f"""
You are a smart planning agent for a banking assistant.

Based on the user's goal and available tools, determine:
- the best tool(s) to use (possibly more than one),
- what parameters are required for each,
- which ones are already available from memory,
- and which are missing that need to be asked.

Reuse values from previously filled parameters (memory), if relevant.

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

Respond in this strict JSON format:
{{
  "goal": "<restated goal>",
  "fallback_response": "<polite question if anything is missing>",
  "tool_chain": [
    {{
      "tool": "<tool_name>",
      "inputs": {{ "<param1>": "<value>" }}
    }}
  ]
}}
"""

    llm_response = call_gemma3(prompt)
    print("🧼 [DEBUG] Cleaning LLM response...")
    cleaned = llm_response.strip().removeprefix("```json").removesuffix("```").strip()
    print(f"📋 [DEBUG] Cleaned LLM Response:\n {cleaned}")
    parsed = json.loads(cleaned)

    plan = parsed.get("tool_chain", [])
    missing = []

    for step in plan:
        tool = step["tool"]
        inputs = step.get("inputs", {})
        contract = tool_contracts.get(tool, {})

        # Separate params to send in API vs local filtering
        required_params = contract.get("required_inputs", [])
        optional_params = contract.get("optional_inputs", [])

        allowed_api_params = set(required_params)
        allowed_api_params.update(
            opt.get("name") for opt in optional_params if opt.get("send_to_api", True)
        )

        api_inputs = {k: v for k, v in inputs.items() if k in allowed_api_params}
        local_filters = {k: v for k, v in inputs.items() if k not in allowed_api_params}

        step["api_inputs"] = api_inputs
        step["local_filters"] = local_filters

        # Check missing required params that must be sent to API
        missing.extend([r for r in required_params if not api_inputs.get(r)])

        print(f"[DEBUG] API inputs for tool {tool}: {api_inputs}")
        print(f"[DEBUG] Local filters for tool {tool}: {local_filters}")

    return {
        "plan": plan,
        "next_action": "ask_user" if missing else "respond_with_result",
        "final_summary": None,
        "raw_result": None,
        "is_final": not missing,
        "memory_passed": memory,
        "session_id": session_id,
        "missing": missing,
        "fallback_response": parsed.get("fallback_response", "Could you please provide the missing information?")
    }

def plan(goal, objective, expected_outcome, memory):
    result = generate_reasoned_plan(goal, objective, expected_outcome, memory)
    return result["plan"], result.get("missing", [])
