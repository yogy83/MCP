import logging
from pathlib import Path
from tools.run_tool import run_tool
from core.utils import load_tool_contracts_from_folder

logger = logging.getLogger(__name__)
TOOL_CONTRACT_DIR = Path("schema/tool_contract")
TOOL_CONTRACTS = load_tool_contracts_from_folder(TOOL_CONTRACT_DIR)

# Helper: normalize and search best match if planner returns wrong tool name
def resolve_tool_name(requested_name: str) -> str:
    if requested_name in TOOL_CONTRACTS:
        return requested_name

    requested_lower = requested_name.lower().strip()
    for name in TOOL_CONTRACTS:
        if name.lower() == requested_lower:
            return name
        if name.lower().endswith(requested_lower):
            return name
        if requested_lower in name.lower():
            return name

    logger.warning(f"⚠️ No match found for tool name: {requested_name}")
    return None

def execute_plan(plan):
    results = {}

    for idx, step in enumerate(plan):
        raw_tool_name = step.get("tool")
        step_key = f"step{idx+1}"

        resolved_tool_name = resolve_tool_name(raw_tool_name)
        if not resolved_tool_name:
            logger.error(f"❌ Tool contract not found for tool: {raw_tool_name}")
            raise ValueError(f"Tool contract not found for tool: {raw_tool_name}")

        logger.debug(f"🔧 [PLAN] Running {step_key} → resolved tool: {resolved_tool_name}")

        tool_contract = TOOL_CONTRACTS[resolved_tool_name]
        logger.debug(f"📄 Loaded contract for {resolved_tool_name}")
        logger.debug(f"🔗 Endpoint: {tool_contract.get('endpoint')}")
        logger.debug(f"📥 Required Inputs: {tool_contract.get('required_inputs')}")
        logger.debug(f"🔎 Filtering Rules: {tool_contract.get('filtering_rules')}")

        inputs = step.get("inputs", {})
        logger.debug(f"⚙️ Executing {resolved_tool_name} with inputs: {inputs}")

        try:
            response = run_tool(
                tool_contract,
                inputs,
                request_schema=tool_contract.get("request_schema"),
                response_schema=tool_contract.get("response_schema")
            )
            logger.debug(f"✅ Response from {resolved_tool_name}: {response}")
        except Exception as e:
            logger.error(f"🚨 Error executing {resolved_tool_name}: {e}")
            raise

        results[step_key] = response

    return results
