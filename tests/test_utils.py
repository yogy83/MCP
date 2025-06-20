# tests/test_utils.py

import os
import sys
import json
import pytest
from pathlib import Path

# Ensure project root is on sys.path so `import core.utils` works
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.utils import load_tool_contracts_from_folder

def write_file(folder: Path, name: str, content: str):
    path = folder / name
    path.write_text(content)
    return path

def test_load_valid_contracts(tmp_path, capsys):
    # Create two valid JSON files
    good1 = {"tool_name": "tool1", "foo": 1}
    good2 = {"foo": 2}  # missing tool_name → key derived from filename

    folder = tmp_path / "contracts"
    folder.mkdir()

    write_file(folder, "a.json", json.dumps(good1))
    write_file(folder, "b.json", json.dumps(good2))
    # Also add a non-JSON file
    write_file(folder, "ignore.txt", "should be ignored")

    result = load_tool_contracts_from_folder(str(folder))

    # Expect two entries
    assert set(result.keys()) == {"tool1", "b"}
    assert result["tool1"]["foo"] == 1
    assert result["b"]["foo"] == 2

    # No error printed
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

def test_load_malformed_json_reports_error(tmp_path, capsys):
    folder = tmp_path / "contracts"
    folder.mkdir()

    # Good file
    write_file(folder, "good.json", json.dumps({"tool_name": "good"}))
    # Malformed JSON
    write_file(folder, "bad.json", "{ not valid json }")

    result = load_tool_contracts_from_folder(str(folder))

    # Only the good one loaded
    assert set(result.keys()) == {"good"}

    # Should have printed an error mentioning bad.json
    captured = capsys.readouterr()
    assert "Failed to load bad.json" in captured.out
    # JSON error messages vary, but always include the word "Expecting"
    assert "Expecting" in captured.out
