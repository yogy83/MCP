from pathlib import Path
from tools.run_tool import run_tool
from core.utils import load_tool_contracts_from_folder

TOOL_CONTRACT_DIR = Path("schema/tool_contract")
TOOL_CONTRACTS = load_tool_contracts_from_folder(TOOL_CONTRACT_DIR)

def execute_plan(plan):
    results = {}
    for idx, step in enumerate(plan):
        tool_name = step.get("tool")
        step_key = f"step{idx+1}"

        tool_contract = TOOL_CONTRACTS.get(tool_name)
        if not tool_contract:
            raise ValueError(f"Tool contract not found for tool: {tool_name}")

        inputs = step.get("inputs", {})
        response = run_tool(tool_contract, inputs)  # Pass all inputs together
        results[step_key] = response

    return results
