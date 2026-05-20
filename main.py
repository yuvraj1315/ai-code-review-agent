from core.pipeline import run_pipeline

repo_url = "https://github.com/pallets/flask"

results = run_pipeline(repo_url)

print(f"Findings: {len(results)}")

for r in results[:5]:
    print(r)