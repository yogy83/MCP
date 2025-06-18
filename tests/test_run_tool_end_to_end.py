import pytest

# 1) Import the function under test
from tools.run_tool import run_tool

# 2) A dummy contract to exercise both required_inputs and a local exact‐match filter
@pytest.fixture
def dummy_contract():
    return {
        "tool_name": "dummy_tool",
        "endpoint":  "/dummy/{required}",
        "required_inputs": ["required"],
        "optional_inputs": [
            {"name": "filter", "send_to_api": False}
        ],
        "filtering_rules": [
            {
                "input_param":    "filter",
                "response_field": "value",
                "filter_type":    "exact",
                "case_sensitive": False
            }
        ]
    }

def test_run_tool_without_local_filters(monkeypatch, dummy_contract):
    """
    If no local_filters are passed, run_tool should just return
    the raw API response (i.e. no filtering).
    """
    inputs = {"required": "X"}

    # fake_raw is what our fake call_api will return
    fake_raw = {"body": [{"value": "A"}, {"value": "B"}]}

    # Monkeypatch call_api to assert correct params and return fake_raw
    def fake_call_api(endpoint, path_params, query_params):
        assert endpoint == dummy_contract["endpoint"]
        assert path_params == {"required": "X"}
        # Since send_to_api is False for "filter", query_params == path_params
        assert query_params == {"required": "X"}
        return fake_raw

    monkeypatch.setattr("tools.run_tool.call_api", fake_call_api)

    result = run_tool(dummy_contract, inputs)
    # Should be unchanged, since no local “filter” was provided
    assert result == fake_raw

def test_run_tool_with_exact_filter(monkeypatch, dummy_contract):
    """
    If a local filter is provided, run_tool should filter out
    any records whose 'value' != filter (case-insensitive).
    """
    inputs = {"required": "X", "filter": "foo"}

    raw = {
        "body": [
            {"value": "foo"},
            {"value": "Foo"},
            {"value": "bar"},
            {"value": None},
        ]
    }

    # Stub call_api to return our raw dataset
    monkeypatch.setattr("tools.run_tool.call_api", lambda e, p, q: raw)

    filtered = run_tool(dummy_contract, inputs)
    # Expect only the two records where value == 'foo' ignoring case
    assert filtered == {
        "body": [
            {"value": "foo"},
            {"value": "Foo"}
        ]
    }
