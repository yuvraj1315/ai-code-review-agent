"""
reviewer.py — Production-grade Groq LLM reviewer with retry, fallback, and safe JSON parsing.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from groq import Groq, APIError, APITimeoutError, RateLimitError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RETRIES = 4
INITIAL_BACKOFF = 1.0          # seconds
BACKOFF_MULTIPLIER = 2.0
MAX_CHUNK_CHARS = 6_000        # safety ceiling — Groq context limits
MODEL = "llama3-70b-8192"      # change to preferred model if needed

SYSTEM_PROMPT = """You are a senior Python code reviewer. You review Python code chunks and return
ONLY a JSON object — no markdown, no code fences, no extra text.

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

If no issues found, return issues as an empty list with a short summary and confidence 90+."""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_fallback(filename: str, reason: str) -> dict[str, Any]:
    """Return a sentinel review object when the LLM pipeline fails completely."""
    return {
        "filename": filename,
        "issues": [
            {
                "severity": "info",
                "category": "review_error",
                "description": f"Automated review could not be completed: {reason}",
                "line": None,
                "suggestion": "Review this file manually or retry the analysis.",
            }
        ],
        "summary": f"Review skipped — {reason}",
        "confidence": 0,
        "error": True,
    }


def _safe_parse_json(raw: str, filename: str) -> dict[str, Any] | None:
    """
    Aggressively extract a JSON object from raw LLM output.
    Returns None if no valid JSON object can be recovered.
    """
    if not raw or not raw.strip():
        logger.warning("[%s] Empty LLM response.", filename)
        return None

    # 1. Try direct parse first (happy path)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown code fences
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

    logger.warning("[%s] Could not parse LLM response as JSON. Raw (first 300 chars): %s",
                   filename, raw[:300])
    return None


def _validate_review(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure required keys exist with sane defaults."""
    data.setdefault("issues", [])
    data.setdefault("summary", "No summary provided.")
    data.setdefault("confidence", 50)

    # Normalise issues list
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


# ---------------------------------------------------------------------------
# Core review function
# ---------------------------------------------------------------------------


def review_chunk(
    client: Groq,
    chunk: str,
    filename: str,
    chunk_index: int = 0,
) -> dict[str, Any]:
    """
    Send a single code chunk to Groq for review.
    Returns a validated review dict (never raises).
    """
    # Skip empty / whitespace-only chunks
    stripped_chunk = chunk.strip()
    if not stripped_chunk:
        logger.debug("[%s] chunk %d is empty — skipping.", filename, chunk_index)
        return {
            "filename": filename,
            "issues": [],
            "summary": "Empty chunk — skipped.",
            "confidence": 100,
            "skipped": True,
        }

    # Truncate if needed
    if len(stripped_chunk) > MAX_CHUNK_CHARS:
        logger.warning("[%s] chunk %d truncated from %d to %d chars.",
                       filename, chunk_index, len(stripped_chunk), MAX_CHUNK_CHARS)
        stripped_chunk = stripped_chunk[:MAX_CHUNK_CHARS]

    user_message = (
        f"Review this Python code chunk from file `{filename}` (chunk {chunk_index}):\n\n"
        f"```python\n{stripped_chunk}\n```"
    )

    backoff = INITIAL_BACKOFF
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.debug("[%s] chunk %d — attempt %d/%d",
                         filename, chunk_index, attempt, MAX_RETRIES)

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
                # Non-JSON response — retry
                logger.warning("[%s] chunk %d attempt %d: non-JSON response.",
                               filename, chunk_index, attempt)
                last_error = ValueError("Non-JSON LLM response")
                time.sleep(backoff)
                backoff = min(backoff * BACKOFF_MULTIPLIER, 30)
                continue

            validated = _validate_review(parsed)
            validated["filename"] = filename
            validated["error"] = False
            logger.info("[%s] chunk %d reviewed — %d issues, confidence %s.",
                        filename, chunk_index,
                        len(validated["issues"]), validated["confidence"])
            return validated

        except RateLimitError as exc:
            logger.warning("[%s] chunk %d attempt %d: rate limit — waiting %.1fs",
                           filename, chunk_index, attempt, backoff)
            last_error = exc
            time.sleep(backoff)
            backoff = min(backoff * BACKOFF_MULTIPLIER, 60)

        except APITimeoutError as exc:
            logger.warning("[%s] chunk %d attempt %d: timeout — waiting %.1fs",
                           filename, chunk_index, attempt, backoff)
            last_error = exc
            time.sleep(backoff)
            backoff = min(backoff * BACKOFF_MULTIPLIER, 30)

        except APIError as exc:
            logger.error("[%s] chunk %d attempt %d: API error: %s",
                         filename, chunk_index, attempt, exc)
            last_error = exc
            # 4xx errors other than rate-limit are unlikely to recover — break early
            if hasattr(exc, "status_code") and exc.status_code and exc.status_code < 500:
                break
            time.sleep(backoff)
            backoff = min(backoff * BACKOFF_MULTIPLIER, 30)

        except Exception as exc:  # noqa: BLE001
            logger.exception("[%s] chunk %d attempt %d: unexpected error: %s",
                             filename, chunk_index, attempt, exc)
            last_error = exc
            break

    reason = str(last_error) if last_error else "Unknown error after retries"
    logger.error("[%s] chunk %d: all %d attempts failed. Using fallback. Reason: %s",
                 filename, chunk_index, MAX_RETRIES, reason)
    return _build_fallback(filename, reason)


# ---------------------------------------------------------------------------
# Public API: review an entire file (multiple chunks)
# ---------------------------------------------------------------------------


def review_file(
    client: Groq,
    chunks: list[str],
    filename: str,
) -> list[dict[str, Any]]:
    """
    Review all non-empty chunks for a single file.
    Always returns a list (never empty if chunks were provided).
    """
    if not chunks:
        logger.warning("[%s] No chunks provided.", filename)
        return [_build_fallback(filename, "No code chunks extracted from file")]

    results: list[dict[str, Any]] = []

    for idx, chunk in enumerate(chunks):
        result = review_chunk(client, chunk, filename, chunk_index=idx)
        results.append(result)

    # If every chunk was skipped or errored without producing real reviews, add fallback
    real_reviews = [r for r in results if not r.get("skipped") and not r.get("error")]
    if not real_reviews and results:
        logger.warning("[%s] All chunks produced errors/skips — appending fallback.", filename)
        results.append(_build_fallback(filename, "All chunks skipped or errored"))

    return results