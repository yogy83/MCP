import os
import sys
import json
import shutil
import tempfile
from unittest.mock import patch, MagicMock
from pathlib import Path

# 🛠️ Allow root-level import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from tools.run_tool import run_tool

# --- Setup ---
temp_dir = tempfile.mkdtemp()
contract_path = Path(temp_dir) / "get_account_transactions.json"

contract_data = {
    "tool_name": "get_account_transactions",
    "endpoint": "/dummy/{accountId}/transactions",
    "required_inputs": ["accountId"],
    "optional_inputs": [
        {"name": "transactionName", "send_to_api": False},
        {"name": "startDate", "send_to_api": False},
        {"name": "endDate", "send_to_api": False}
    ],
    "filtering_rules": [
        {"input_param": "transactionName", "response_field": "transactionName", "filter_type": "substring"},
        {"input_param": "startDate", "response_field": "bookingDate", "filter_type": "date_from"},
        {"input_param": "endDate", "response_field": "bookingDate", "filter_type": "date_to"}
    ]
}

with open(contract_path, "w") as f:
    json.dump(contract_data, f)

mock_api_response = {
    "body": [
        {"transactionName": "ATM Withdrawal", "bookingDate": "01 Apr 2024"},
        {"transactionName": "Internal Transfer", "bookingDate": "05 Apr 2024"},
        {"transactionName": "ATM Withdrawal", "bookingDate": "20 Apr 2024"},
        {"transactionName": "ATM Withdrawal", "bookingDate": "01 May 2024"}
    ]
}

# --- Test Case ---
@patch("tools.run_tool.requests.get")
@patch("config.config.build_auth_headers", return_value={"Authorization": "Bearer test"})
def test_run_tool_with_april_filters(mock_headers, mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_api_response
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    inputs = {
        "accountId": "105929",
        "transactionName": "ATM Withdrawal",
        "startDate": "01 Apr 2024",
        "endDate": "30 Apr 2024"
    }

    result = run_tool(contract_data, inputs)
    expected = {
        "body": [
            {"transactionName": "ATM Withdrawal", "bookingDate": "01 Apr 2024"},
            {"transactionName": "ATM Withdrawal", "bookingDate": "20 Apr 2024"}
        ]
    }

    assert result == expected

# --- Cleanup ---
def teardown_module(module):
    shutil.rmtree(temp_dir)
