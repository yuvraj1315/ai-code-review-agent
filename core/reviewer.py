import os
import json
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def review_code(code_chunk):
    prompt = f"""
You are an expert Python code reviewer.

Analyze the following code and return ONLY valid JSON.

Required JSON format:
{{
    "issue": "short issue description",
    "severity": "low|medium|high",
    "confidence": 0-100,
    "suggestion": "fix recommendation",
    "category": "security|performance|readability|reliability"
}}

Code:
{code_chunk}
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=300
        )

        content = response.choices[0].message.content.strip()

        start = content.find("{")
        end = content.rfind("}") + 1

        if start != -1 and end != -1:
            content = content[start:end]

        return json.loads(content)

    except Exception as e:
        print("Review error:", e)

        return {
            "issue": "AI review failed",
            "severity": "low",
            "confidence": 10,
            "suggestion": "Retry later or reduce scan size",
            "category": "reliability"
        }