"""
pipeline.py — Production-grade orchestration pipeline.
Never silently returns an empty findings list.
"""

from __future__ import annotations

import logging
import os
import shutil
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from groq import Groq

# Local modules — using actual function names from each file
from core.clone_repo import clone_repository   # clone_repository(url) -> str (path)
from core.file_scanner import scan_python_files # scan_python_files(repo_path) -> list[str]
from core.parser import extract_code_chunks     # extract_code_chunks(file_path) -> list[str]
from core.reviewer import review_file

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PipelineResult:
    findings: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    success: bool = False

    def has_findings(self) -> bool:
        return bool(self.findings)

    def summary_line(self) -> str:
        n = len(self.findings)
        files = self.stats.get("files_reviewed", 0)
        return f"{n} finding(s) across {files} file(s)."


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_groq_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY environment variable is missing or empty. "
            "Set it in Streamlit Cloud secrets or your .env file."
        )
    return Groq(api_key=api_key)


def _flatten_file_results(
    file_results: list[dict[str, Any]],
    min_confidence: int,
) -> list[dict[str, Any]]:
    """
    Flatten chunk-level results into a single findings list,
    applying confidence filter and ensuring required keys.
    """
    findings: list[dict[str, Any]] = []
    for result in file_results:
        confidence = result.get("confidence", 0)
        if confidence < min_confidence and not result.get("error"):
            logger.debug("Skipping result for '%s' — confidence %d < %d",
                         result.get("filename"), confidence, min_confidence)
            continue

        for issue in result.get("issues", []):
            findings.append({
                "filename": result.get("filename", "unknown"),
                "severity": issue.get("severity", "info"),
                "category": issue.get("category", "general"),
                "description": issue.get("description", ""),
                "line": issue.get("line"),
                "suggestion": issue.get("suggestion", ""),
                "confidence": confidence,
                "summary": result.get("summary", ""),
            })

    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_pipeline(
    repo_url: str,
    min_confidence: int = 60,
    severity_filter: str | None = None,
    progress_callback: Callable[[str, float], None] | None = None,
) -> PipelineResult:
    """
    Full end-to-end pipeline.

    Args:
        repo_url:          GitHub repository URL.
        min_confidence:    Drop findings below this confidence score (0–100).
        severity_filter:   If set, keep only findings with this severity level.
        progress_callback: Optional callable(message: str, pct: float) for UI updates.

    Returns:
        PipelineResult — always populated; never silently empty.
    """

    def _progress(msg: str, pct: float = 0.0) -> None:
        logger.info("[pipeline] %.0f%% — %s", pct * 100, msg)
        if progress_callback:
            try:
                progress_callback(msg, pct)
            except Exception:  # noqa: BLE001
                pass  # UI callback failures must not kill the pipeline

    result = PipelineResult()
    tmp_dir: str | None = None

    try:
        # ------------------------------------------------------------------
        # 1. Validate inputs
        # ------------------------------------------------------------------
        repo_url = (repo_url or "").strip()
        if not repo_url:
            result.errors.append("Repository URL is empty.")
            return result

        if not repo_url.startswith(("https://", "http://", "git@")):
            result.errors.append(f"Invalid repository URL: {repo_url!r}")
            return result

        # ------------------------------------------------------------------
        # 2. Initialise Groq client early — fail fast if key is missing
        # ------------------------------------------------------------------
        _progress("Initialising AI client…", 0.02)
        try:
            client = _get_groq_client()
        except EnvironmentError as exc:
            result.errors.append(str(exc))
            return result

        # ------------------------------------------------------------------
        # 3. Clone repository
        # ------------------------------------------------------------------
        _progress(f"Cloning {repo_url}…", 0.05)

        try:
            tmp_dir = clone_repository(repo_url)   # manages its own temp dir
            if not tmp_dir:
                result.errors.append(
                    f"clone_repository() returned empty path for URL: {repo_url}. "
                    "Check network access and repository visibility."
                )
                return result
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"Cloning failed: {exc}\n{traceback.format_exc()}")
            return result

        # ------------------------------------------------------------------
        # 4. Scan for Python files
        # ------------------------------------------------------------------
        _progress("Scanning for Python files…", 0.15)
        try:
            python_files: list[str] = scan_python_files(tmp_dir)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"File scanning failed: {exc}\n{traceback.format_exc()}")
            return result

        if not python_files:
            result.warnings.append(
                "No Python files found in this repository. "
                "The repo may not contain .py files or may be empty."
            )
            result.success = True  # Not a pipeline error — repo just has no Python
            result.stats["files_found"] = 0
            return result

        result.stats["files_found"] = len(python_files)
        _progress(f"Found {len(python_files)} Python file(s).", 0.20)

        # ------------------------------------------------------------------
        # 5. Parse + review each file
        # ------------------------------------------------------------------
        all_findings: list[dict[str, Any]] = []
        files_reviewed = 0
        files_with_errors = 0

        for file_idx, filepath in enumerate(python_files):
            pct = 0.20 + 0.70 * (file_idx / len(python_files))
            short_path = filepath.replace(tmp_dir, "").lstrip("/\\")
            _progress(f"Reviewing {short_path}…", pct)

            # Parse
            try:
                chunks: list[str] = extract_code_chunks(filepath)
            except Exception as exc:  # noqa: BLE001
                warn = f"AST parsing failed for {short_path}: {exc}"
                logger.warning(warn)
                result.warnings.append(warn)
                files_with_errors += 1
                continue

            if not chunks:
                logger.debug("No chunks extracted from %s — skipping.", short_path)
                result.warnings.append(f"No code chunks extracted from {short_path}.")
                continue

            # Non-empty chunks — send to reviewer
            try:
                file_reviews = review_file(client, chunks, short_path)
            except Exception as exc:  # noqa: BLE001
                warn = f"Review failed for {short_path}: {exc}"
                logger.error("%s\n%s", warn, traceback.format_exc())
                result.warnings.append(warn)
                files_with_errors += 1
                continue

            file_findings = _flatten_file_results(file_reviews, min_confidence)
            all_findings.extend(file_findings)
            files_reviewed += 1

        result.stats["files_reviewed"] = files_reviewed
        result.stats["files_with_errors"] = files_with_errors
        result.stats["raw_findings"] = len(all_findings)

        # ------------------------------------------------------------------
        # 6. Apply severity filter
        # ------------------------------------------------------------------
        if severity_filter and severity_filter.lower() not in ("all", ""):
            before = len(all_findings)
            all_findings = [
                f for f in all_findings
                if f.get("severity", "").lower() == severity_filter.lower()
            ]
            logger.info("Severity filter '%s': %d → %d findings.",
                        severity_filter, before, len(all_findings))

        result.stats["filtered_findings"] = len(all_findings)

        # ------------------------------------------------------------------
        # 7. Guard: if we reviewed files but got zero findings after filtering
        # ------------------------------------------------------------------
        if files_reviewed > 0 and not all_findings:
            result.warnings.append(
                f"Analysis completed but no findings matched the current filters "
                f"(min_confidence={min_confidence}, severity={severity_filter or 'all'}). "
                "Try lowering the Minimum Confidence slider or changing the Severity Filter."
            )

        result.findings = all_findings
        result.success = True
        _progress(f"Done — {result.summary_line()}", 1.0)

    except Exception as exc:  # noqa: BLE001
        # Top-level safety net — should never fire, but prevents blank UI
        result.errors.append(
            f"Unexpected pipeline error: {exc}\n{traceback.format_exc()}"
        )
        logger.critical("Unhandled pipeline exception: %s", exc, exc_info=True)

    finally:
        # Always clean up cloned repo
        if tmp_dir and os.path.exists(tmp_dir):
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass

    return result