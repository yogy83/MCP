# tests/test_planner_filters.py

import json, os, sys
import pytest

# Make sure core is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core import planner

def fake_call_gemma3(prompt: str) -> str:
    # Return a plan that only includes accountId—missing the filters on purpose
    return "```json\n" + json.dumps({
        "goal": "g",
        "fallback_response": "ask",
        "tool_chain": [
            {"tool": "get_account_transactions", "inputs": {"accountId": "XYZ"}}
        ]
    }) + "\n```"

@pytest.fixture(autouse=True)
def stub_llm(monkeypatch):
    monkeypatch.setattr(planner, "call_gemma3", fake_call_gemma3)
    return monkeypatch

def test_generate_plan_injects_local_filters(monkeypatch):
    # Simulate user having passed these filters
    user_inputs = {
        "startDate": "2024-04-01",
        "endDate":   "2024-04-30",
        "transactionName": "ATM Withdrawal",
        "accountId": "XYZ"
    }

    plan, missing = planner.plan(
        goal="g",
        objective="o",
        expected_outcome="e",
        memory={},            # no memory
        user_inputs=user_inputs
    )

    # We expect exactly one step, and that its inputs now include the 3 filters
    assert len(plan) == 1
    step = plan[0]

    assert step["tool"] == "get_account_transactions"
    for key in ("startDate", "endDate", "transactionName"):
        assert key in step["inputs"], f"{key!r} should be injected"
    
    # And missing should only refer to required inputs (accountId was present)
    assert missing == []
