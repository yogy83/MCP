
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))



import json
from pathlib import Path
from core.llm import call_gemma3

CONTRACT_DIR = Path("schema/tool_contract")
REGISTRY_FILE = Path("schema/tool_registry_llm.json")
GEN_JSON_PATH = Path("schema/json_schemas/generated")

def enrich_description(tool_name, endpoint, required_inputs, response_sample=None):
    sample_snippet = ""
    if response_sample:
        sample_snippet = f"\nSample response:\n{json.dumps(response_sample, indent=2)}"
    prompt = f"""
You are an expert at documenting API tools for AI assistants (like OpenAI function calling).

Given this tool contract:
- Tool name: {tool_name}
- Endpoint: {endpoint}
- Required parameters: {required_inputs}
{sample_snippet}

Write a **concise, clear, and user-facing description** for this tool.
- 1-2 sentences.
- Avoid technical jargon.
- Focus on what real users can accomplish with this tool.
- Example: "Retrieves account statements for a specific holding account. Requires the account ID to identify the statements."

Respond **only** with the description string, no extra formatting.
"""
    response = call_gemma3(prompt).strip().strip('"')
    return response

def enrich_param_descriptions(tool_name, required_inputs, schema_obj=None):
    param_desc = {}
    for param in required_inputs:
        example = ""
        if schema_obj:
            desc = schema_obj.get("properties", {}).get(param, {}).get("description", "")
            if desc:
                example = f" Example: {desc}"
        prompt = f"""
You are an API assistant. Describe the input parameter '{param}' for the '{tool_name}' tool in a short phrase (max 10 words).{example}
Only respond with the description for '{param}'.
"""
        desc = call_gemma3(prompt).strip().strip('"')
        param_desc[param] = desc
    return param_desc

def try_load_json(path):
    if not Path(path).exists():
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Failed to load {path}: {e}")
        return None

def build_llm_registry():
    registry = []
    for contract_file in CONTRACT_DIR.glob("*.json"):
        with open(contract_file, "r") as f:
            contract = json.load(f)
            tool_name = contract["tool_name"]
            endpoint = contract.get("endpoint", "")
            required = contract.get("required_inputs", [])

            # --- Try loading actual sample response and schema for enrichment ---
            response_sample = None
            schema_obj = None
            # Look for the correct files, fallback gracefully
            json_base = GEN_JSON_PATH / f"{tool_name}_response.json"
            schema_base = GEN_JSON_PATH / f"{tool_name}_response_schema.json"
            response_sample = try_load_json(json_base)
            schema_obj = try_load_json(schema_base)

            description = contract.get("description", "")
            if not description or description.strip().lower().startswith("no description"):
                description = enrich_description(tool_name, endpoint, required, response_sample=response_sample)

            param_desc = contract.get("input_descriptions", {})
            if not param_desc or any(not v for v in param_desc.values()):
                param_desc = enrich_param_descriptions(tool_name, required, schema_obj=schema_obj)

            # Build LLM-friendly schema
            registry.append({
                "name": tool_name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        param: {
                            "type": "string",
                            "description": param_desc.get(param, "")
                        } for param in required
                    },
                    "required": required
                }
            })
    with open(REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=2)
    print(f"✅ LLM tool registry built at {REGISTRY_FILE}")

if __name__ == "__main__":
    build_llm_registry()
