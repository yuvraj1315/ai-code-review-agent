import json
import streamlit as st
from groq import Groq

client = Groq(api_key=st.secrets["GROQ_API_KEY"])


def review_code(code_chunk):
    prompt = f"""
You are an expert Python code reviewer.

Return ONLY valid JSON:

{{
    "issue": "issue",
    "severity": "low|medium|high",
    "confidence": 0-100,
    "suggestion": "fix suggestion",
    "category": "security|performance|readability|reliability"
}}

Code:
{code_chunk}
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=300
        )

        content = response.choices[0].message.content.strip()

        start = content.find("{")
        end = content.rfind("}") + 1

        if start != -1:
            content = content[start:end]

        return json.loads(content)

    except Exception as e:
        print("Groq error:", e)

        return {
            "issue": "AI review failed",
            "severity": "low",
            "confidence": 10,
            "suggestion": str(e),
            "category": "reliability"
        }