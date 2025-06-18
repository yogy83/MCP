import os
import json
current_dir = os.path.dirname(__file__)

def load_tool_contracts_from_folder(contract_folder):
    tool_contracts = {}
    for filename in os.listdir(contract_folder):
        if filename.endswith(".json"):
            filepath = os.path.join(contract_folder, filename)
            try:
                with open(filepath, "r") as f:
                    content = json.load(f)
                    tool_name = content.get("tool_name", filename.replace(".json", ""))
                    tool_contracts[tool_name] = content
            except Exception as e:
                print(f"❌ [ERROR] Failed to load {filename}: {e}")
    return tool_contracts

# Ensure correct folder path for loading tool contracts
CONTRACT_FOLDER = os.path.abspath(os.path.join(current_dir, "..", "schema", "tool_contract"))
OUTPUT_CONTRACT_FOLDER = os.path.abspath(os.path.join(current_dir, "..", "schema", "output_contract"))
tool_schemas = load_tool_contracts_from_folder(CONTRACT_FOLDER)
