import subprocess
import json
import re
from core.llm import call_gemma3

def clean(text: str) -> str:
    return re.sub(r"```(?:json|text)?", "", text, flags=re.IGNORECASE).strip()

def summarize_step(step_id: str, step_result: dict, local_filters: dict) -> str:
    filters_desc = ""
    if local_filters:
        filters_desc = f" Filters applied locally: {json.dumps(local_filters)}."

    step_prompt = f"""
You are a banking assistant. Summarize the result below for step {step_id} in 1-2 lines in plain English.{filters_desc}

{json.dumps(step_result, indent=2)}

Avoid technical jargon. Keep it simple.
"""
    return clean(call_gemma3(step_prompt))

def aggregate(tool_outputs: list, expected_outcome: str) -> dict:
    result_summary = {}
    result_texts = {}

    for i, step in enumerate(tool_outputs):
        tool = step.get("tool")
        api_inputs = step.get("api_inputs", {})
        local_filters = step.get("local_filters", {})
        output = step.get("result")

        # Construct a key for storing step results and summaries
        key = f"{tool}_" + "_".join(f"{k}_{v}" for k, v in api_inputs.items())
        key = key.replace(" ", "")

        # Summarize each step with local filter info included
        response = summarize_step(f"Step {i+1}", output, local_filters)

        result_summary[key] = output
        result_texts[key] = response.strip()

    # Prepare full context for final summary
    full_context = "\n".join([f"{k}: {v}" for k, v in result_texts.items()])
    prompt = f"""
You are an aggregator providing a response to a MCP requestor, who is usually an AI agent.
Based on the following tool outputs:

{full_context}

Please summarize the information in 2 concise and friendly sentences aligned with this goal: {expected_outcome}.
Focus on being clear and informative, and mention if any local filtering was applied.
Do not ask for further inputs or mention uploading documents.
"""
    final_summary = call_gemma3(prompt).strip()

    return {
        "summary": final_summary,
        "raw_result": result_summary,
        "raw_text": result_texts
    }
