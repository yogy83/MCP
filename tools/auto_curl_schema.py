import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import requests
import re
from genson import SchemaBuilder
from core.llm import call_gemma3
from config.config import TEMENOS_BASE_URL, build_auth_headers
from urllib.parse import urlparse

TEST_VALUES = {
    "accountId": "105929",
    "customerId": "100210",
    "arrangementId": "AA24110J9XJ3",
    "currency": "USD",
    "page_size": "10",
    "page_start": "1",
    "page_token": "init"
}

class SkipEndpointException(Exception):
    pass

def curl_test_and_fetch(api_url: str, method="get", payload=None) -> dict:
    print(f"🌐 Hitting: {api_url}")
    headers = build_auth_headers()
    method_func = getattr(requests, method.lower())
    if payload and method.lower() == "post":
        resp = method_func(api_url, headers=headers, json=payload)
    else:
        resp = method_func(api_url, headers=headers)
    resp.raise_for_status()
    print("✅ API call success")
    return resp.json()

def save_json(data: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"📁 Saved: {path}")

def generate_schema(json_data: dict) -> dict:
    builder = SchemaBuilder()
    builder.add_object(json_data)
    schema = builder.to_schema()
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    return schema

def get_mock_value_for_param(name: str) -> str:
    if name in TEST_VALUES:
        return TEST_VALUES[name]
    print(f"⚠️ Skipping endpoint due to missing test value for required param '{name}'.")
    raise SkipEndpointException(name)

def build_full_url(base: str, base_path: str, endpoint: str, query: dict) -> str:
    parsed_base = urlparse(base)
    base_root = f"{parsed_base.scheme}://{parsed_base.netloc}"
    base_parts = parsed_base.path.strip("/").split("/")
    swagger_parts = base_path.strip("/").split("/") if base_path else []
    endpoint_part = endpoint.strip("/")

    while swagger_parts and swagger_parts[0] in base_parts:
        swagger_parts.pop(0)
    full_path = "/".join(filter(None, base_parts + swagger_parts + [endpoint_part]))
    url = f"{base_root}/{full_path}"
    if query:
        url += "?" + "&".join(f"{k}={v}" for k, v in query.items())
    return url

def get_tool_name(http_method: str, path: str) -> str:
    # Remove all {param} blocks for tool name; make generic
    generic = re.sub(r"\{[^\}]*\}", "", path)
    generic = generic.replace("//", "/")
    generic = generic.strip("/").replace("/", "_")
    # Collapse multiple underscores to one (avoid __)
    generic = re.sub(r'_+', '_', generic)
    return f"tool_{http_method.lower()}_{generic}"

def get_contract_filenames(tool_name: str):
    schema_folder = "schema/json_schemas/generated"
    contract_folder = "schema/tool_contract"
    response_path = f"{schema_folder}/{tool_name}_response.json"
    schema_path = f"{schema_folder}/{tool_name}_response_schema.json"
    contract_path = f"{contract_folder}/{tool_name}.json"
    return response_path, schema_path, contract_path

def extract_required_inputs_from_path(path):
    # Returns a list of param names, e.g. /foo/{bar}/baz/{bif} -> ['bar', 'bif']
    return re.findall(r"\{([^}]+)\}", path)

