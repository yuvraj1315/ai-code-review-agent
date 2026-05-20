"""
reviewer.py — Production-grade Groq LLM reviewer.
Accepts chunk dicts from parser.py: {"code": str, "name": str, "type": str, "line": int, "file": str}
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from groq import Groq, APIError, APITimeoutError, RateLimitError

logger = logging.getLogger(__name__)

MAX_RETRIES = 4
INITIAL_BACKOFF = 1.0
BACKOFF_MULTIPLIER = 2.0
MAX_CHUNK_CHARS = 6_000
MODEL = "llama3-70b-8192"

SYSTEM_PROMPT = """You are a senior Python code reviewer. You review Python code and return
ONLY a JSON object — no markdown, no code fences, no extra text whatsoever.

Required JSON schema:
{
  "issues": [
    {
      "severity": "critical|high|medium|low|info",
      "category": "string",
      "description": "string",
      "line": "string or null",
      "suggestion": "string"
    }
  ],
  "summary": "string",
  "confidence": 0-100
}

If no issues found, return issues as an empty list with a short summary and confidence 90+.
Respond with ONLY the JSON object. No explanation before or after."""


def _build_fallback(filename: str, reason: str, chunk_name: str = "", chunk_type: str = "", chunk_line: int = 0) -> dict[str, Any]:
    return {
        "filename": filename,
        "chunk_name": chunk_name,
        "chunk_type": chunk_type,
        "chunk_line": chunk_line,
        "issues": [{
            "severity": "info",
            "category": "review_error",
            "description": f"Automated review could not be completed: {reason}",
            "line": str(chunk_line) if chunk_line else None,
            "suggestion": "Review this code manually or retry the analysis.",
        }],
        "summary": f"Review skipped — {reason}",
        "confidence": 0,
        "error": True,
    }


def _safe_parse_json(raw: str, filename: str) -> dict[str, Any] | None:
    if not raw or not raw.strip():
        return None
    # 1. Direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 2. Strip markdown fences
    stripped = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # 3. Extract first {...} block
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    logger.warning("[%s] Could not parse LLM response. Raw (first 300): %s", filename, raw[:300])
    return None


def _validate_review(data: dict[str, Any]) -> dict[str, Any]:
    data.setdefault("issues", [])
    data.setdefault("summary", "No summary provided.")
    data.setdefault("confidence", 50)
    cleaned = []
    for issue in data["issues"]:
        if not isinstance(issue, dict):
            continue
        cleaned.append({
            "severity": issue.get("severity", "info"),
            "category": issue.get("category", "general"),
            "description": issue.get("description", "No description."),
            "line": issue.get("line"),
            "suggestion": issue.get("suggestion", ""),
        })
    data["issues"] = cleaned
    return data


def review_chunk(
    client: Groq,
    chunk: dict[str, Any],
    filename: str,
    chunk_index: int = 0,
) -> dict[str, Any]:
    """
    Review a single chunk dict: {"code": str, "name": str, "type": str, "line": int}.
    Returns a validated review dict (never raises).
    """
    code = chunk.get("code", "")
    chunk_name = chunk.get("name", "unknown")
    chunk_type = chunk.get("type", "unknown")
    chunk_line = chunk.get("line", 0)

    if not code or not code.strip():
        logger.debug("[%s] chunk %d (%s) is empty — skipping.", filename, chunk_index, chunk_name)
        return {
            "filename": filename,
            "chunk_name": chunk_name,
            "chunk_type": chunk_type,
            "chunk_line": chunk_line,
            "issues": [],
            "summary": "Empty chunk — skipped.",
            "confidence": 100,
            "skipped": True,
        }

    if len(code) > MAX_CHUNK_CHARS:
        logger.warning("[%s] chunk '%s' truncated from %d to %d chars.",
                       filename, chunk_name, len(code), MAX_CHUNK_CHARS)
        code = code[:MAX_CHUNK_CHARS]

    user_message = (
        f"Review this Python {chunk_type} `{chunk_name}` from file `{filename}` "
        f"(starting at line {chunk_line}):\n\n"
        f"```python\n{code}\n```"
    )

    backoff = INITIAL_BACKOFF
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.debug("[%s] '%s' — attempt %d/%d", filename, chunk_name, attempt, MAX_RETRIES)

            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,
                max_tokens=1024,
            )

            raw = response.choices[0].message.content or ""
            parsed = _safe_parse_json(raw, filename)

            if parsed is None:
                logger.warning("[%s] '%s' attempt %d: non-JSON response.", filename, chunk_name, attempt)
                last_error = ValueError("Non-JSON LLM response")
                time.sleep(backoff)
                backoff = min(backoff * BACKOFF_MULTIPLIER, 30)
                continue

            validated = _validate_review(parsed)
            validated["filename"] = filename
            validated["chunk_name"] = chunk_name
            validated["chunk_type"] = chunk_type
            validated["chunk_line"] = chunk_line
            validated["error"] = False
            logger.info("[%s] '%s' reviewed — %d issue(s), confidence %s.",
                        filename, chunk_name, len(validated["issues"]), validated["confidence"])
            return validated

        except RateLimitError as exc:
            logger.warning("[%s] '%s' attempt %d: rate limit — waiting %.1fs",
                           filename, chunk_name, attempt, backoff)
            last_error = exc
            time.sleep(backoff)
            backoff = min(backoff * BACKOFF_MULTIPLIER, 60)

        except APITimeoutError as exc:
            logger.warning("[%s] '%s' attempt %d: timeout — waiting %.1fs",
                           filename, chunk_name, attempt, backoff)
            last_error = exc
            time.sleep(backoff)
            backoff = min(backoff * BACKOFF_MULTIPLIER, 30)

        except APIError as exc:
            logger.error("[%s] '%s' attempt %d: API error: %s", filename, chunk_name, attempt, exc)
            last_error = exc
            if hasattr(exc, "status_code") and exc.status_code and exc.status_code < 500:
                break
            time.sleep(backoff)
            backoff = min(backoff * BACKOFF_MULTIPLIER, 30)

        except Exception as exc:  # noqa: BLE001
            logger.exception("[%s] '%s' attempt %d: unexpected error: %s", filename, chunk_name, attempt, exc)
            last_error = exc
            break

    reason = str(last_error) if last_error else "Unknown error after retries"
    logger.error("[%s] '%s': all %d attempts failed. Reason: %s", filename, chunk_name, MAX_RETRIES, reason)
    return _build_fallback(filename, reason, chunk_name, chunk_type, chunk_line)


def review_file(
    client: Groq,
    chunks: list[dict[str, Any]],
    filename: str,
) -> list[dict[str, Any]]:
    """
    Review all chunks for a single file.
    chunks: list of dicts with keys: code, name, type, line, file
    Always returns a non-empty list.
    """
    if not chunks:
        logger.warning("[%s] No chunks provided.", filename)
        return [_build_fallback(filename, "No code chunks extracted from file")]

    results: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        result = review_chunk(client, chunk, filename, chunk_index=idx)
        results.append(result)

    real_reviews = [r for r in results if not r.get("skipped") and not r.get("error")]
    if not real_reviews and results:
        logger.warning("[%s] All chunks produced errors/skips — appending fallback.", filename)
        results.append(_build_fallback(filename, "All chunks skipped or errored"))

    return results