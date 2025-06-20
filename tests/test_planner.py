# tests/test_planner.py

import os
import sys
import json
import pytest
from uuid import UUID

# Ensure project root is on sys.path so `import core.planner` works
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.planner as planner

@pytest.fixture(autouse=True)
def dummy_contracts(monkeypatch):
    """
    Override tool_contracts with a simplified, known set:
    - tool_a requires ['foo']
    - tool_b requires ['bar'] and has optional send_to_api 'baz'
    """
    dummy = {
        "tool_a": {
            "required_inputs": ["foo"],
            "optional_inputs": []
        },
        "tool_b": {
            "required_inputs": ["bar"],
            "optional_inputs": [
                {"name": "baz", "send_to_api": True},
                {"name": "qux", "send_to_api": False}
            ]
        }
    }
    monkeypatch.setattr(planner, "tool_contracts", dummy)
    yield

@pytest.fixture
def fake_llm(monkeypatch):
    """
    Stub call_gemma3 to return a deterministic JSON payload.
    """
    def _fake(prompt):
        data = {
            "goal": "restated",
            "fallback_response": "Please provide missing",
            "tool_chain": [
                {
                    "tool": "tool_a",
                    "inputs": {"foo": "val1", "qux": "local1"}
                },
                {
                    "tool": "tool_b",
                    "inputs": {"bar": "val2", "baz": "val3", "qux": "local2"}
                }
            ]
        }
        # wrap in ```json blocks
        return "```json\n" + json.dumps(data) + "\n```"
    monkeypatch.setattr(planner, "call_gemma3", _fake)
    yield

def test_generate_reasoned_plan_no_missing(fake_llm):
    """
    When all required inputs are present, missing==[], next_action == respond_with_result.
    """
    # We must now pass user_inputs (even if empty) to planner.plan()
    user_inputs = {"foo": "val1", "bar": "val2", "baz": "val3", "qux": "local?"}
    out = planner.generate_reasoned_plan(
        goal="g",
        objective="o",
        expected_outcome="e",
        memory={},          # no pre‐filled memory
        user_inputs=user_inputs
    )

    # session_id is a valid UUID
    assert isinstance(UUID(out["session_id"]), UUID)
    assert out["next_action"] == "respond_with_result"
    assert out["is_final"] is True
    assert out["missing"] == []

    chain = out["plan"]
    assert len(chain) == 2

    # Step1: tool_a
    step1 = chain[0]
    assert step1["tool"] == "tool_a"
    assert step1["api_inputs"] == {"foo": "val1"}
    assert step1["local_filters"] == {"qux": "local1"}

    # Step2: tool_b
    step2 = chain[1]
    assert step2["tool"] == "tool_b"
    assert step2["api_inputs"] == {"bar": "val2", "baz": "val3"}
    assert step2["local_filters"] == {"qux": "local2"}

    assert out["fallback_response"] == "Please provide missing"

def test_generate_reasoned_plan_injects_user_filters(fake_llm):
    """
    Even if the LLM plan omitted local filters, we re-inject them from user_inputs.
    """
    # Stub LLM to omit qux entirely
    def _broken(prompt):
        data = {
            "goal": "restated",
            "fallback_response": "ask",
            "tool_chain": [
                {"tool": "tool_a", "inputs": {"foo": "val1"}}
            ]
        }
        return "```json\n" + json.dumps(data) + "\n```"
    planner.call_gemma3 = _broken

    user_inputs = {"foo": "val1", "qux": "manual_local"}
    out = planner.generate_reasoned_plan(
        goal="g", objective="o", expected_outcome="e",
        memory={}, user_inputs=user_inputs
    )

    # Even though the LLM only gave foo, we expect qux to show up under local_filters
    step = out["plan"][0]
    assert step["api_inputs"] == {"foo": "val1"}
    assert step["local_filters"] == {"qux": "manual_local"}

def test_generate_reasoned_plan_with_missing(monkeypatch):
    """
    If the JSON omits a required param, that appears in missing[] and next_action==ask_user.
    """
    # stub LLM to drop 'foo'
    def broken(prompt):
        data = {
            "goal":"g","fallback_response":"ask","tool_chain":[
                {"tool":"tool_a","inputs":{}}
            ]
        }
        return "```json\n" + json.dumps(data) + "\n```"
    monkeypatch.setattr(planner, "call_gemma3", broken)
    monkeypatch.setattr(planner, "tool_contracts", {
        "tool_a": {"required_inputs": ["foo"], "optional_inputs": []}
    })

    out = planner.generate_reasoned_plan(
        goal="g", objective="o", expected_outcome="e",
        memory={}, user_inputs={}
    )
    assert out["next_action"] == "ask_user"
    assert out["is_final"] is False
    assert out["missing"] == ["foo"]
    # inputs remain empty
    step = out["plan"][0]
    assert step["api_inputs"] == {}
    assert step["local_filters"] == {}

def test_plan_helper_returns_plan_and_missing(fake_llm):
    """
    The plan() wrapper returns exactly (plan, missing).
    """
    p, missing = planner.plan(
        goal="g", objective="o", expected_outcome="e",
        memory={}, user_inputs={"foo":"val1"}
    )
    full = planner.generate_reasoned_plan(
        goal="g", objective="o", expected_outcome="e",
        memory={}, user_inputs={"foo":"val1"}
    )
    assert p == full["plan"]
    assert missing == full["missing"]
