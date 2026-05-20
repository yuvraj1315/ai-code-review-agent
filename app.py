"""
app.py — Production-grade Streamlit frontend for AI Code Review Agent.
Fixes: state bugs, silent empty results, missing error/warning surfaces.
"""

from __future__ import annotations

import logging
import os
import sys
import time

import streamlit as st

# ---------------------------------------------------------------------------
# Logging — configure before any local imports so pipeline logs are visible
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local imports
# ---------------------------------------------------------------------------

from pipeline import PipelineResult, run_pipeline  # noqa: E402

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI Code Review Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
SEVERITY_COLOURS = {
    "critical": "#FF4B4B",
    "high":     "#FF8C00",
    "medium":   "#FFA500",
    "low":      "#4CAF50",
    "info":     "#2196F3",
}

# ---------------------------------------------------------------------------
# Session-state initialisation
# Calling this once at import-time prevents KeyError on rerun.
# ---------------------------------------------------------------------------

def _init_state() -> None:
    defaults: dict = {
        "result": None,           # PipelineResult | None
        "running": False,         # True while pipeline is executing
        "last_repo_url": "",      # Detect URL changes
        "run_id": 0,              # Incremented per run to bust stale cache
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()

# ---------------------------------------------------------------------------
# Sidebar — controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("⚙️ Control Panel")

    repo_url: str = st.text_input(
        "GitHub Repository URL",
        value=st.session_state.last_repo_url or "",
        placeholder="https://github.com/owner/repo",
        key="repo_url_input",
    )

    severity_options = ["All", "critical", "high", "medium", "low", "info"]
    severity_filter: str = st.selectbox(
        "Severity Filter",
        options=severity_options,
        index=0,
        key="severity_filter_input",
    )

    min_confidence: int = st.slider(
        "Minimum Confidence",
        min_value=0,
        max_value=100,
        value=60,
        step=5,
        key="min_confidence_input",
        help="Drop findings where the AI confidence is below this threshold.",
    )

    analyze_clicked = st.button(
        "🚀 Analyze Repository",
        disabled=st.session_state.running,
        use_container_width=True,
    )

    st.divider()
    st.caption("AI Code Review Agent — powered by Groq LLM + AST analysis")

# ---------------------------------------------------------------------------
# Main content header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div style="background: linear-gradient(135deg,#1a1a2e,#16213e);
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
# Handle Analyze button click — trigger pipeline
# ---------------------------------------------------------------------------

if analyze_clicked:
    url = (repo_url or "").strip()
    if not url:
        st.error("Please enter a GitHub repository URL.")
    else:
        # Reset state for this run
        st.session_state.result = None
        st.session_state.running = True
        st.session_state.last_repo_url = url
        st.session_state.run_id += 1

        # ---- Progress placeholders ----
        status_box = st.empty()
        progress_bar = st.progress(0.0)

        def _update_progress(message: str, pct: float) -> None:
            try:
                status_box.info(f"⏳ {message}")
                progress_bar.progress(min(max(pct, 0.0), 1.0))
            except Exception:  # noqa: BLE001
                pass  # UI updates are best-effort

        _update_progress("Starting pipeline…", 0.01)

        t0 = time.time()
        try:
            pipeline_result: PipelineResult = run_pipeline(
                repo_url=url,
                min_confidence=min_confidence,
                severity_filter=severity_filter if severity_filter != "All" else None,
                progress_callback=_update_progress,
            )
        except Exception as exc:
            # Absolute last-resort catch
            logger.exception("run_pipeline raised unexpectedly: %s", exc)
            pipeline_result = PipelineResult()
            pipeline_result.errors.append(
                f"Critical pipeline failure: {exc}. Check logs for traceback."
            )

        elapsed = time.time() - t0
        st.session_state.result = pipeline_result
        st.session_state.running = False

        progress_bar.progress(1.0)
        status_box.success(
            f"Analysis complete in {elapsed:.1f}s — {pipeline_result.summary_line()}"
        )
        logger.info("Pipeline finished in %.1fs. %s", elapsed, pipeline_result.summary_line())

# ---------------------------------------------------------------------------
# Results rendering
# ---------------------------------------------------------------------------

result: PipelineResult | None = st.session_state.result

if result is None:
    st.info("Enter a GitHub repository URL and click **Analyze Repository** to begin.")
    st.stop()

# ---- Errors (pipeline-level) ----
if result.errors:
    for err in result.errors:
        st.error(f"🚨 **Pipeline Error**\n\n{err}")

# ---- Warnings ----
if result.warnings:
    with st.expander(f"⚠️ {len(result.warnings)} Warning(s)", expanded=not result.findings):
        for w in result.warnings:
            st.warning(w)

# ---- Stats ----
if result.stats:
    cols = st.columns(4)
    stat_defs = [
        ("files_found",      "📁 Files Found"),
        ("files_reviewed",   "🔍 Files Reviewed"),
        ("raw_findings",     "📋 Raw Findings"),
        ("filtered_findings","✅ Filtered Findings"),
    ]
    for col, (key, label) in zip(cols, stat_defs):
        col.metric(label, result.stats.get(key, 0))

st.divider()

# ---- No findings ----
if not result.findings:
    if result.success and not result.errors:
        st.success(
            "✅ No findings matched the current filters. "
            "Try adjusting Severity Filter or Minimum Confidence."
        )
    elif result.errors:
        st.error("Pipeline encountered errors. See details above.")
    else:
        st.warning("No findings generated. See warnings above for details.")
    st.stop()

# ---- Sort findings: severity order, then confidence descending ----
sorted_findings = sorted(
    result.findings,
    key=lambda f: (
        SEVERITY_ORDER.get(f.get("severity", "info").lower(), 99),
        -(f.get("confidence") or 0),
    ),
)

# ---- Findings header ----
st.subheader(f"🔎 {len(sorted_findings)} Finding(s)")

# ---- Render each finding ----
for idx, finding in enumerate(sorted_findings, start=1):
    severity = (finding.get("severity") or "info").lower()
    colour = SEVERITY_COLOURS.get(severity, "#888")
    filename = finding.get("filename", "unknown")
    category = finding.get("category", "general")
    description = finding.get("description", "No description.")
    suggestion = finding.get("suggestion", "")
    line = finding.get("line")
    confidence = finding.get("confidence", 0)
    summary = finding.get("summary", "")

    line_str = f"Line {line}" if line else "—"

    with st.expander(
        f"[{severity.upper()}] {filename} — {category} ({line_str})",
        expanded=(severity in ("critical", "high")),
    ):
        col_left, col_right = st.columns([3, 1])

        with col_left:
            st.markdown(
                f"<span style='color:{colour};font-weight:700;font-size:1.05rem;'>"
                f"{'🔴' if severity == 'critical' else '🟠' if severity == 'high' else '🟡' if severity == 'medium' else '🟢' if severity == 'low' else '🔵'} "
                f"{severity.capitalize()}</span>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**Description:** {description}")
            if suggestion:
                st.markdown(f"**Suggestion:** {suggestion}")
            if summary:
                st.caption(f"Chunk summary: {summary}")

        with col_right:
            st.metric("Confidence", f"{confidence}%")
            st.caption(f"File: `{filename}`")
            if line:
                st.caption(f"Line: `{line}`")

# ---------------------------------------------------------------------------
# Debug expander — always available for troubleshooting
# ---------------------------------------------------------------------------

with st.expander("🛠️ Debug Info", expanded=False):
    st.json({
        "run_id": st.session_state.run_id,
        "repo_url": st.session_state.last_repo_url,
        "min_confidence": min_confidence,
        "severity_filter": severity_filter,
        "pipeline_success": result.success if result else None,
        "stats": result.stats if result else {},
        "error_count": len(result.errors) if result else 0,
        "warning_count": len(result.warnings) if result else 0,
        "finding_count": len(result.findings) if result else 0,
        "groq_api_key_set": bool(os.environ.get("GROQ_API_KEY")),
    })