import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from tools.run_tool import run_tool, apply_local_filters

DATA = {
    "body": [
        {"value": "Foo"},
        {"value": "foobar"},
        {"value": "bar"},
        {"value": None},
    ]
}

def make_contract(rules):
    return {
        "filtering_rules": rules
    }

def test_run_tool_request_validation_failure():
    tool_contract = {
        "tool_name": "get_account_balance",
        "endpoint": "/v1.0.0/holdings/accounts/{accountId}",
        "required_inputs": ["accountId"],
        "request_schema": {
            "type": "object",
            "properties": {
                "accountId": {"type": "string", "pattern": "^[0-9]{5,12}$"}
            },
            "required": ["accountId"]
        },
        "optional_inputs": []
    }
    invalid_inputs = {"accountId": "CUST001"}  # invalid pattern
    with pytest.raises(Exception):
        run_tool(tool_contract, invalid_inputs, request_schema=tool_contract["request_schema"])

def test_exact_case_insensitive():
    contract = make_contract([{
        "input_param": "q",
        "response_field": "value",
        "filter_type": "exact",
        "case_sensitive": False
    }])
    out = apply_local_filters(DATA, contract, {"q": "foo"})
    assert out == {"body": [{"value": "Foo"}]}

def test_substring():
    contract = make_contract([{
        "input_param": "q",
        "response_field": "value",
        "filter_type": "substring",
        "case_sensitive": False
    }])
    out = apply_local_filters(DATA, contract, {"q": "foo"})
    assert out == {"body": [{"value": "Foo"}, {"value": "foobar"}]}

def test_fuzzy_substring_partial():
    contract = make_contract([{
        "input_param": "q",
        "response_field": "value",
        "filter_type": "fuzzy_substring",
        "threshold": 50,
        "method": "partial"
    }])
    out = apply_local_filters(DATA, contract, {"q": "foo"})
    assert out == {"body": [{"value": "Foo"}, {"value": "foobar"}]}

def test_numerical_fuzzy():
    data = {"body": [{"val": 90}, {"val": 110}, {"val": 130}]}
    contract = {
        "filtering_rules": [{
            "input_param": "x",
            "response_field": "val",
            "filter_type": "numerical_fuzzy",
            "tolerance": 0.2
        }]
    }
    out = apply_local_filters(data, contract, {"x": "100"})
    assert out == {"body": [{"val": 90}, {"val": 110}]}
