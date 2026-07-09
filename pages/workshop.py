"""Co-design workshop page for generating structured product concepts."""

import streamlit as st

from src.db import log_prompt_response, save_spc
from src.llm import build_spc, format_spc_for_display

st.title("Co-Design Workshop")
st.write("Enter a campus need and generate a structured product concept.")

need_input = st.text_area("Describe the campus need", height=120)
if st.button("Generate SPC") and need_input:
    spc = build_spc(need_input)
    st.session_state.spc = spc
    log_prompt_response(st.session_state.participant_code, need_input, format_spc_for_display(spc))
    save_spc(st.session_state.participant_code, spc)
    st.success("Structured product concept generated")

if "spc" in st.session_state:
    spc = st.session_state.spc
    st.subheader("Structured Product Concept")
    st.write(f"**Need:** {spc.get('need', '')}")
    st.write(f"**Problem statement:** {spc.get('problem_statement', '')}")
    st.write(f"**Target user:** {spc.get('target_user', '')}")
    st.write(f"**Solution concept:** {spc.get('solution_concept', '')}")
    st.write(f"**Evidence:** {spc.get('evidence', '')}")
