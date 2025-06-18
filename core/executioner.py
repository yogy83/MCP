# core/executioner.py
from pathlib import Path
from tools.runner import run_tool

TOOL_CONTRACT_DIR = Path("schema/tool_contract")

def execute_plan(plan):
    results = {}
    for idx, step in enumerate(plan):
        tool = step.get("tool")
        inputs = step.get("inputs", {})
        step_key = f"step{idx+1}"

        response = run_tool(tool, inputs)
        results[step_key] = response

    return results
