"""Evaluation page for rubric scoring."""

import streamlit as st

from src.db import save_rubric_scores

st.title("Evaluation")
st.write("Score the concept using a short rubric.")

with st.form("evaluation_form"):
    clarity = st.slider("Clarity", 1, 5, 3)
    usefulness = st.slider("Usefulness", 1, 5, 3)
    feasibility = st.slider("Feasibility", 1, 5, 3)
    inclusivity = st.slider("Inclusivity", 1, 5, 3)
    notes = st.text_area("Optional notes")
    submitted = st.form_submit_button("Save evaluation")

if submitted:
    save_rubric_scores(
        st.session_state.participant_code,
        {
            "clarity": clarity,
            "usefulness": usefulness,
            "feasibility": feasibility,
            "inclusivity": inclusivity,
        },
        notes,
    )
    st.success("Evaluation saved")
