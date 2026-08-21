"""Login, signup, and consent page for the co-design platform."""

import streamlit as st

from src.db import (
    authenticate_user,
    create_consent_record,
    create_user,
    get_remembered_user,
    logout_user,
)

current_user = get_remembered_user()

if current_user:
    st.title("Login / Consent")
    st.success(f"Logged in as {current_user['username']}")
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Go to Workshop"):
            st.rerun()
    with col2:
        if st.button("Log out"):
            logout_user()
            for key in ("user", "participant_code", "chat_history", "spc"):
                st.session_state.pop(key, None)
            st.rerun()

    st.markdown("---")
    st.subheader("Consent")
    st.write("Please confirm that you understand the study and that you consent to participate.")

    consent_checked = st.checkbox("I consent to take part in this study")
    if st.button("Save consent"):
        if consent_checked:
            create_consent_record(
                current_user["user_id"],
                current_user["username"],
                True,
                "Participant consented",
            )
            st.success("Consent recorded")
        else:
            create_consent_record(
                current_user["user_id"],
                current_user["username"],
                False,
                "Participant declined",
            )
            st.warning("Consent declined")
else:
    st.title("Login / Signup")
    mode = st.radio("Choose an action", ["Log in", "Sign up"], index=0)

    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")
    confirm_password = None

    if mode == "Sign up":
        confirm_password = st.text_input("Confirm password", type="password", key="login_confirm_password")

    if st.button("Submit", key="login_submit"):
        if not username.strip() or not password:
            st.error("Username and password are required.")
        elif mode == "Sign up" and password != confirm_password:
            st.error("Passwords do not match.")
        else:
            try:
                if mode == "Sign up":
                    user = create_user(username, password)
                else:
                    user = authenticate_user(username, password)
                if user:
                    st.success(f"Logged in as {user['username']}")
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
            except ValueError as exc:
                st.error(str(exc))
