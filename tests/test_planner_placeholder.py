import pytest
from unittest.mock import patch
from core import planner

def test_resolve_placeholders_basic():
    memory = {"customerId": "CUST123", "accountId": "ACC456"}
    user_inputs = {"userRole": "admin"}
    inputs = {
        "customerId": "<customerId>",
        "accountId": "<accountId>",
        "role": "<userRole>",
        "staticValue": "fixed"
    }

    resolved = planner.resolve_placeholders(inputs, memory, user_inputs)
    assert resolved == {
        "customerId": "CUST123",
        "accountId": "ACC456",
        "role": "admin",
        "staticValue": "fixed"
    }

def test_resolve_placeholders_nested():
    memory = {"id": "ID1"}
    user_inputs = {}
    inputs = {
        "outer": {
            "inner": "<id>"
        }
    }
    resolved = planner.resolve_placeholders(inputs, memory, user_inputs)
    assert resolved == {
        "outer": {
            "inner": "ID1"
        }
    }

@patch("core.planner.call_gemma3")
def test_generate_reasoned_plan_placeholder_resolution(mock_call_gemma3):
    # Simulate LLM JSON response with placeholders in inputs
    mock_call_gemma3.return_value = """
    {
        "goal": "Test Goal",
        "fallback_response": "Fallback",
        "tool_chain": [
            {
                "tool": "get_customer_accounts",
                "inputs": {
                    "customerId": "<customerId>",
                    "extraFilter": "<extraFilter>"
                }
            }
        ]
    }
    """
    memory = {"customerId": "CUST999"}
    user_inputs = {"extraFilter": "extraValue"}

    result = planner.generate_reasoned_plan(
        goal="Test Goal",
        objective="Test Objective",
        expected_outcome="Test Outcome",
        memory=memory,
        user_inputs=user_inputs
    )

    tool_chain = result["plan"]
    assert tool_chain[0]["api_inputs"]["customerId"] == "CUST999"
    assert tool_chain[0]["local_filters"]["extraFilter"] == "extraValue"
    assert result["missing"] == []
