# core/memory.py

_session_memory = {}

def set_memory(key: str, value):
    _session_memory[key] = value

def get_memory(key: str, default=None):
    return _session_memory.get(key, default)

def clear_memory():
    _session_memory.clear()
