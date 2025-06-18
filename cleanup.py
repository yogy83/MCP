
import os
import shutil

TARGETS = [
    "/Users/yogeshg/Documents/PY/T_mcp/.venv",
]

# Common clutter patterns
EXTRA_CLEANUP = [
    "__pycache__",
    ".DS_Store",
    "*.pyc",
    "*.pyo",
    "*.log"
]

def delete_path(path):
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
            print(f"🗑️ Deleted folder: {path}")
        elif os.path.isfile(path):
            os.remove(path)
            print(f"🗑️ Deleted file: {path}")
    except Exception as e:
        print(f"❌ Failed to delete {path}: {e}")

def clean_extra(directory="."):
    for root, dirs, files in os.walk(directory):
        for name in dirs + files:
            full_path = os.path.join(root, name)
            if (
                name == "__pycache__" or
                name == ".DS_Store" or
                name.endswith(".pyc") or
                name.endswith(".pyo") or
                name.endswith(".log")
            ):
                delete_path(full_path)

def main():
    for target in TARGETS:
        if os.path.exists(target):
            confirm = input(f"Are you sure you want to delete {target}? (yes/no): ")
            if confirm.lower() == 'yes':
                delete_path(target)
            else:
                print(f"Skipping {target}")
        else:
            print(f"{target} not found.")

    print("\n🔍 Scanning for extra clutter...")
    clean_extra("T_mcp")

if __name__ == "__main__":
    main()
