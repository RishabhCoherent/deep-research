"""Reusable UI components — step indicator, API key checker, custom CSS."""

import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def apply_custom_css():
    """Inject custom styling to match the report's corporate theme."""
    st.markdown("""
    <style>
    .stApp h1 { color: #1B3A5C; }
    .stApp h2 { color: #2E75B6; }
    .step-row { display: flex; align-items: center; justify-content: center; gap: 0.5rem; margin-bottom: 1.5rem; }
    .step-badge { display: inline-block; width: 32px; height: 32px; border-radius: 50%;
                  text-align: center; line-height: 32px; font-weight: bold; font-size: 14px; }
    .step-active { background: #2E75B6; color: white; }
    .step-done { background: #1B3A5C; color: white; }
    .step-pending { background: #D9D9D9; color: #888; }
    .step-line { width: 60px; height: 2px; background: #D9D9D9; }
    .step-line-done { background: #1B3A5C; }
    </style>
    """, unsafe_allow_html=True)


def render_step_indicator(current_step: int):
    """Render a 4-step progress indicator."""
    steps = ["Upload", "Extract", "Generate", "Download"]
    cols = st.columns(len(steps) * 2 - 1)

    for i, label in enumerate(steps):
        step_num = i + 1
        col_idx = i * 2

        with cols[col_idx]:
            if step_num < current_step:
                st.markdown(f"**:white_check_mark: {label}**")
            elif step_num == current_step:
                st.markdown(f"**:large_blue_circle: {label}**")
            else:
                st.markdown(f":white_circle: {label}")

        # Connector line between steps
        if i < len(steps) - 1:
            with cols[col_idx + 1]:
                st.markdown("---")


def check_api_keys() -> dict:
    """Check which API keys are available. Returns status dict."""
    openai_key = os.getenv("OPENAI_API_KEY", "")

    # Check SearXNG availability
    searxng_ok = False
    try:
        from tools.search import _searxng_available
        searxng_ok = _searxng_available()
    except Exception:
        pass

    return {
        "openai": bool(openai_key),
        "searxng": searxng_ok,
    }


def render_sidebar():
    """Render the sidebar with API key status and generation settings."""
    with st.sidebar:
        st.header("Configuration")

        # API Key Status
        with st.expander("API Keys", expanded=True):
            keys = check_api_keys()

            # Check for runtime overrides
            if st.session_state.get("openai_key_override"):
                os.environ["OPENAI_API_KEY"] = st.session_state["openai_key_override"]
                keys["openai"] = True

            st.markdown(f"{'✅' if keys['openai'] else '❌'} **OpenAI** {'(from .env)' if keys['openai'] else '— required'}")
            st.markdown(f"{'✅' if keys['searxng'] else '⚠️'} **SearXNG** {'(running)' if keys['searxng'] else '— not running (DuckDuckGo fallback)'}")

            if not keys["openai"]:
                st.text_input("OpenAI API Key", type="password", key="openai_key_override",
                              help="Required for content generation")

            if not keys["searxng"]:
                st.caption("Start SearXNG: `docker compose up -d`")

            if not keys["openai"] and not st.session_state.get("openai_key_override"):
                st.error("OpenAI API key is required for report generation.")

        # Generation Settings
        with st.expander("Generation Settings", expanded=True):
            st.toggle("Skip LLM content (charts + tables only)", key="skip_content",
                       help="Much faster (~1 min vs ~20 min). No researched text, just data visualizations.")

            st.text_input("Topic name override", key="topic_override",
                          help="Leave empty to auto-detect from TOC. Override if you want a different title used for research.")

        # Info
        with st.expander("About"):
            st.markdown("""
            **Market Research Report Generator**

            Generates comprehensive .docx reports from:
            - PPTX (Table of Contents)
            - XLSX (Market Estimate data)

            Pipeline: Web Research → LLM Content → Charts → Tables → .docx

            **Estimated times:**
            - Charts only: ~1 minute
            - Full report: 15-30 minutes
            """)

        # Show detected report info if available
        if st.session_state.get("report_title"):
            st.divider()
            st.markdown(f"**Report:** {st.session_state['report_title']}")
            plans = st.session_state.get("section_plans", [])
            if plans:
                st.markdown(f"**Sections:** {len(plans)}")

    return keys
