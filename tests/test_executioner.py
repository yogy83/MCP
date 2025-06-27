import os
import sys
import pytest

# Allow imports from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import executioner

def test_execute_plan_two_steps(monkeypatch):
    """
    A plan with two steps should invoke run_tool twice
    and return correct output for each step.
    """
    dummy_contracts = {
        "alpha": {"endpoint": "/dummy/alpha", "required_inputs": ["x"], "params": {"x": {"type": "string"}}},
        "beta":  {"endpoint": "/dummy/beta",  "required_inputs": ["y"], "params": {"y": {"type": "string"}}}
    }

    # Updated dummy_run_tool to accept 4 parameters
    def dummy_run_tool(tool_contract, inputs, request_schema=None, response_schema=None):
        if tool_contract["endpoint"] == "/dummy/alpha":
            return {"alpha_result": inputs}
        elif tool_contract["endpoint"] == "/dummy/beta":
            return {"beta_result": inputs}
        else:
            return {"unknown_tool": inputs}

    monkeypatch.setattr(executioner, "TOOL_CONTRACTS", dummy_contracts)
    monkeypatch.setattr(executioner, "run_tool", dummy_run_tool)

    plan = [
        {"tool": "alpha", "inputs": {"x": "1"}},
        {"tool": "beta",  "inputs": {"y": "2"}}
    ]

    out = executioner.execute_plan(plan)

    assert "step1" in out
    assert out["step1"] == {"alpha_result": {"x": "1"}}
    assert "step2" in out
    assert out["step2"] == {"beta_result": {"y": "2"}}

def test_execute_plan_propagates_exception(monkeypatch):
    """
    If run_tool raises an exception, execute_plan should propagate it.
    """
    dummy_contracts = {
        "gamma": {"endpoint": "/dummy/gamma", "required_inputs": ["z"], "params": {"z": {"type": "string"}}}
    }

    # Updated boom to accept 4 parameters
    def boom(tool_contract, inputs, request_schema=None, response_schema=None):
        raise RuntimeError(f"fail on {tool_contract['endpoint']}")

    monkeypatch.setattr(executioner, "TOOL_CONTRACTS", dummy_contracts)
    monkeypatch.setattr(executioner, "run_tool", boom)

    plan = [{"tool": "gamma", "inputs": {"z": "3"}}]

    with pytest.raises(RuntimeError) as exc:
        executioner.execute_plan(plan)

    assert "fail on /dummy/gamma" in str(exc.value)
