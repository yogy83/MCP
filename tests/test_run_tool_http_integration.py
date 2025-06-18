import json
import pytest
import responses

# 1) Import the full entry-point
from tools.run_tool import run_tool

# 2) Patch BASE_URL so run_tool targets our fake server
import config.config as cfg
@pytest.fixture(autouse=True)
def configure_base_url(monkeypatch):
    monkeypatch.setattr(cfg, "BASE_URL", "http://localhost:8000/api")

# 3) A sample contract for the transactions tool
@pytest.fixture
def tx_contract():
    return {
        "tool_name": "get_account_transactions",
        "endpoint":  "/v1.0.0/holdings/accounts/{accountId}/transactions",
        "required_inputs": ["accountId"],
        "optional_inputs": [
            {"name": "transactionName", "send_to_api": False}
        ],
        "filtering_rules": [
            {
                "input_param":    "transactionName",
                "response_field": "transactionName",
                "filter_type":    "exact",
                "case_sensitive": False
            }
        ]
    }

@responses.activate
def test_http_integration_exact_filter(tx_contract):
    """
    True integration: run_tool -> call_api (requests.get) -> apply_local_filters
    """
    # 1) Stub the HTTP endpoint. Note BASE_URL + endpoint:
    url = "http://localhost:8000/api" + tx_contract["endpoint"].format(accountId="100")
    sample_body = {
        "body": [
            {"transactionName": "Rent"},
            {"transactionName": "Food"},
            {"transactionName": "rent"}
        ]
    }
    responses.add(responses.GET, url, json=sample_body, status=200)

    # 2) Invoke with a local filter
    result = run_tool(tx_contract, {"accountId": "100", "transactionName": "rent"})

    # 3) Only records matching “rent” (case-insensitive) remain
    assert result == {
        "body": [
            {"transactionName": "Rent"},
            {"transactionName": "rent"}
        ]
    }

@responses.activate
def test_http_integration_no_filter(tx_contract):
    """
    When no local_filters are provided, output == raw API response.
    """
    url = "http://localhost:8000/api" + tx_contract["endpoint"].format(accountId="200")
    sample_body = {"body":[{"transactionName":"X"},{"transactionName":"Y"}]}
    responses.add(responses.GET, url, json=sample_body, status=200)

    # No 'transactionName' filter in inputs → no filtering
    result = run_tool(tx_contract, {"accountId": "200"})
    assert result == sample_body
