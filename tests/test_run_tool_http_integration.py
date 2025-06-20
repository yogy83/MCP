import pytest
import responses
from tools.run_tool import run_tool
from config import config as cfg
import os
import sys
import pytest

# Allow imports from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.run_tool import apply_local_filters

@pytest.fixture(autouse=True)
def override_base_url():
    # Override base URL for tests
    cfg.TEMENOS_BASE_URL = "http://172.16.204.40:8280/irf-provider-container/api"


@pytest.fixture
def tx_contract():
    return {
        "tool_name": "get_account_transactions",
        "endpoint": "/v1.0.0/holdings/accounts/{accountId}/transactions",
        "required_inputs": ["accountId"],
        "optional_inputs": [
            {"name": "transactionName", "send_to_api": False}
        ],
        "filtering_rules": [
            {
                "input_param": "transactionName",
                "response_field": "transactionName",
                "filter_type": "exact",
                "case_sensitive": False
            }
        ]
    }


@responses.activate
def test_http_integration_exact_filter(tx_contract):
    url = cfg.TEMENOS_BASE_URL + tx_contract["endpoint"].format(accountId="100")
    sample = {"body": [
        {"transactionName": "Rent"},
        {"transactionName": "Food"},
        {"transactionName": "rent"}
    ]}
    responses.add(responses.GET, url, json=sample, status=200)

    out = run_tool(tx_contract, {"accountId": "100", "transactionName": "rent"})
    assert out == {"body": [
        {"transactionName": "Rent"},
        {"transactionName": "rent"}
    ]}


@responses.activate
def test_http_integration_no_filter(tx_contract):
    url = cfg.TEMENOS_BASE_URL + tx_contract["endpoint"].format(accountId="200")
    sample = {"body": [{"transactionName": "X"}, {"transactionName": "Y"}]}
    responses.add(responses.GET, url, json=sample, status=200)

    out = run_tool(tx_contract, {"accountId": "200"})
    assert out == sample
