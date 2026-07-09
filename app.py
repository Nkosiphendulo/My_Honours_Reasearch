"""Main entry point for the Streamlit co-design platform."""

import streamlit as st

from src.db import create_participant

st.set_page_config(page_title="Campus Co-Design Platform", page_icon="🏫", layout="wide")

if "participant_code" not in st.session_state:
    participant = create_participant()
    st.session_state.participant_code = participant["participant_code"]

st.title("Campus Co-Design Platform")
st.write("This multipage app supports consent, co-design, evaluation, and survey steps for campus innovation work.")
st.info("Participant code: %s" % st.session_state.participant_code)

st.sidebar.title("Navigation")
st.sidebar.page_link("pages/consent.py", label="Consent")
st.sidebar.page_link("pages/workshop.py", label="Co-Design Workshop")
st.sidebar.page_link("pages/evaluation.py", label="Evaluation")
st.sidebar.page_link("pages/survey.py", label="Survey")

st.markdown("### Privacy guardrails")
st.markdown("- No names or email addresses are stored.")
st.markdown("- The app uses an anonymised participant code.")
st.markdown("- Free text is sanitised before persistence.")
