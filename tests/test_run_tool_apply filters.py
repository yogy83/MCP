import pytest
from tools.run_tool import apply_local_filters

@pytest.fixture
def sample_data():
    return {
        "body": [
            {
                "transactionName": "ATM Withdrawal - Mumbai",
                "transactionAmount": 5000,
                "bookingDate": "2024-04-10"
            },
            {
                "transactionName": "POS Purchase",
                "transactionAmount": 200,
                "bookingDate": "2024-05-01"
            }
        ]
    }

def test_fuzzy_substring_match(sample_data):
    contract = {
        "filtering_rules": [
            {
                "input_param": "transactionName",
                "response_field": "transactionName",
                "filter_type": "fuzzy_substring",
                "threshold": 70,
                "method": "partial"
            }
        ]
    }
    filters = {"transactionName": "ATM Withdrawal"}
    result = apply_local_filters(sample_data, contract, filters)
    assert len(result["body"]) == 1
    assert "ATM Withdrawal" in result["body"][0]["transactionName"]

def test_date_range_filter(sample_data):
    contract = {
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
    }
    filters = {
        "startDate": "2024-04-01",
        "endDate": "2024-04-30"
    }
    result = apply_local_filters(sample_data, contract, filters)
    assert len(result["body"]) == 1
    assert result["body"][0]["bookingDate"] == "2024-04-10"

def test_numerical_fuzzy_pass(sample_data):
    contract = {
        "filtering_rules": [
            {
                "input_param": "transactionAmount",
                "response_field": "transactionAmount",
                "filter_type": "numerical_fuzzy",
                "tolerance": 0.1
            }
        ]
    }
    filters = {"transactionAmount": 5100}  # 5000 is within 10%
    result = apply_local_filters(sample_data, contract, filters)
    assert len(result["body"]) == 1

def test_numerical_fuzzy_fail(sample_data):
    contract = {
        "filtering_rules": [
            {
                "input_param": "transactionAmount",
                "response_field": "transactionAmount",
                "filter_type": "numerical_fuzzy",
                "tolerance": 0.01  # too tight
            }
        ]
    }
    filters = {"transactionAmount": 5100}
    result = apply_local_filters(sample_data, contract, filters)
    assert len(result["body"]) == 0
