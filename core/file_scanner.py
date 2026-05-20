import os

EXCLUDED_DIRS = {
    "venv",
    "__pycache__",
    ".git",
    "tests",
    "test",
    "docs",
    "examples",
    "site-packages"
}


def scan_python_files(repo_path):
    python_files = []

    for root, dirs, files in os.walk(repo_path):

        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                python_files.append(full_path)

    return python_files