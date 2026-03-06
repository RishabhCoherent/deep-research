"""
Streamlit UI for Market Research Report Generation.

Launch: streamlit run app.py --server.maxUploadSize=200
"""

import json
import time

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from ui.components import apply_custom_css, render_step_indicator, render_sidebar
from ui.extraction import run_extraction, run_extraction_from_paths, load_json_upload, load_json_from_path, get_extraction_summary
from ui.generation import start_generation, drain_queue

# ─── Page Config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Market Research Report Generator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_custom_css()

# ─── Session State Init ─────────────────────────────────────────────────────

defaults = {
    "current_step": 1,
    "extracted_data": None,
    "report_title": "",
    "section_plans": [],
    "extraction_summary": None,
    "skip_content": False,
    "topic_override": "",
    "generation_running": False,
    "generation_complete": False,
    "generation_progress": [],
    "generation_thread": None,
    "progress_queue": None,
    "generation_result": None,
    "output_bytes": None,
    "output_size": 0,
    "citation_count": 0,
}

for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ─── Sidebar ─────────────────────────────────────────────────────────────────

api_keys = render_sidebar()

# ─── Main Area ───────────────────────────────────────────────────────────────

st.title("Market Research Report Generator")
st.markdown("Generate comprehensive market research reports from TOC and Market Estimate data.")

render_step_indicator(st.session_state["current_step"])

