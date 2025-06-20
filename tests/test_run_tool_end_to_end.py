import pytest
from tools.run_tool import run_tool

@pytest.fixture
def dummy_contract():
    return {
        "tool_name": "dummy_tool",
        "endpoint": "/dummy/{required}",
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
    the raw API response (i.e. no filtering), and should not send
    any optional inputs to the API.
    """
    inputs = {"required": "X"}
    fake_raw = {"body": [{"value": "A"}, {"value": "B"}]}

    def fake_call_api(endpoint, path_params, query_params):
        # endpoint & path_params still get passed
        assert endpoint == dummy_contract["endpoint"]
        assert path_params == {"required": "X"}
        # but since filter.send_to_api is False, query_params must be empty
        assert query_params == {}
        return fake_raw

    monkeypatch.setattr("tools.run_tool.call_api", fake_call_api)
    result = run_tool(dummy_contract, inputs)
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
    assert filtered == {
        "body": [
            {"value": "foo"},
            {"value": "Foo"}
        ]
    }
