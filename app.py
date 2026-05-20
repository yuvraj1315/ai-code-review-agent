import streamlit as st
import pandas as pd
import plotly.express as px
import json
import time
from core.pipeline import run_pipeline

# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="AI Code Review Agent",
    page_icon="🤖",
    layout="wide"
)

# ---------------- CUSTOM CSS ----------------
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
        color: white;
    }

    .metric-card {
        background: linear-gradient(135deg, #1f2937, #111827);
        padding: 20px;
        border-radius: 16px;
        box-shadow: 0px 4px 20px rgba(0,0,0,0.35);
        text-align: center;
        border: 1px solid #2d3748;
    }

    .metric-title {
        font-size: 16px;
        color: #9ca3af;
    }

    .metric-value {
        font-size: 28px;
        font-weight: bold;
        color: white;
    }

    .finding-card {
        background: #161b22;
        padding: 15px;
        border-radius: 14px;
        border: 1px solid #30363d;
        margin-bottom: 12px;
    }

    .severity-high {
        color: #ff4b4b;
        font-weight: bold;
    }

    .severity-medium {
        color: #f59e0b;
        font-weight: bold;
    }

    .severity-low {
        color: #10b981;
        font-weight: bold;
    }

    .hero {
        text-align: center;
        padding: 20px;
        background: linear-gradient(135deg, #111827, #1e293b);
        border-radius: 18px;
        margin-bottom: 25px;
        border: 1px solid #334155;
    }
</style>
""", unsafe_allow_html=True)

# ---------------- HERO ----------------
st.markdown("""
<div class="hero">
    <h1>🤖 AI Code Review Agent</h1>
    <p>Autonomous AI-powered code analysis using AST parsing and intelligent review pipeline</p>
</div>
""", unsafe_allow_html=True)

# ---------------- SIDEBAR ----------------
st.sidebar.title("⚙ Control Panel")

repo_url = st.sidebar.text_input(
    "GitHub Repository URL",
    placeholder="https://github.com/pallets/flask"
)

severity_filter = st.sidebar.selectbox(
    "Severity Filter",
    ["All", "high", "medium", "low"]
)

confidence_threshold = st.sidebar.slider(
    "Minimum Confidence",
    0,
    100,
    0
)

analyze_button = st.sidebar.button("🚀 Analyze Repository")

# ---------------- MAIN LOGIC ----------------
if analyze_button:

    if not repo_url:
        st.warning("Please enter a GitHub repository URL.")
        st.stop()

    progress = st.progress(0)
    status = st.empty()

    steps = [
        "Cloning repository...",
        "Scanning Python files...",
        "Parsing AST structures...",
        "Running AI code review...",
        "Generating findings..."
    ]

    for i, step in enumerate(steps):
        status.info(step)
        progress.progress((i + 1) * 20)
        time.sleep(0.5)

    with st.spinner("Running analysis..."):
        try:
            results = run_pipeline(repo_url)
        except Exception as e:
            st.error(f"Analysis failed: {e}")
            st.stop()

    if not results:
        st.error("No findings generated.")
        st.stop()

    df = pd.DataFrame(results)

    # Clean file paths
    df["file"] = df["file"].apply(
        lambda x: x.split("temp_repos\\")[-1] if "temp_repos" in x else x
    )

    # Apply filters
    if severity_filter != "All":
        df = df[df["severity"] == severity_filter]

    df = df[df["confidence"] >= confidence_threshold]

    # ---------------- METRICS ----------------
    total_findings = len(df)
    high_count = len(df[df["severity"] == "high"])
    medium_count = len(df[df["severity"] == "medium"])
    low_conf = len(df[df["confidence"] < 50])

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Total Findings</div>
            <div class="metric-value">{total_findings}</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">High Severity</div>
            <div class="metric-value">{high_count}</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Medium Severity</div>
            <div class="metric-value">{medium_count}</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Low Confidence</div>
            <div class="metric-value">{low_conf}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ---------------- CHARTS ----------------
    col1, col2 = st.columns(2)

    with col1:
        severity_counts = df["severity"].value_counts().reset_index()
        severity_counts.columns = ["severity", "count"]

        fig1 = px.bar(
            severity_counts,
            x="severity",
            y="count",
            title="Severity Distribution"
        )

        st.plotly_chart(fig1, width='stretch')

    with col2:
        category_counts = df["category"].value_counts().reset_index()
        category_counts.columns = ["category", "count"]

        fig2 = px.pie(
            category_counts,
            names="category",
            values="count",
            title="Category Distribution"
        )

        st.plotly_chart(fig2, width='stretch')

    st.markdown("---")

    # ---------------- FINDINGS ----------------
    st.subheader("📋 Review Findings")

    for idx, row in df.iterrows():

        severity_class = f"severity-{row['severity']}"

        with st.expander(f"🔍 {row['issue']} ({row['name']})"):

            st.markdown(f"""
            <div class="finding-card">
                <p><b>File:</b> {row['file']}</p>
                <p><b>Line:</b> {row['line']}</p>
                <p><b>Type:</b> {row['type']}</p>
                <p><b>Severity:</b> <span class="{severity_class}">{row['severity'].upper()}</span></p>
                <p><b>Confidence:</b> {row['confidence']}%</p>
                <p><b>Category:</b> {row['category']}</p>
                <p><b>Suggestion:</b> {row['suggestion']}</p>
            </div>
            """, unsafe_allow_html=True)

    # ---------------- LOW CONFIDENCE ----------------
    low_conf_df = df[df["confidence"] < 50]

    if not low_conf_df.empty:
        st.markdown("---")
        st.subheader("⚠ Verify These Findings")

        st.warning(
            "These findings have low AI confidence and should be manually verified."
        )

        for _, row in low_conf_df.iterrows():
            st.error(f"{row['issue']} → {row['file']}")

    # ---------------- EXPORT ----------------
    st.markdown("---")
    st.subheader("⬇ Export Reports")

    csv_data = df.to_csv(index=False).encode("utf-8")
    json_data = df.to_json(orient="records", indent=2)

    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            "Download CSV Report",
            csv_data,
            "review_results.csv",
            "text/csv"
        )

    with col2:
        st.download_button(
            "Download JSON Report",
            json_data,
            "review_results.json",
            "application/json"
        )

else:
    st.info("Enter a GitHub repository URL from the sidebar and click Analyze.")