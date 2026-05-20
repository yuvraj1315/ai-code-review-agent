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

    try:
        repo_path = clone_repository(repo_url)
        python_files = scan_python_files(repo_path)

        # Limit API usage for testing/demo
        python_files = python_files[:2]

        for file_path in python_files:
            try:
                chunks = extract_code_chunks(file_path)

                for chunk in chunks[:3]:

                    # Skip tiny wrapper/helper functions
                    if chunk["type"] == "function" and chunk["name"] in ["wrapper", "inner"]:
                        continue

                    review = review_code(chunk["code"])

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

            except Exception as e:
                print(f"Error processing {file_path}: {e}")

    except Exception as e:
        print(f"Pipeline failed: {e}")

    # Save CSV report
    try:
        outputs_dir = Path("outputs")
        outputs_dir.mkdir(exist_ok=True)

        df = pd.DataFrame(results)
        df.to_csv(outputs_dir / "review_results.csv", index=False)

    except Exception as e:
        print("CSV save failed:", e)

    return results