def generate_llm_tool_contract(tool_name: str, endpoint_path: str, sample_json: dict, required_inputs: list) -> dict:
    def extract_keys(obj, parent_key=""):
        keys = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                full_key = f"{parent_key}.{k}" if parent_key else k
                keys.append(full_key)
                keys.extend(extract_keys(v, full_key))
        elif isinstance(obj, list) and obj and isinstance(obj[0], dict):
            keys.extend(extract_keys(obj[0], parent_key))
        return keys

    response_keys = extract_keys(sample_json)
    key_summary = "\n".join(f"- {k}" for k in sorted(set(response_keys)))

    # Always force endpoint to have a leading slash
    if not endpoint_path.startswith("/"):
        endpoint_path = "/" + endpoint_path

    prompt = f"""
You are an intelligent API tool contract generator.

Given:
- Tool name: {tool_name}
- Endpoint (use exactly as provided): {endpoint_path}
- Sample JSON response:
{json.dumps(sample_json, indent=2)}

Extracted response keys:
{key_summary}

Create a JSON contract with:
- tool_name
- endpoint (unchanged)
- required_inputs: only required path/query params (populate with {required_inputs})
- optional_inputs: []    // (always empty for this script)
- filtering_rules: filters on fields inside response['body'] or response['header'] (not paging fields). Format:
  {{
    "input_param": "inputField",
    "response_field": "json.path",
    "filter_type": "exact" | "substring" | "date",
    "case_sensitive": false
  }}
Also:
- json_schema → request: null, response: "schema/json_schemas/generated/{tool_name}_response_schema.json"

Only output valid JSON. No markdown or commentary.
"""
    print(f"[DEBUG] Sending contract prompt to LLM for {tool_name}")
    llm_response = call_gemma3(prompt)
    llm_response = llm_response.strip()
    if llm_response.startswith("```json"):
        llm_response = llm_response.removeprefix("```json").removesuffix("```").strip()
    if not llm_response or not llm_response.startswith("{"):
        print(f"[DEBUG] LLM contract output empty or invalid, skipping.")
        return {}
    contract = json.loads(llm_response)
    contract["tool_name"] = tool_name
    contract["endpoint"] = endpoint_path
    contract["required_inputs"] = required_inputs
    contract["optional_inputs"] = []
    return contract

def main(swagger_path: str):
    with open(swagger_path) as f:
        swagger = json.load(f)

    # --- Defensive check on paths field ---
    paths = swagger.get("paths", {})
    if not isinstance(paths, dict):
        print("\n❌ ERROR: Swagger/OpenAPI 'paths' is not a dict!")
        print(f"Type of 'paths': {type(paths)}")
        print(f"Sample: {str(paths)[:250]} ...")
        print("You may have selected an inventory or non-Swagger file. Please provide a valid Swagger/OpenAPI spec.")
        return

    base_path = swagger.get("basePath", "")

    for path, methods in paths.items():
        for http_method in ["get", "post", "put", "delete"]:
            if http_method not in methods:
                continue
            endpoint_def = methods[http_method]
            all_params = endpoint_def.get("parameters", [])
            required_params = [p for p in all_params if p.get("required", False)]

            path_with_mock = path
            query = {}
            required_input_names = []

            skip_this = False
            for param in required_params:
                name = param.get("name")
                in_type = param.get("in")
                try:
                    mock_value = get_mock_value_for_param(name)
                except SkipEndpointException:
                    print(f"⏩ Skipping {path} for method {http_method} due to missing test value.")
                    skip_this = True
                    break
                required_input_names.append(name)
                if in_type == "path":
                    path_with_mock = path_with_mock.replace("{" + name + "}", mock_value)
                elif in_type == "query":
                    query[name] = mock_value
            if skip_this:
                continue

            # 2. Add all {param} in path as required if not already present
            for pname in extract_required_inputs_from_path(path):
                if pname not in required_input_names:
                    required_input_names.append(pname)

            # **SKIP if required_input_names is empty**
            if not required_input_names:
                print(f"⏩ Skipping {path} for method {http_method} (no required inputs)")
                continue

            # Compose endpoint_path: always has leading slash, always generic (with {param}!)
            endpoint_path = f"{base_path.rstrip('/')}/{path.lstrip('/')}"
            if not endpoint_path.startswith("/"):
                endpoint_path = "/" + endpoint_path

            url = build_full_url(TEMENOS_BASE_URL, base_path, path_with_mock, query)
            print(f"\n[Batch] Testing {http_method.upper()} {url}")

            try:
                response_json = curl_test_and_fetch(url, method=http_method)
            except Exception as e:
                print(f"❌ Skipping {path} due to: {e}")
                continue

            tool_name = get_tool_name(http_method, path)
            response_path, schema_path, contract_path = get_contract_filenames(tool_name)

            save_json(response_json, response_path)
            save_json(generate_schema(response_json), schema_path)
            contract = generate_llm_tool_contract(tool_name, endpoint_path, response_json, required_input_names)
            if contract:
                contract["json_schema"] = {
                    "request": None,
                    "response": schema_path
                }
                save_json(contract, contract_path)

if __name__ == "__main__":
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()

    swagger_path = filedialog.askopenfilename(
        title="Select Swagger JSON File",
        filetypes=[("Swagger/OpenAPI JSON", "*.json")]
    )

    if not swagger_path:
        print("❌ No file selected.")
        exit(1)

    print(f"📂 Selected Swagger: {swagger_path}")
    main(swagger_path)
