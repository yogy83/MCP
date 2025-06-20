import pytest
from tools.run_tool import apply_local_filters

# Test data without a "body" key
def test_missing_body_key_returns_empty_list():
    contract = {
        "filtering_rules": [
            {
                "input_param":    "q",
                "response_field": "value",
                "filter_type":    "exact",
                "case_sensitive": False
            }
        ]
    }
    out = apply_local_filters({}, contract, {"q": "foo"})
    assert out == {"body": []}

# Test unknown filter_type leaves data unchanged
def test_unknown_filter_type_skips_filter():
    data = {"body": [{"a": 1}, {"a": 2}]}
    contract = {
        "filtering_rules": [
            {
                "input_param":    "q",
                "response_field": "a",
                "filter_type":    "weird_type"
            }
        ]
    }
    out = apply_local_filters(data, contract, {"q": "ignored"})
    assert out == data

# Test missing response_field in items yields empty result
def test_missing_response_field_yields_empty():
    data = {"body": [{"x": 1}, {"x": 2}]}
    contract = {
        "filtering_rules": [
            {
                "input_param":    "q",
                "response_field": "value",
                "filter_type":    "exact",
                "case_sensitive": False
            }
        ]
    }
    out = apply_local_filters(data, contract, {"q": "1"})
    assert out == {"body": []}

# Test invalid date_format causes skip of that filter
def test_invalid_date_format_skips_date_filter():
    data = {"body": [
        {"date": "2025-01-15"},
        {"date": "2025-02-15"}
    ]}
    contract = {
        "filtering_rules": [
            {
                "input_param":    "startDate",
                "response_field": "date",
                "filter_type":    "date_from",
                "date_format":    "%d/%m/%Y"
            }
        ]
    }
    out = apply_local_filters(data, contract, {"startDate": "2025-01-01"})
    assert out == data

# Test non-string local_filters value is handled gracefully
def test_non_string_local_filter_value():
    data = {"body": [{"num": 100}, {"num": 200}, {"num": 300}]}
    contract = {
        "filtering_rules": [
            {
                "input_param":    "num",
                "response_field": "num",
                "filter_type":    "exact"
            }
        ]
    }
    out = apply_local_filters(data, contract, {"num": 200})
    assert out == {"body": [{"num": 200}]}
