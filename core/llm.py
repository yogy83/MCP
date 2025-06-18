# core/llm.py

import subprocess

def call_gemma3(prompt: str) -> str:
    result = subprocess.run(
        ["ollama", "run", "gemma3:latest"],
        input=prompt,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return result.stdout.strip()
