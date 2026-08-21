"""Co-design workshop page for generating structured product concepts with an AI assistant."""

import streamlit as st
import html as _html
import json

from src.db import (
    create_participant,
    get_remembered_user,
    log_prompt_response,
    save_chat_history,
    save_spc_output,
    get_chat_history,
)
from src.llm import chat_spc, generate_final_spc, format_spc_for_display
from src.tts import generate_speech

current_user = get_remembered_user()
if not current_user:
    st.warning("Please log in or sign up on the Login page before using the workshop.")
    st.stop()

st.title("Co-Design Workshop")
st.write(
    "Use the AI assistant below to describe a campus need and create a Structured Product Concept (SPC)."
)

with st.container():
    st.subheader("Next steps")
    cols = st.columns(2)
    with cols[0]:
        st.page_link("app_pages/evaluation.py", label="Go to Evaluation", icon="📝", use_container_width=True)
    with cols[1]:
        st.page_link("app_pages/survey.py", label="Go to Survey", icon="📋", use_container_width=True)

st.markdown("---")

if "participant_code" not in st.session_state:
    participant = create_participant(user_id=current_user["user_id"])
    st.session_state.participant_code = participant["participant_code"]
    st.session_state.user = current_user

if "chat_history" not in st.session_state:
    saved_history = get_chat_history(current_user["user_id"])
    st.session_state.chat_history = saved_history or [
        {
            "role": "assistant",
            "message": f"Hi {current_user['username']}! Tell me about a campus need and I will help you create an SPC.",
        }
    ]

if "spc" not in st.session_state:
    st.session_state.spc = None

st.markdown(
    "<style>"
    ".chat-container{max-height:420px;overflow:auto;padding:12px;background:#f6f6f6;border-radius:8px;}"
    ".bubble{padding:10px;border-radius:16px;margin:6px 0;display:inline-block;max-width:80%;line-height:1.4;color:#111;}"
    ".user{background:#DCF8C6;align-self:flex-end;margin-left:40px;color:#000;}"
    ".ai{background:#ffffff;border:1px solid #e6e6e6;margin-right:40px;color:#000;}"
    ".row{display:flex;align-items:flex-start;}"
    ".spacer{flex:1;}"
    "</style>",
    unsafe_allow_html=True,
)

st.subheader("AI Design Assistant")
chat_text = st.chat_input("Tell the assistant about the campus need...", key="workshop_chat_input")

if chat_text and chat_text.strip():
    st.session_state.chat_history.append({"role": "user", "message": chat_text.strip()})
    save_chat_history(current_user["user_id"], st.session_state.chat_history)
    result = chat_spc(st.session_state.chat_history, username=current_user["username"])
    assistant_reply = result.get("reply", "")
    if result.get("reset_conversation"):
        st.session_state.chat_history = [
            {"role": "user", "message": chat_text.strip()},
        ]
        st.session_state.assistant_asked_generate = False
    st.session_state.chat_history.append({"role": "assistant", "message": assistant_reply})
    # mark that assistant has asked whether to generate the SPC
    if result.get("ready_for_generation") or result.get("asks_generate"):
        st.session_state.assistant_asked_generate = True
    save_chat_history(current_user["user_id"], st.session_state.chat_history)

chat_box = st.container()
with chat_box:
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    for entry in st.session_state.chat_history:
        role = entry.get("role")
        msg = entry.get("message", "")

        def _esc(text: str) -> str:
            return _html.escape(text).replace("\n", "<br>")

        if role == "user":
            st.markdown(
                f'<div class="row"><div class="spacer"></div><div class="bubble user">{_esc(msg)}</div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="row"><div class="bubble ai">{_esc(msg)}</div><div class="spacer"></div></div>',
                unsafe_allow_html=True,
            )
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")
# Show generate button only when assistant has asked for generation
if st.session_state.get("assistant_asked_generate"):
    st.info("The assistant thinks it has enough detail to draft your SPC. Click to confirm generation.")
    if st.button("Yes — generate my SPC now"):
        # generate final SPC only after explicit confirmation
        final = generate_final_spc(st.session_state.chat_history, current_user.get("username"), st.session_state.participant_code)
        # persist the structured fields
        try:
            save_spc_output(
                current_user["user_id"],
                current_user["username"],
                st.session_state.participant_code,
                final.get("overview", ""),
                final.get("overview_traced_from"),
                final.get("target_users", ""),
                final.get("target_users_traced_from"),
                final.get("functional_requirements", []),
                final.get("functional_requirements_traced_from"),
                final.get("nonfunctional_requirements", []),
                final.get("nonfunctional_requirements_traced_from"),
                final.get("assumptions_constraints"),
                final.get("assumptions_constraints_traced_from"),
                final.get("expected_benefits"),
                final.get("expected_benefits_traced_from"),
            )
            # store for display
            st.session_state.spc = final
            # log a summary prompt-response
            log_prompt_response(
                current_user["user_id"],
                current_user["username"],
                "Conversation-based SPC generation",
                json.dumps({k: final.get(k) for k in ["overview", "target_users"]}),
            )
            st.success("Structured Product Concept generated and saved.")
        except Exception as exc:
            st.error(f"Could not save SPC: {exc}")

if st.session_state.get("spc"):
    spc = st.session_state["spc"]
    st.subheader("Generated Structured Product Concept")
    st.write(f"**Problem statement:** {spc.get('overview', spc.get('problem_statement', ''))}")
    st.write(f"**Target users:** {spc.get('target_users', spc.get('target_user', ''))}")
    solution = spc.get('functional_requirements', spc.get('solution_concept', ''))
    if isinstance(solution, list):
        solution = " ".join(item.get('text', str(item)) if isinstance(item, dict) else str(item) for item in solution)
    st.write(f"**Solution concept:** {solution}")
    evidence = spc.get('expected_benefits', spc.get('evidence', ''))
    st.write(f"**Evidence/rationale:** {evidence}")

    st.markdown("---")
    st.subheader("Listen to SPC")
    col1, col2 = st.columns([3, 1])
    with col1:
        tts_text = st.text_area(
            "Text to read aloud",
            value=format_spc_for_display(spc),
            height=100,
        )
    with col2:
        st.write("")
        st.write("")
        if st.button("🔊 Generate Audio"):
            with st.spinner("Generating audio..."):
                audio_bytes, error_msg = generate_speech(tts_text)
                if audio_bytes:
                    st.audio(audio_bytes, format="audio/wav")
                    st.success("Audio generated successfully!")
                else:
                    st.error(error_msg or "Could not generate audio. Please check your configuration.")

    if st.button("Reset SPC"):
        st.session_state.spc = None
        st.success("SPC cleared. You can generate a new one.")
