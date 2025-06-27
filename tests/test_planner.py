import os
import sys
import json
import pytest
from uuid import UUID

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.planner as planner  # <-- Correct import here


def test_generate_reasoned_plan_handles_invalid_json(monkeypatch):
    # Stub LLM to return invalid JSON
    def broken(prompt):
        return "This is not JSON"
    monkeypatch.setattr(planner, "call_gemma3", broken)
    monkeypatch.setattr(planner, "tool_contracts", {
        "tool_a": {"required_inputs": ["foo"], "optional_inputs": []}
    })

    with pytest.raises(json.JSONDecodeError):
        planner.generate_reasoned_plan(
            goal="g", objective="o", expected_outcome="e",
            memory={}, user_inputs={}
        )

def test_generate_reasoned_plan_handles_unexpected_json_structure(monkeypatch):
    # Stub LLM to return JSON missing expected keys
    def broken(prompt):
        return "```json\n" + json.dumps({"unexpected": "data"}) + "\n```"
    monkeypatch.setattr(planner, "call_gemma3", broken)
    monkeypatch.setattr(planner, "tool_contracts", {
        "tool_a": {"required_inputs": ["foo"], "optional_inputs": []}
    })

    # Should not raise but return defaults with empty plan and missing all required inputs
    out = planner.generate_reasoned_plan(
        goal="g", objective="o", expected_outcome="e",
        memory={}, user_inputs={}
    )
    assert out["plan"] == []
    # Missing should contain all required inputs from tool contracts (foo)
    assert "foo" in out["missing"]
    assert out["next_action"] == "ask_user"

def test_resolve_placeholders_basic():
    memory = {"KEY1": "value1"}
    user_inputs = {"KEY2": "value2"}
    inputs = {
        "param1": "<KEY1>",
        "param2": "<KEY2>",
        "param3": "literal",
        "param4": {"nested": "<KEY1>"},
        "param5": "<UNKNOWN>"
    }

    resolved = planner.resolve_placeholders(inputs, memory, user_inputs)
    assert resolved["param1"] == "value1"
    assert resolved["param2"] == "value2"
    assert resolved["param3"] == "literal"
    assert isinstance(resolved["param4"], dict)
    assert resolved["param4"]["nested"] == "value1"
    # Unresolved placeholder returns None
    assert resolved["param5"] is None

def test_generate_reasoned_plan_missing_tool_contract(monkeypatch):
    # LLM returns a tool name not in tool_contracts
    def fake(prompt):
        data = {
            "goal": "g",
            "fallback_response": "fallback",
            "tool_chain": [
                {"tool": "non_existent_tool", "inputs": {}}
            ]
        }
        return "```json\n" + json.dumps(data) + "\n```"
    monkeypatch.setattr(planner, "call_gemma3", fake)
    monkeypatch.setattr(planner, "tool_contracts", {
        # Intentionally empty dict so no tool contracts
    })

    out = planner.generate_reasoned_plan(
        goal="g", objective="o", expected_outcome="e",
        memory={}, user_inputs={}
    )
    # Plan contains the step as is (no inputs can be validated)
    assert out["plan"][0]["tool"] == "non_existent_tool"
    # Missing should be empty because we cannot check required inputs
    assert out["missing"] == []
    # Next action should default to respond_with_result since no missing known
    assert out["next_action"] == "respond_with_result"
