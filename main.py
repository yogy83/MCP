import uuid
import json
import requests
import subprocess

# --- Session Initialization ---
session_id = str(uuid.uuid4())
memory = {}
DEBUG_MODE = True

# --- Logging ---
def debug_log(msg):
    if DEBUG_MODE:
        print(f"[DEBUG] {msg}")

# --- Gemma Interaction ---
def sanitize(raw):
    raw = raw.strip()
    if raw.startswith("```json"):
        return raw.removeprefix("```json").removesuffix("```" ).strip()
    elif raw.startswith("```"):
        return raw.removeprefix("```" ).removesuffix("```" ).strip()
    return raw

def gemma(prompt):
    debug_log(f"Prompt sent to Gemma:\n{prompt}")
    result = subprocess.run(["ollama", "run", "gemma3"], input=prompt, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    output = result.stdout.strip()
    debug_log(f"Gemma raw output:\n{output}")
    return output

# --- Prompt Contracts ---
def prompt_to_contract(user_input):
    prompt = f"""
You are a helpful assistant tasked with generating the user's goal, objective, and expected outcome based on this input: \"{user_input}\".
Return a JSON object:
{{
  "goal": "...",
  "objective": "...",
  "expected_outcome": "..."
}}
Avoid numeric/hallucinated fields.
"""
    return json.loads(sanitize(gemma(prompt)))

def extract_memory_via_llm(user_input, missing_keys):
    prompt = f"""
You are a smart assistant. Extract relevant values for the following fields from the user's response.
User input: "{user_input}"
Fields required: {missing_keys}
Return a JSON object with extracted memory like: {{"accountId": "105929"}}
Only include keys you are confident about.
"""
    return json.loads(sanitize(gemma(prompt)))

# --- MCP Interaction ---
def mcp_request(goal, objective, outcome, mem):
    payload = {
        "goal": goal,
        "objective": objective,
        "expected_outcome": outcome,
        "memory": mem,
        "history": [],
        "last_execution_results": {},
        "conversation_context": {},
        "session_id": session_id
    }
    debug_log(f"Sending to MCP:\n{json.dumps(payload, indent=2)}")
    res = requests.post("http://localhost:8000/process", json=payload)
    response = res.json()
    debug_log(f"MCP response:\n{json.dumps(response, indent=2)}")
    return response

# --- Final Summary ---
def summarize_final_result(result):
    prompt = f"""
You are a banking assistant. Summarize the following MCP result for the user:

{json.dumps(result, indent=2)}

Return only a short user-friendly summary.
"""
    return gemma(prompt)

# --- Agent Loop ---
def agent_loop(user_input):
    contract = prompt_to_contract(user_input)
    goal, objective, expected_outcome = contract.values()

    def step(goal, objective, expected_outcome, memory):
        response = mcp_request(goal, objective, expected_outcome, memory)

        action_prompt = f"""
You are a smart assistant. Given the user's goal and the system response, decide the next action.

Goal: {goal}
Objective: {objective}
Expected Outcome: {expected_outcome}

MCP Response:
{json.dumps(response, indent=2)}

Current Memory:
{json.dumps(memory, indent=2)}

What should the assistant do next? Respond in JSON:
{{
  "action": "ask_user | update_memory | replan | exit | summarize",
  "prompt": "<if ask_user>",
  "memory_update": {{ <key>: <value> }}
}}
"""
        decision = json.loads(sanitize(gemma(action_prompt)))
        memory.update(decision.get("memory_update", {}))

        actions = {
            "ask_user": lambda: input(f"Agent: {decision['prompt']}\nYou: "),
            "update_memory": lambda: None,
            "replan": lambda: step(goal, objective, expected_outcome, memory),
            "summarize": lambda: print("Agent:", summarize_final_result(response.get("raw_result", {}))),
            "exit": lambda: print("Agent: Goodbye!")
        }

        user_reply = actions.get(decision["action"], lambda: None)()
        if decision["action"] == "ask_user" and user_reply:
            memory.update(extract_memory_via_llm(user_reply, response.get("missing", [])))
            step(goal, objective, expected_outcome, memory)

    step(goal, objective, expected_outcome, memory)

# --- Main Entry ---
def main():
    print("Agent started. Type 'exit' to quit.")
    try:
        user_input = input("You: ")
        if user_input.lower() != "exit":
            agent_loop(user_input)
    except KeyboardInterrupt:
        print("\nAgent stopped.")

if __name__ == "__main__":
    main()
