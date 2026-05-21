"""
app.py — Production-grade Streamlit frontend for AI Code Review Agent.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import sys
import time

import streamlit as st

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)

from core.pipeline import PipelineResult, run_pipeline

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Code Review Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
SEVERITY_COLOURS = {
    "critical": "#FF4B4B",
    "high":     "#FF8C00",
    "medium":   "#FFA500",
    "low":      "#4CAF50",
    "info":     "#2196F3",
}
SEVERITY_EMOJI = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🟢",
    "info":     "🔵",
}

# ---------------------------------------------------------------------------
# Session state — initialise once
# ---------------------------------------------------------------------------
for _k, _v in {
    "result": None,
    "running": False,
    "last_repo_url": "",
    "run_id": 0,
    "elapsed": 0.0,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _to_csv(findings: list[dict]) -> bytes:
    if not findings:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[
        "filename", "chunk_name", "chunk_type", "severity",
        "category", "description", "line", "suggestion", "confidence", "summary"
    ], extrasaction="ignore")
    writer.writeheader()
    writer.writerows(findings)
    return buf.getvalue().encode("utf-8")

def _to_json(findings: list[dict]) -> bytes:
    return json.dumps(findings, indent=2, default=str).encode("utf-8")

def _to_markdown(findings: list[dict], repo_url: str) -> bytes:
    lines = [
        "# AI Code Review Report",
        f"**Repository:** {repo_url}",
        f"**Total findings:** {len(findings)}",
        "", "---", "",
    ]
    for i, f in enumerate(findings, 1):
        sev = (f.get("severity") or "info").lower()
        emoji = SEVERITY_EMOJI.get(sev, "🔵")
        lines += [
            f"## {i}. {emoji} [{sev.upper()}] `{f.get('filename', 'unknown')}`",
            f"- **Function/Class:** `{f.get('chunk_name', '—')}` ({f.get('chunk_type', '—')})",
            f"- **Category:** {f.get('category', '—')}",
            f"- **Line:** {f.get('line') or f.get('chunk_line') or '—'}",
            f"- **Confidence:** {f.get('confidence', 0)}%",
            "",
            f"**Description:** {f.get('description', '')}",
            "",
            f"**Suggestion:** {f.get('suggestion', '')}",
            "", "---", "",
        ]
    return "\n".join(lines).encode("utf-8")

# ---------------------------------------------------------------------------
# Sidebar — always rendered, reads from session_state
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Control Panel")

    repo_url: str = st.text_input(
        "GitHub Repository URL",
        value=st.session_state.last_repo_url or "",
        placeholder="https://github.com/owner/repo",
        key="repo_url_input",
    )

    severity_filter: str = st.selectbox(
        "Severity Filter",
        options=["All", "critical", "high", "medium", "low", "info"],
        index=0,
        key="severity_filter_input",
    )

    min_confidence: int = st.slider(
        "Minimum Confidence",
        min_value=0, max_value=100, value=60, step=5,
        key="min_confidence_input",
        help="Drop findings where AI confidence is below this threshold.",
    )

    analyze_clicked = st.button(
        "🚀 Analyze Repository",
        disabled=st.session_state.running,
        use_container_width=True,
    )

    # Category filter — only shown after results exist
    current_result: PipelineResult | None = st.session_state.result
    category_filter = "All"
    if current_result and current_result.findings:
        st.divider()
        st.markdown("**Filter by Category**")
        all_categories = sorted({f.get("category", "general") for f in current_result.findings})
        category_filter = st.selectbox(
            "Category",
            options=["All"] + all_categories,
            key="category_filter_input",
        )

    st.divider()
    st.caption("AI Code Review Agent — powered by Groq LLM + AST analysis")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);
                border-radius:12px;padding:2rem;margin-bottom:1.5rem;text-align:center;">
        <h1 style="color:#fff;margin:0;">🤖 AI Code Review Agent</h1>
        <p style="color:#aaa;margin-top:.5rem;">
            Autonomous AI-powered code analysis using AST parsing and intelligent review pipeline
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Pipeline execution — runs synchronously, stores result in session_state
# ---------------------------------------------------------------------------
if analyze_clicked and not st.session_state.running:
    url = (repo_url or "").strip()
    if not url:
        st.error("Please enter a GitHub repository URL.")
    else:
        # Mark as running and store URL before rerun
        st.session_state.running = True
        st.session_state.last_repo_url = url
        st.session_state.result = None
        st.session_state.run_id += 1

        status_ph = st.empty()
        bar_ph = st.progress(0.0)

        def _progress(msg: str, pct: float) -> None:
            try:
                status_ph.info(f"⏳ {msg}")
                bar_ph.progress(float(min(max(pct, 0.0), 1.0)))
            except Exception:
                pass

        _progress("Starting pipeline...", 0.01)
        t0 = time.time()

        try:
            pipeline_result = run_pipeline(
                repo_url=url,
                min_confidence=min_confidence,
                severity_filter=severity_filter if severity_filter != "All" else None,
                progress_callback=_progress,
            )
        except Exception as exc:
            logger.exception("run_pipeline raised: %s", exc)
            pipeline_result = PipelineResult()
            pipeline_result.errors.append(f"Critical pipeline failure: {exc}")

        st.session_state.elapsed = round(time.time() - t0, 1)
        st.session_state.result = pipeline_result
        st.session_state.running = False

        bar_ph.progress(1.0)
        status_ph.success(
            f"✅ Analysis complete in {st.session_state.elapsed}s — "
            f"{pipeline_result.summary_line()}"
        )
        logger.info("Pipeline done in %ss — %s", st.session_state.elapsed, pipeline_result.summary_line())
        # Small pause so user sees the success message before results render
        time.sleep(0.5)
        st.rerun()

# ---------------------------------------------------------------------------
# Results rendering
# ---------------------------------------------------------------------------
result: PipelineResult | None = st.session_state.result

if result is None:
    st.info("Enter a GitHub repository URL and click **Analyze Repository** to begin.")
    st.stop()

# Show completion banner
if result.success and result.findings:
    st.success(
        f"✅ Analysis complete in {st.session_state.elapsed}s — {result.summary_line()}"
    )

# Errors
if result.errors:
    for err in result.errors:
        st.error(f"🚨 **Pipeline Error**\n\n{err}")

# Warnings
if result.warnings:
    with st.expander(f"⚠️ {len(result.warnings)} Warning(s)", expanded=not result.findings):
        for w in result.warnings:
            st.warning(w)

# Stats
if result.stats:
    c1, c2, c3, c4 = st.columns(4)
    for col, (key, label) in zip(
        [c1, c2, c3, c4],
        [("files_found","📁 Files Found"),("files_reviewed","🔍 Files Reviewed"),
         ("raw_findings","📋 Raw Findings"),("filtered_findings","✅ Filtered Findings")]
    ):
        col.metric(label, result.stats.get(key, 0))

st.divider()

if not result.findings:
    if result.success and not result.errors:
        st.success("✅ No findings matched the current filters. Try lowering Minimum Confidence or changing Severity Filter.")
    elif result.errors:
        st.error("Pipeline encountered errors. See details above.")
    else:
        st.warning("No findings generated. See warnings above for details.")
    st.stop()

# ---------------------------------------------------------------------------
# Apply filters + sort
# ---------------------------------------------------------------------------
display_findings = result.findings

if severity_filter != "All":
    display_findings = [f for f in display_findings
                        if (f.get("severity") or "info").lower() == severity_filter.lower()]

if category_filter != "All":
    display_findings = [f for f in display_findings
                        if f.get("category", "general") == category_filter]

sorted_findings = sorted(
    display_findings,
    key=lambda f: (
        SEVERITY_ORDER.get((f.get("severity") or "info").lower(), 99),
        -(f.get("confidence") or 0),
    ),
)

# ---------------------------------------------------------------------------
# Download bar
# ---------------------------------------------------------------------------
st.subheader(f"🔎 {len(sorted_findings)} Finding(s)")

repo_slug = (st.session_state.last_repo_url or "findings").rstrip("/").split("/")[-1] or "findings"

dl1, dl2, dl3, _ = st.columns([1, 1, 1, 3])
with dl1:
    st.download_button("⬇️ Download CSV", data=_to_csv(sorted_findings),
                       file_name=f"{repo_slug}_review.csv", mime="text/csv",
                       use_container_width=True)
with dl2:
    st.download_button("⬇️ Download JSON", data=_to_json(sorted_findings),
                       file_name=f"{repo_slug}_review.json", mime="application/json",
                       use_container_width=True)
with dl3:
    st.download_button("⬇️ Download Markdown", data=_to_markdown(sorted_findings, st.session_state.last_repo_url),
                       file_name=f"{repo_slug}_review.md", mime="text/markdown",
                       use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Findings list
# ---------------------------------------------------------------------------
for idx, finding in enumerate(sorted_findings, start=1):
    severity = (finding.get("severity") or "info").lower()
    colour = SEVERITY_COLOURS.get(severity, "#888")
    emoji = SEVERITY_EMOJI.get(severity, "🔵")
    filename = finding.get("filename", "unknown")
    chunk_name = finding.get("chunk_name", "")
    chunk_type = finding.get("chunk_type", "")
    category = finding.get("category", "general")
    description = finding.get("description", "No description.")
    suggestion = finding.get("suggestion", "")
    line = finding.get("line") or finding.get("chunk_line")
    confidence = finding.get("confidence", 0)
    summary = finding.get("summary", "")
    line_str = f"Line {line}" if line else "—"

    with st.expander(
        f"{emoji} [{severity.upper()}] {filename} — {category} ({line_str})",
        expanded=(severity in ("critical", "high")),
    ):
        left, right = st.columns([3, 1])
        with left:
            st.markdown(
                f"<span style='color:{colour};font-weight:700;font-size:1.05rem;'>"
                f"{emoji} {severity.capitalize()}</span>",
                unsafe_allow_html=True,
            )
            if chunk_name and chunk_name not in ("unknown", ""):
                st.markdown(f"**{chunk_type.replace('_',' ').title()}:** `{chunk_name}`")
            st.markdown(f"**Description:** {description}")
            if suggestion:
                st.markdown(f"**Suggestion:** {suggestion}")
            if summary:
                st.caption(f"Summary: {summary}")
        with right:
            st.metric("Confidence", f"{confidence}%")
            st.caption(f"File: `{filename}`")
            if line:
                st.caption(f"Line: `{line}`")
            if chunk_name and chunk_name not in ("unknown", ""):
                st.caption(f"Function: `{chunk_name}`")

# ---------------------------------------------------------------------------
# Debug expander
# ---------------------------------------------------------------------------
with st.expander("🛠️ Debug Info", expanded=False):
    st.json({
        "run_id": st.session_state.run_id,
        "repo_url": st.session_state.last_repo_url,
        "elapsed_s": st.session_state.elapsed,
        "min_confidence": min_confidence,
        "severity_filter": severity_filter,
        "category_filter": category_filter,
        "pipeline_success": result.success,
        "stats": result.stats,
        "total_findings": len(result.findings),
        "displayed_findings": len(sorted_findings),
        "error_count": len(result.errors),
        "warning_count": len(result.warnings),
        "groq_api_key_set": bool(os.environ.get("GROQ_API_KEY")),
    })