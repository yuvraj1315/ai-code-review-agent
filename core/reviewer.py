import os
import json
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def review_code(code_chunk):
    # truncate huge code chunks
    if len(code_chunk) > 3000:
        code_chunk = code_chunk[:3000]

    prompt = f"""
You are a senior software engineer.

Analyze this Python code.

Return ONLY JSON.

Schema:

{{
  "issue": "short issue",
  "severity": "low/medium/high",
  "confidence": 0,
  "suggestion": "fix recommendation",
  "category": "bug/security/performance/readability/reliability"
}}

No markdown.
No explanation.
JSON only.

Code:
{code_chunk}
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=250
        )

        result = response.choices[0].message.content.strip()

        # remove markdown wrappers
        if "```" in result:
            result = result.replace("```json", "")
            result = result.replace("```", "")
            result = result.strip()

        # isolate JSON object safely
        start = result.find("{")
        end = result.rfind("}") + 1

        result = result[start:end]

        parsed = json.loads(result)

        return {
            "issue": parsed.get("issue", "Potential issue detected"),
            "severity": parsed.get("severity", "medium").lower(),
            "confidence": int(parsed.get("confidence", 50)),
            "suggestion": parsed.get("suggestion", "Manual review recommended"),
            "category": parsed.get("category", "readability").lower()
        }

    except Exception as e:
     if "429" in str(e):
        return {
            "issue": "API rate limit reached",
            "severity": "low",
            "confidence": 10,
            "suggestion": "Retry later or reduce scan size",
            "category": "reliability"
        }

    print("Review error:", e)

    return {
            "issue": "AI review failed — manual verification required",
            "severity": "low",
            "confidence": 20,
            "suggestion": "Check this code manually",
            "category": "reliability"
        }