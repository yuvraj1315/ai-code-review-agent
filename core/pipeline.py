from typing import List, Dict, Any
from pathlib import Path
import pandas as pd

from core.clone_repo import clone_repository
from core.file_scanner import scan_python_files
from core.parser import extract_code_chunks
from core.reviewer import review_code
from core.confidence import classify_confidence


def run_pipeline(repo_url: str) -> List[Dict[str, Any]]:
    results = []

    print("STEP 1: Cloning repo...")
    repo_path = clone_repository(repo_url)
    print("CLONED TO:", repo_path)

    print("STEP 2: Scanning files...")
    python_files = scan_python_files(repo_path)
    print("FILES FOUND:", len(python_files))
    print(python_files)

    python_files = python_files[:1]

    for file_path in python_files:
        print("PROCESSING FILE:", file_path)

        chunks = extract_code_chunks(file_path)
        print("CHUNKS FOUND:", len(chunks))

        if chunks:
            print("FIRST CHUNK:", chunks[0])

        for chunk in chunks[:2]:
            print("REVIEWING:", chunk["name"])

            review = review_code(chunk["code"])
            print("REVIEW RESULT:", review)

            confidence = review.get("confidence", 0)

            results.append({
                "file": chunk["file"],
                "line": chunk["line"],
                "type": chunk["type"],
                "name": chunk["name"],
                "issue": review.get("issue"),
                "severity": review.get("severity"),
                "confidence": confidence,
                "confidence_label": classify_confidence(confidence),
                "suggestion": review.get("suggestion"),
                "category": review.get("category")
            })

    Path("outputs").mkdir(exist_ok=True)
    pd.DataFrame(results).to_csv("outputs/review_results.csv", index=False)

    return results