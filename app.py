"""Main entry point for the Streamlit co-design platform."""

import streamlit as st

from src.db import get_remembered_user, logout_user

st.set_page_config(page_title="Campus Co-Design Platform", page_icon="🏫", layout="wide")

if "user" not in st.session_state:
    remembered = get_remembered_user()
    if remembered:
        st.session_state.user = remembered
        st.session_state.participant_code = remembered.get("participant_code")

logged_in = bool(st.session_state.get("user"))

login_page = st.Page(
    "app_pages/login.py",
    title="Login / Consent",
    url_path="login",
    default=True,
)
workshop_page = st.Page(
    "app_pages/workshop.py",
    title="Co-Design Workshop",
    url_path="workshop",
)
evaluation_page = st.Page(
    "app_pages/evaluation.py",
    title="Evaluation",
    url_path="evaluation",
)
survey_page = st.Page(
    "app_pages/survey.py",
    title="Survey",
    url_path="survey",
)

if logged_in:
    pages = [workshop_page, evaluation_page, survey_page]

    st.sidebar.title("Navigation")
    st.sidebar.write(f"Signed in as {st.session_state['user']['username']}")
    if st.sidebar.button("Logout"):
        logout_user()
        for key in ("user", "participant_code", "chat_history", "spc"):
            st.session_state.pop(key, None)
        st.rerun()

    st.sidebar.markdown("### Pages")
    st.sidebar.page_link(workshop_page, label="App", icon="🏠", use_container_width=True)
    st.sidebar.page_link(workshop_page, label="Workshop", icon="🛠️", use_container_width=True)
    st.sidebar.markdown("---")
    st.sidebar.page_link(evaluation_page, label="Evaluation", icon="📝", use_container_width=True)
    st.sidebar.page_link(survey_page, label="Survey", icon="📋", use_container_width=True)
else:
    pages = [login_page]

page = st.navigation(pages, position="hidden")
page.run()

# Hide everything else in this router entrypoint.
st.stop()
