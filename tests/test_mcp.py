# tests/test_mcp.py

import os
import sys
import pytest

# allow imports from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.mcp as mcp

@pytest.fixture(autouse=True)
def stub_components(monkeypatch):
    """
    Stub out:
      - planner.plan
      - execute_plan
      - aggregate
    so process_user_request returns a predictable happy-path.
    """
    # 1) stub planner.plan → returns (plan_steps, missing_list)
    def fake_plan(goal, objective, outcome, memory):
        # single step with placeholders for inputs/api_inputs/local_filters
        step = {"tool": "t1", "inputs": {"x": 1}}
        return [step], []
    monkeypatch.setattr(mcp.planner, "plan", fake_plan)

    # 2) stub execute_plan → returns {"step1": {"data": 123}}
    monkeypatch.setattr(mcp, "execute_plan", lambda plan: {"step1": {"data": 123}})

    # 3) stub aggregate → returns summary/raw_result/raw_text
    def fake_aggregate(tool_outputs, expected_outcome):
        return {
            "summary": "OK summary",
            "raw_result": {"step1": {"data": 123}},
            "raw_text": {"step1": "Step text"}
        }
    monkeypatch.setattr(mcp, "aggregate", fake_aggregate)

    yield

def test_process_user_request_happy_path():
    payload = {
        "goal": "g",
        "objective": "o",
        "expected_outcome": "e",
        "parameters": {},    # initial memory
    }

    # call the function
    resp = mcp.process_user_request(payload, session_id="sess1")

    # plan should be echoed
    assert isinstance(resp["plan"], list) and len(resp["plan"]) == 1
    assert resp["plan"][0]["tool"] == "t1"
    # next_action must be respond_with_result
    assert resp["next_action"] == "respond_with_result"
    # summary and raw_text from fake_aggregate
    assert resp["final_summary"] == "OK summary"
    assert resp["raw_result"] == {"step1": {"data": 123}}
    assert resp["raw_text"] == {"step1": "Step text"}
    # is_final true
    assert resp["is_final"] is True
    # session_id propagated
    assert resp["session_id"] == "sess1"
    # memory_passed echoes parameters
    assert resp["memory_passed"] == {}

def test_process_user_request_missing_param(monkeypatch):
    """
    If planner.plan returns missing parameters, should ask_user.
    """
    # stub plan to return missing
    monkeypatch.setattr(mcp.planner, "plan", lambda g,o,e,m: ([], ["foo"]))

    payload = {
        "goal": "g",
        "objective": "o",
        "expected_outcome": "e",
        "parameters": {},
    }
    resp = mcp.process_user_request(payload, session_id="sess2")

    assert resp["next_action"] == "ask_user"
    assert "prompt" in resp and "Please provide foo" in resp["prompt"]
    assert resp["missing"] == ["foo"]
    assert resp["is_final"] is False
    # plan should be empty
    assert resp["plan"] == []
