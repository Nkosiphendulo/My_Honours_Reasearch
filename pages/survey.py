"""Survey page for post-session feedback."""

import streamlit as st

from src.db import save_survey_responses

st.title("Survey")
st.write("Please share your feedback on the workshop experience.")

with st.form("survey_form"):
    agency = st.slider("Agency", 1, 5, 3)
    usefulness = st.slider("Usefulness", 1, 5, 3)
    satisfaction = st.slider("Satisfaction", 1, 5, 3)
    participation = st.slider("Participation", 1, 5, 3)
    notes = st.text_area("Interview observations")
    submitted = st.form_submit_button("Save survey")

if submitted:
    save_survey_responses(
        st.session_state.participant_code,
        {
            "agency": agency,
            "usefulness": usefulness,
            "satisfaction": satisfaction,
            "participation": participation,
            "notes": notes,
        },
    )
    st.success("Survey saved")
