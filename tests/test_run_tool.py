import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from tools.run_tool import apply_local_filters


# Sample data for multiple tests
DATA = {
    "body": [
        {"value": "Foo"},       # exact / substring / fuzzy
        {"value": "foobar"},    # substring
        {"value": "bar"},       # no match
        {"value": None},        # guard
    ]
}

def make_contract(rules):
    return {
        "filtering_rules": rules
    }

def test_exact_case_insensitive():
    contract = make_contract([{
        "input_param":    "q",
        "response_field": "value",
        "filter_type":    "exact",
        "case_sensitive": False
    }])
    out = apply_local_filters(DATA, contract, {"q": "foo"})
    assert out == {"body": [{"value": "Foo"}]}

def test_substring():
    contract = make_contract([{
        "input_param":    "q",
        "response_field": "value",
        "filter_type":    "substring",
        "case_sensitive": False
    }])
    out = apply_local_filters(DATA, contract, {"q": "foo"})
    assert out == {"body": [{"value": "Foo"}, {"value": "foobar"}]}

def test_fuzzy_substring_partial():
    contract = make_contract([{
        "input_param":    "q",
        "response_field": "value",
        "filter_type":    "fuzzy_substring",
        "threshold":      50,
        "method":         "partial"
    }])
    out = apply_local_filters(DATA, contract, {"q": "foo"})
    # "Foo" (100), "foobar" (100) both pass
    assert out == {"body": [{"value": "Foo"}, {"value": "foobar"}]}

def test_numerical_fuzzy():
    data = {"body": [{"val": 90}, {"val": 110}, {"val": 130}]}
    contract = {
        "filtering_rules": [{
            "input_param":    "x",
            "response_field": "val",
            "filter_type":    "numerical_fuzzy",
            "tolerance":      0.2
        }]
    }
    out = apply_local_filters(data, contract, {"x": "100"})
    assert out == {"body": [{"val": 90}, {"val": 110}]}

def test_date_from_to():
    data = {"body": [
        {"d": "2025-01-15"},
        {"d": "2024-12-31"},
        {"d": "2025-02-01"}
    ]}
    contract = {
        "filtering_rules": [
            {
                "input_param":    "startDate",
                "response_field": "d",
                "filter_type":    "date_from",
                "date_format":    "%Y-%m-%d"
            },
            {
                "input_param":    "endDate",
                "response_field": "d",
                "filter_type":    "date_to",
                "date_format":    "%Y-%m-%d"
            }
        ]
    }
    out = apply_local_filters(
        data,
        contract,
        {"startDate": "2025-01-01", "endDate": "2025-01-31"}
    )
    assert out == {"body": [{"d": "2025-01-15"}]}

def test_date_from_greater_than_date_to():
    data = {"body": [
        {"d": "2025-01-10"},
        {"d": "2025-01-20"}
    ]}
    contract = {
        "filtering_rules": [
            {
                "input_param":    "startDate",
                "response_field": "d",
                "filter_type":    "date_from",
                "date_format":    "%Y-%m-%d"
            },
            {
                "input_param":    "endDate",
                "response_field": "d",
                "filter_type":    "date_to",
                "date_format":    "%Y-%m-%d"
            }
        ]
    }
    out = apply_local_filters(
        data,
        contract,
        {"startDate": "2025-01-31", "endDate": "2025-01-01"}  # Inverted range
    )
    # Nothing should match
    assert out == {"body": []}


def test_date_parsing_with_timezone_included():
    data = {"body": [
        {"d": "2025-01-15T10:00:00Z"},
        {"d": "2025-01-01T00:00:00+00:00"},
        {"d": "2025-01-31T23:59:59Z"}
    ]}
    contract = {
        "filtering_rules": [
            {
                "input_param":    "startDate",
                "response_field": "d",
                "filter_type":    "date_from"
            },
            {
                "input_param":    "endDate",
                "response_field": "d",
                "filter_type":    "date_to"
            }
        ]
    }
    out = apply_local_filters(
        data,
        contract,
        {"startDate": "2025-01-10", "endDate": "2025-01-20"}
    )
    assert out == {"body": [{"d": "2025-01-15T10:00:00Z"}]}
