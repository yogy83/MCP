#!/usr/bin/env python3
import subprocess
import json
import requests
import sys
import re

OLLAMA_CMD = ["ollama", "run", "gemma3"]
MCP_URL    = "http://localhost:8000/process"

def sanitize(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```json"): raw = raw[len("```json"):]
    if raw.endswith("```"): raw = raw[:-3]
    return raw.strip()

def gemma(prompt: str) -> str:
    proc = subprocess.run(OLLAMA_CMD, input=prompt, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return sanitize(proc.stdout)

def plan_contract(user_request: str) -> dict:
    prompt = f"""
You are a banking assistant.  The user wants to do a _banking_ operation 
(like list accounts, check balance, view transactions).  Output EXACTLY one JSON object:

{{
  "goal": "...",
  "objective": "...",
  "expected_outcome": "..."
}}

Do not add any extra keys or text.
User request:
\"\"\"{user_request}\"\"\"
"""
    return json.loads(gemma(prompt))

def extract_memory(mcp_res: dict) -> dict:
    prompt = f"""
You are an assistant. Extract any new facts from this MCP JSON into simple key/value pairs.  
Return ONLY a JSON object, e.g. {{"accountCount":"3"}}, or {{}} if none.

MCP response:
{json.dumps(mcp_res, indent=2)}
"""
    return json.loads(gemma(prompt))

def summarise_mcp(user_request: str, mcp_res: dict) -> str:
    prompt = f"""
The user asked:
  "{user_request}"

The system returned:
{json.dumps(mcp_res, indent=2)}

Summarize for the user in one concise sentence, referencing their original request.
"""
    return gemma(prompt)

def is_chitchat(msg: str) -> bool:
    # very simple greeting/thanks detection
    return bool(re.search(r"\b(hi|hello|hey|thanks|thank you)\b", msg, re.I))

def main():
    # 1) Get numeric customer ID once
    print("Agent: Welcome! Please enter your numeric customer ID (or 'exit' to quit).")
    while True:
        cid = input("You: ").strip()
        if cid.lower() in ("exit","quit",""): 
            print("Agent: Goodbye!"); sys.exit(0)
        if cid.isdigit():
            memory = {"customerId": cid}
            break
        print("Agent: That’s not numeric. Please enter your digits-only customer ID.")

    print("Agent: Thank you! How can I help you today?")

    # 2–11) CLI chat loop
    while True:
        user = input("You: ").strip()
        if not user or user.lower() in ("exit","quit"):
            print("Agent: Goodbye!"); break

        # 2a) If pure chitchat, handle locally:
        if is_chitchat(user):
            # you can customize these replies
            reply = "Hi there! For account info I’ll go fetch that, otherwise happy to chat!"
            print("Agent:", reply)
            continue

        # 3) Plan the 3-field MCP payload
        contract = plan_contract(user)

        # 4–7) Call MCP, looping on missing parameters
        while True:
            payload = {**contract, **memory}
            print("Agent: Calling MCP with:")
            print(json.dumps(payload, indent=2))

            res = requests.post(MCP_URL, json=payload).json()

            if res.get("next_action") == "ask_user":
                prompt = res.get("prompt", "I need more info")
                for key in res.get("missing", []):
                    answer = input(f"Agent: {prompt} ({key}): ").strip()
                    memory[key] = answer
                # retry with updated memory (no re-plan)
                continue
            break

        # 8) Extract any new facts into memory
        new_mem = extract_memory(res)
        memory.update(new_mem)

        # 9) Summarize in context of the original question
        summary = summarise_mcp(user, res)
        print("Agent:", summary, "\n")

if __name__=="__main__":
    main()
