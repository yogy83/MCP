import os
import sys
import json
import pytest

# Allow imports from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.aggregator as aggregator
from core.aggregator import clean, summarize_step, aggregate

@pytest.fixture(autouse=True)
def stub_llm(monkeypatch):
    """
    Stub call_gemma3 so that:
    - The first N calls (summaries) return "```text\nSummary for Step\n```"
    - The final call (overall) returns "Final overall summary."
    """
    calls = {"count": 0}

    def fake_call(prompt: str) -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            return "```text\nSummary for Step\n```"
        else:
            return "Final overall summary."

    monkeypatch.setattr(aggregator, "call_gemma3", fake_call)
    yield

def test_clean_removes_code_fences_and_strips():
    txt = " ```json\nHello```  "
    assert clean(txt) == "Hello"
    # case-insensitive
    assert clean("```TEXT world```") == "world"

def test_summarize_step_includes_filters_and_cleans():
    step_id = "1"
    result = {"foo": "bar"}
    local_filters = {"x": 123}
    summary = summarize_step(step_id, result, local_filters)
    assert isinstance(summary, str)
    assert len(summary) > 0
    # Optional: check that local_filters are somehow reflected - you can do regex on summary if you want

def test_summarize_step_no_filters():
    step_id = "2"
    result = {"a": 1}
    summary = summarize_step(step_id, result, {})
    assert isinstance(summary, str)
    assert len(summary) > 0

def test_aggregate_builds_keys_and_texts_and_summary():
    tool_outputs = [
        {
            "tool": "get_a",
            "api_inputs": {"foo": "A"},
            "local_filters": {"f": 1},
            "result": {"data": 10}
        },
        {
            "tool": "get_b",
            "api_inputs": {"bar": "B"},
            "local_filters": {},
            "result": {"data": 20}
        }
    ]
    expected_outcome = "Do something"

    agg = aggregate(tool_outputs, expected_outcome)

    # raw_result should mirror the 'result' fields
    assert "get_a_foo_A" in agg["raw_result"]
    assert "get_b_bar_B" in agg["raw_result"]
    assert agg["raw_result"]["get_a_foo_A"] == {"data": 10}
    assert agg["raw_result"]["get_b_bar_B"] == {"data": 20}

    # raw_text should contain non-empty strings for each key
    assert "get_a_foo_A" in agg["raw_text"]
    assert "get_b_bar_B" in agg["raw_text"]
    assert isinstance(agg["raw_text"]["get_a_foo_A"], str)
    assert len(agg["raw_text"]["get_a_foo_A"]) > 0
    assert isinstance(agg["raw_text"]["get_b_bar_B"], str)
    assert len(agg["raw_text"]["get_b_bar_B"]) > 0

    # summary should be a non-empty string
    assert isinstance(agg["summary"], str)
    assert len(agg["summary"]) > 0
