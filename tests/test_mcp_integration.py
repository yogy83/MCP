# tests/test_mcp_integration.py

import os
import sys
import pytest
import json

# Allow imports from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.mcp as mcp
import core.planner as planner

@pytest.fixture(autouse=True)
def stub_llm_and_tools(monkeypatch):
    # 1) Stub planner.plan to return a single-step plan
    def fake_plan(goal, objective, expected_outcome, memory):
        step = {"tool": "get_account_balance", "inputs": {"accountId": "123"}}
        return [step], []
    monkeypatch.setattr(planner, "plan", fake_plan)

    # 2) Stub mcp.execute_plan (imported in mcp.py) to return a step1 result
    monkeypatch.setattr(
        mcp,
        "execute_plan",
        lambda plan_steps: {"step1": {"body": [{"balance": 1000}]}}
    )

    # 3) Stub mcp.aggregate (imported in mcp.py) to return summary and structured raw_result
    def fake_aggregate(tool_outputs, expected_outcome):
        return {
            "summary": "Your balance is $1000.",
            "raw_result": {"step1": tool_outputs[0]["result"]},
            "raw_text": {"step1": "Balance returned: 1000"}
        }
    monkeypatch.setattr(mcp, "aggregate", fake_aggregate)

    yield

def test_full_pipeline_smoke():
    payload = {
        "goal": "What’s my balance?",
        "objective": "...",
        "expected_outcome": "...",
        "parameters": {}   # initial memory
    }
    out = mcp.process_user_request(payload, session_id="sess")

    # 1) Planner produced a single step
    assert len(out["plan"]) == 1
    assert out["plan"][0]["tool"] == "get_account_balance"

    # 2) Execution result surfaced under raw_result
    assert out["raw_result"] == {"step1": {"body": [{"balance": 1000}]}}

    # 3) Aggregator stub shapes summary & raw_text
    assert out["final_summary"] == "Your balance is $1000."
    assert out["raw_text"]["step1"] == "Balance returned: 1000"

    # 4) Session info & next_action
    assert out["session_id"] == "sess"
    assert out["next_action"] == "respond_with_result"
