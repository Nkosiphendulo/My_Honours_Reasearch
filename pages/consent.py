"""Consent page for the co-design platform."""

import streamlit as st

from src.db import create_consent_record

st.set_page_config(page_title="Consent", layout="wide")

st.title("Consent")
st.write("Please confirm that you understand the study and that you consent to participate.")

consent_checked = st.checkbox("I consent to take part in this study")
if st.button("Save consent"):
    if consent_checked:
        create_consent_record(st.session_state.participant_code, True, "Participant consented")
        st.success("Consent recorded")
    else:
        create_consent_record(st.session_state.participant_code, False, "Participant declined")
        st.warning("Consent declined")
