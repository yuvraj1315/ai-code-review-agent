import ast


def extract_code_chunks(file_path):
    chunks = []

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        tree = ast.parse(code)

        for node in ast.walk(tree):

            if isinstance(node, ast.FunctionDef):
                source = ast.get_source_segment(code, node)

                chunks.append({
                    "type": "function",
                    "name": node.name,
                    "line": node.lineno,
                    "file": file_path,
                    "code": source[:3000] if source else ""
                })

            elif isinstance(node, ast.AsyncFunctionDef):
                source = ast.get_source_segment(code, node)

                chunks.append({
                    "type": "async_function",
                    "name": node.name,
                    "line": node.lineno,
                    "file": file_path,
                    "code": source[:3000] if source else ""
                })

            elif isinstance(node, ast.ClassDef):
                source = ast.get_source_segment(code, node)

                chunks.append({
                    "type": "class",
                    "name": node.name,
                    "line": node.lineno,
                    "file": file_path,
                    "code": source[:3000] if source else ""
                })

    except Exception as e:
        print(f"Parser error in {file_path}: {e}")

    return chunks