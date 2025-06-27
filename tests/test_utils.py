import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import pytest
from unittest import mock
from core.utils import load_tool_contracts_from_folder, load_json_file


def test_load_json_file_success(tmp_path):
    # Create a valid JSON file
    file = tmp_path / "valid.json"
    file.write_text('{"key": "value"}', encoding="utf-8")
    
    data = load_json_file(str(file))  # <-- only one argument now
    assert data == {"key": "value"}

def test_load_json_file_file_not_found():
    data = load_json_file("non_existent_file.json")  # <-- only one argument now
    assert data is None

def test_load_json_file_malformed_json(tmp_path):
    file = tmp_path / "bad.json"
    file.write_text('{"key": "value"', encoding="utf-8")  # missing closing }

    data = load_json_file(str(file))  # <-- only one argument now
    assert data is None

@mock.patch("os.listdir")
@mock.patch("builtins.open")
def test_load_tool_contracts_from_folder_loads_contracts(mock_open, mock_listdir, tmp_path):
    mock_listdir.return_value = ["contract1.json"]
    
    contract_content = {
        "tool_name": "tool1",
        "json_schema": {
            "request": "request_schema.json",
            "response": "response_schema.json"
        }
    }
    request_schema = {"type": "object"}
    response_schema = {"type": "object"}

    schema_dir = tmp_path / "json_schemas"
    schema_dir.mkdir()
    (schema_dir / "request_schema.json").write_text(json.dumps(request_schema))
    (schema_dir / "response_schema.json").write_text(json.dumps(response_schema))

    def open_side_effect(filepath, *args, **kwargs):
        if filepath.endswith("contract1.json"):
            return mock.mock_open(read_data=json.dumps(contract_content)).return_value
        elif filepath.endswith("request_schema.json"):
            return mock.mock_open(read_data=json.dumps(request_schema)).return_value
        elif filepath.endswith("response_schema.json"):
            return mock.mock_open(read_data=json.dumps(response_schema)).return_value
        else:
            raise FileNotFoundError

    mock_open.side_effect = open_side_effect

    original_join = os.path.join  # Save the original os.path.join function

    with mock.patch("os.path.join", side_effect=lambda *args: original_join(tmp_path, *args[-2:])):
        contracts = load_tool_contracts_from_folder(str(tmp_path))
    
    assert "tool1" in contracts
    assert contracts["tool1"]["request_schema"] == request_schema
    assert contracts["tool1"]["response_schema"] == response_schema

def test_load_tool_contracts_folder_not_exist():
    contracts = load_tool_contracts_from_folder("/non/existent/folder")
    assert contracts == {}
