import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from tools.run_tool import apply_local_filters


def make_response(body):
    return {"body": body}


def test_exact_match_case_insensitive():
    response = make_response([
        {"status": "Active"},
        {"status": "inactive"}
    ])
    contract = {
        "filtering_rules": [
            {
                "input_param": "status",
                "response_field": "status",
                "filter_type": "exact",
                "case_sensitive": False
            }
        ]
    }
    filtered = apply_local_filters(response, contract, {"status": "active"})
    assert filtered["body"] == [{"status": "Active"}]


def test_substring_contains():
    response = make_response([
        {"name": "HelloWorld"},
        {"name": "Test"}
    ])
    contract = {
        "filtering_rules": [
            {
                "input_param": "query",
                "response_field": "name",
                "filter_type": "substring"
            }
        ]
    }
    filtered = apply_local_filters(response, contract, {"query": "lloWo"})
    assert filtered["body"] == [{"name": "HelloWorld"}]


def test_fuzzy_substring_threshold():
    response = make_response([
        {"text": "Monthly Rent"},
        {"text": "Grocery Store"}
    ])
    contract = {
        "filtering_rules": [
            {
                "input_param": "query",
                "response_field": "text",
                "filter_type": "fuzzy_substring",
                "threshold": 80,
                "method": "partial"
            }
        ]
    }
    filtered = apply_local_filters(response, contract, {"query": "rent"})
    assert filtered["body"] == [{"text": "Monthly Rent"}]


def test_numerical_fuzzy_tolerance():
    response = make_response([
        {"amount": "100"},
        {"amount": "130"},
        {"amount": "90"}
    ])
    contract = {
        "filtering_rules": [
            {
                "input_param": "amt",
                "response_field": "amount",
                "filter_type": "numerical_fuzzy",
                "tolerance": 0.2
            }
        ]
    }
    filtered = apply_local_filters(response, contract, {"amt": "100"})
    amounts = {item["amount"] for item in filtered["body"]}
    assert "100" in amounts
    assert "90" in amounts
    assert "130" not in amounts


def test_date_from_and_to_filters():
    body = [
        {"date": "2025-01-01"},
        {"date": "2025-06-18"},
        {"date": "2024-12-31"}
    ]
    contract = {
        "filtering_rules": [
            {
                "input_param": "start",
                "response_field": "date",
                "filter_type": "date_from",
                "date_format": "%Y-%m-%d"
            },
            {
                "input_param": "end",
                "response_field": "date",
                "filter_type": "date_to",
                "date_format": "%Y-%m-%d"
            }
        ]
    }
    filtered = apply_local_filters(make_response(body), contract, {"start": "2025-01-01", "end": "2025-06-18"})
    dates = {item["date"] for item in filtered["body"]}
    assert dates == {"2025-01-01", "2025-06-18"}


if __name__ == "__main__":
    pytest.main()