st.divider()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 1: Upload Files
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if st.session_state["current_step"] == 1:
    st.header("Step 1: Input Files")

    tab1, tab2, tab3, tab4 = st.tabs([
        "📂 File Paths (PPTX + XLSX)",
        "📂 File Path (JSON)",
        "📁 Upload (PPTX + XLSX)",
        "📁 Upload (JSON)",
    ])

    # ── Tab 1: Local file paths (PPTX + XLSX) ────────────────────────
    with tab1:
        st.markdown("Enter the **local file paths** for the PowerPoint (TOC) and Excel (Market Estimate) files.")
        pptx_path = st.text_input(
            "Path to TOC file (.pptx)",
            placeholder=r"C:\Users\...\TOC.pptx",
            key="path_pptx",
        )
        xlsx_path = st.text_input(
            "Path to Market Estimate file (.xlsx)",
            placeholder=r"C:\Users\...\ME_Data.xlsx",
            key="path_xlsx",
        )

        if pptx_path and xlsx_path:
            if st.button("Extract Data →", type="primary", use_container_width=True, key="btn_path_extract"):
                with st.spinner("Extracting TOC and Market Estimate data..."):
                    try:
                        data = run_extraction_from_paths(pptx_path, xlsx_path)
                        summary = get_extraction_summary(data)

                        st.session_state["extracted_data"] = data
                        st.session_state["report_title"] = summary["report_title"]
                        st.session_state["extraction_summary"] = summary
                        st.session_state["section_plans"] = summary["plans"]
                        st.session_state["current_step"] = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"Extraction failed: {e}")

    # ── Tab 2: Local file path (JSON) ────────────────────────────────
    with tab2:
        st.markdown("Enter the **local path** to a pre-extracted JSON file.")
        json_path = st.text_input(
            "Path to JSON file",
            placeholder=r"C:\Users\...\extracted_data.json",
            key="path_json",
        )

        if json_path:
            if st.button("Load JSON →", type="primary", use_container_width=True, key="btn_path_json"):
                try:
                    data = load_json_from_path(json_path)
                    summary = get_extraction_summary(data)

                    st.session_state["extracted_data"] = data
                    st.session_state["report_title"] = summary["report_title"]
                    st.session_state["extraction_summary"] = summary
                    st.session_state["section_plans"] = summary["plans"]
                    st.session_state["current_step"] = 2
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to load JSON: {e}")

    # ── Tab 3: Upload PPTX + XLSX ────────────────────────────────────
    with tab3:
        st.markdown("Upload the **PowerPoint** (TOC) and **Excel** (Market Estimate) files.")
        col1, col2 = st.columns(2)

        with col1:
            pptx_file = st.file_uploader(
                "Table of Contents (.pptx)",
                type=["pptx"],
                key="upload_pptx",
                help="PowerPoint file containing the report Table of Contents",
            )

        with col2:
            xlsx_file = st.file_uploader(
                "Market Estimate (.xlsx)",
                type=["xlsx"],
                key="upload_xlsx",
                help="Excel file containing market estimate data sheets",
            )

        if pptx_file and xlsx_file:
            st.success(f"Files ready: **{pptx_file.name}** + **{xlsx_file.name}**")

            if st.button("Extract Data →", type="primary", use_container_width=True, key="btn_upload_extract"):
                with st.spinner("Extracting TOC and Market Estimate data..."):
                    try:
                        data = run_extraction(pptx_file, xlsx_file)
                        summary = get_extraction_summary(data)

                        st.session_state["extracted_data"] = data
                        st.session_state["report_title"] = summary["report_title"]
                        st.session_state["extraction_summary"] = summary
                        st.session_state["section_plans"] = summary["plans"]
                        st.session_state["current_step"] = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"Extraction failed: {e}")
        elif pptx_file or xlsx_file:
            st.info("Upload both files to proceed.")

    # ── Tab 4: Upload JSON ───────────────────────────────────────────
    with tab4:
        st.markdown("Upload a JSON file previously generated by `extract_inputs.py`.")
        json_file = st.file_uploader(
            "Pre-extracted JSON",
            type=["json"],
            key="upload_json",
            help="JSON file with 'toc' and 'me_data' keys",
        )

        if json_file:
            if st.button("Load JSON →", type="primary", use_container_width=True, key="btn_upload_json"):
                try:
                    data = load_json_upload(json_file)
                    summary = get_extraction_summary(data)

                    st.session_state["extracted_data"] = data
                    st.session_state["report_title"] = summary["report_title"]
                    st.session_state["extraction_summary"] = summary
                    st.session_state["section_plans"] = summary["plans"]
                    st.session_state["current_step"] = 2
                    st.rerun()
                except Exception as e:
                    st.error(f"Invalid JSON: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 2: Extraction Results
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

elif st.session_state["current_step"] == 2:
    st.header("Step 2: Extraction Complete")

    summary = st.session_state.get("extraction_summary", {})
    if not summary:
        st.session_state["current_step"] = 1
        st.rerun()

    # Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Report Title", summary.get("report_title", "Unknown"))
    col2.metric("TOC Sections", summary.get("section_count", 0))
    col3.metric("ME Data Sheets", summary.get("sheet_count", 0))

    # Section plan preview
    with st.expander("Section Plan Preview", expanded=True):
        for plan in summary.get("plans", []):
            st.markdown(f"**S{plan['number']}** `{plan['type']}` — {plan['title']}")

    # Data sheets
    with st.expander("ME Data Sheets"):
        for sheet in summary.get("sheets", []):
            st.markdown(f"- {sheet}")

    # Download extracted JSON
    data_json = json.dumps(st.session_state["extracted_data"], indent=2, ensure_ascii=False)
    st.download_button(
        "💾 Download Extracted JSON",
        data=data_json,
        file_name=f"{summary.get('report_title', 'data').replace(' ', '_')[:40]}.json",
        mime="application/json",
    )

    st.divider()

    # Generation config summary
    mode = "Charts + Tables only" if st.session_state.get("skip_content") else "Full report with LLM content"
    topic = st.session_state.get("topic_override") or summary.get("report_title", "")
    st.markdown(f"**Mode:** {mode}")
    st.markdown(f"**Topic:** {topic}")

    if not st.session_state.get("skip_content"):
        st.warning("Full report generation takes **15-30 minutes** (LLM + web research). Use the sidebar toggle to skip for a quick preview.")

    # Check API key before allowing generation
    has_openai = api_keys.get("openai") or bool(st.session_state.get("openai_key_override"))
    if not has_openai and not st.session_state.get("skip_content"):
        st.error("OpenAI API key required for content generation. Add it in the sidebar or enable 'Skip LLM content'.")
    else:
        col_a, col_b = st.columns([3, 1])
        with col_a:
            if st.button("Generate Report →", type="primary", use_container_width=True):
                st.session_state["current_step"] = 3
                st.session_state["generation_running"] = True
                st.session_state["generation_progress"] = []
                st.session_state["generation_complete"] = False

                thread, pq, result = start_generation(
                    st.session_state["extracted_data"],
                    skip_content=st.session_state.get("skip_content", False),
                    topic_override=st.session_state.get("topic_override", ""),
                )
                st.session_state["generation_thread"] = thread
                st.session_state["progress_queue"] = pq
                st.session_state["generation_result"] = result
                st.rerun()

        with col_b:
            if st.button("← Back to Upload"):
                st.session_state["current_step"] = 1
                st.session_state["extracted_data"] = None
                st.rerun()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 3: Generation Progress
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

elif st.session_state["current_step"] == 3:
    st.header("Step 3: Generating Report")

    thread = st.session_state.get("generation_thread")
    pq = st.session_state.get("progress_queue")
    result = st.session_state.get("generation_result", {})

    # Drain new messages from queue
    if pq:
        new_msgs = drain_queue(pq)
        st.session_state["generation_progress"].extend(new_msgs)

    messages = st.session_state.get("generation_progress", [])

    # Check if thread is done
    is_done = False
    if thread and not thread.is_alive():
        is_done = True

    # Display progress
    if not is_done:
        status_label = "Generating report..."
        for msg_type, msg_text in reversed(messages):
            if msg_type == "status":
                status_label = msg_text
                break

        with st.status(status_label, expanded=True, state="running"):
            if not messages:
                st.markdown("**Initializing report generation pipeline...**")
                st.text("  Setting up LLM and web research tools")
            for msg_type, msg_text in messages:
                if msg_type == "done":
                    continue
                if msg_type == "status":
                    st.markdown(f"**{msg_text}**")
                elif msg_type == "info":
                    st.info(msg_text)
                elif msg_type == "warning":
                    st.warning(msg_text)
                elif msg_type == "progress":
                    st.text(f"  {msg_text}")

        # Estimate progress
        section_count = len(st.session_state.get("section_plans", []))
        progress_msgs = [m for t, m in messages if t == "progress"]
        if section_count > 0 and progress_msgs:
            content_done = sum(1 for m in progress_msgs if "Generating content:" in m)
            build_done = sum(1 for m in progress_msgs if "Building section" in m)
            pct = min((content_done * 0.7 + build_done * 0.3) / max(section_count, 1), 1.0)
            st.progress(pct, text=f"~{int(pct * 100)}% complete")
        else:
            st.progress(0, text="Starting up...")

        # Poll again
        time.sleep(2)
        st.rerun()

    else:
        # Generation finished
        if result.get("success"):
            st.balloons()

            output_path = result["output_path"]
            with open(output_path, "rb") as f:
                output_bytes = f.read()

            st.session_state["output_bytes"] = output_bytes
            st.session_state["output_size"] = len(output_bytes)
            st.session_state["generation_running"] = False
            st.session_state["generation_complete"] = True

            # Extract citation count from progress messages
            for msg_type, msg_text in messages:
                if msg_type == "info" and "Citations:" in msg_text:
                    try:
                        cit_part = msg_text.split("Citations:")[1].strip()
                        st.session_state["citation_count"] = int(cit_part)
                    except (ValueError, IndexError):
                        pass

            st.session_state["current_step"] = 4
            st.rerun()
        else:
            error_msg = result.get("error", "Unknown error")
            st.error(f"Report generation failed: {error_msg}")

            # Show progress messages for debugging
            with st.expander("Generation Log", expanded=False):
                for msg_type, msg_text in messages:
                    if msg_type == "done":
                        continue
                    st.text(f"[{msg_type}] {msg_text}")

            if st.button("← Back to Configuration"):
                st.session_state["current_step"] = 2
                st.session_state["generation_running"] = False
                st.rerun()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STEP 4: Download
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

elif st.session_state["current_step"] == 4:
    st.header("Step 4: Report Ready!")

    output_bytes = st.session_state.get("output_bytes")
    if not output_bytes:
        st.session_state["current_step"] = 1
        st.rerun()

    report_title = st.session_state.get("report_title", "Report")
    size_mb = st.session_state.get("output_size", 0) / (1024 * 1024)
    section_count = len(st.session_state.get("section_plans", []))
    citation_count = st.session_state.get("citation_count", 0)

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Report", report_title[:30])
    col2.metric("File Size", f"{size_mb:.1f} MB")
    col3.metric("Sections", section_count)
    col4.metric("Citations", citation_count)

    st.divider()

    # Download button
    safe_name = report_title.replace(" ", "_")[:60]
    st.download_button(
        label="📥 Download Report (.docx)",
        data=output_bytes,
        file_name=f"{safe_name}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary",
        use_container_width=True,
    )

    st.divider()

    # Generation log
    messages = st.session_state.get("generation_progress", [])
    if messages:
        with st.expander("Generation Log"):
            for msg_type, msg_text in messages:
                if msg_type == "done":
                    continue
                if msg_type == "info":
                    st.markdown(f"**{msg_text}**")
                elif msg_type == "warning":
                    st.warning(msg_text)
                else:
                    st.text(msg_text)

    # New report button
    if st.button("Generate Another Report", use_container_width=True):
        # Skip keys bound to widgets — Streamlit forbids setting them after render
        _widget_keys = {"skip_content", "topic_override"}
        for key, val in defaults.items():
            if key not in _widget_keys:
                st.session_state[key] = val
        st.rerun()
