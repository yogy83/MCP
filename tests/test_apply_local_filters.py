# tests/test_apply_local_filters_all_cases.py


import os
import sys
import pytest

# Allow imports from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.run_tool import apply_local_filters

@pytest.mark.parametrize("description,response_data,tool_contract,local_filters,expected", [
    (
        "Exact match - case insensitive",
        {"body": [{"transactionName": "ATM Withdrawal"}]},
        {
            "filtering_rules": [
                {"input_param": "transactionName", "response_field": "transactionName", "filter_type": "exact"}
            ]
        },
        {"transactionName": "atm withdrawal"},
        [{"transactionName": "ATM Withdrawal"}]
    ),
    (
        "Substring match - partial match inside",
        {"body": [{"transactionName": "ATM Withdrawal at NY"}]},
        {
            "filtering_rules": [
                {"input_param": "transactionName", "response_field": "transactionName", "filter_type": "substring"}
            ]
        },
        {"transactionName": "ATM"},
        [{"transactionName": "ATM Withdrawal at NY"}]
    ),
    (
        "Fuzzy substring - partial match score above threshold",
        {"body": [{"transactionName": "ATM Withdrawl"}]},  # misspelled 'Withdrawal'
        {
            "filtering_rules": [
                {
                    "input_param": "transactionName",
                    "response_field": "transactionName",
                    "filter_type": "fuzzy_substring",
                    "threshold": 70
                }
            ]
        },
        {"transactionName": "ATM Withdrawal"},
        [{"transactionName": "ATM Withdrawl"}]
    ),
    (
        "Numerical fuzzy - within tolerance",
        {"body": [{"transactionAmount": 505.0}]},
        {
            "filtering_rules": [
                {
                    "input_param": "transactionAmount",
                    "response_field": "transactionAmount",
                    "filter_type": "numerical_fuzzy",
                    "tolerance": 0.02
                }
            ]
        },
        {"transactionAmount": "500"},
        [{"transactionAmount": 505.0}]
    ),
    (
        "Date from + to - within range",
        {"body": [{"bookingDate": "2024-04-15"}]},
        {
            "filtering_rules": [
                {
                    "input_param": "startDate",
                    "response_field": "bookingDate",
                    "filter_type": "date_from",
                    "date_format": "%Y-%m-%d"
                },
                {
                    "input_param": "endDate",
                    "response_field": "bookingDate",
                    "filter_type": "date_to",
                    "date_format": "%Y-%m-%d"
                }
            ]
        },
        {"startDate": "2024-04-01", "endDate": "2024-04-30"},
        [{"bookingDate": "2024-04-15"}]
    ),
    (
        "Unknown filter type - returns unfiltered list",
        {"body": [{"foo": "bar"}]},
        {
            "filtering_rules": [
                {"input_param": "x", "response_field": "foo", "filter_type": "unsupported"}
            ]
        },
        {"x": "bar"},
        [{"foo": "bar"}]
    )
])
def test_apply_local_filters_all_cases(description, response_data, tool_contract, local_filters, expected):
    result = apply_local_filters(response_data, tool_contract, local_filters)
    assert result["body"] == expected, f"Failed: {description}"
