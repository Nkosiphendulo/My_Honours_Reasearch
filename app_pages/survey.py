"""Survey page for post-session feedback."""

import streamlit as st

from src.db import save_survey_responses, get_remembered_user

current_user = get_remembered_user()
if not current_user:
    st.warning("Please log in or sign up on the Login page before leaving survey feedback.")
    st.stop()

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
        current_user["user_id"],
        current_user["username"],
        {
            "agency": agency,
            "usefulness": usefulness,
            "satisfaction": satisfaction,
            "participation": participation,
            "notes": notes,
        },
    )
    st.success("Survey saved")
