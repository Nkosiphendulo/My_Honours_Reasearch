"""Co-design workshop page for generating structured product concepts with an SPC chatbot."""

import streamlit as st
import html as _html

from src.db import log_prompt_response, save_spc, LOCAL_STORE, create_participant
from src.llm import build_spc, chat_spc, format_spc_for_display
from src.tts import generate_speech

st.title("Co-Design Workshop")
st.write(
    "Use the SPC chatbot to co-create a Structured Product Concept (SPC). "
    "Chat with the assistant below; press Generate SPC when you're ready."
)

# Initialize participant code if not already set
if "participant_code" not in st.session_state:
    participant = create_participant()
    st.session_state.participant_code = participant["participant_code"]

if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        {
            "role": "assistant",
            "message": "Hi! Describe the campus need and I will help you create a Structured Product Concept (SPC).",
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

st.subheader("SPC Chat")

# Process chat input FIRST before rendering
chat_text = st.chat_input("Type a message...")

if chat_text and chat_text.strip():
    st.session_state.chat_history.append({"role": "user", "message": chat_text.strip()})
    assistant_reply = chat_spc(st.session_state.chat_history, spc=st.session_state.spc)
    st.session_state.chat_history.append({"role": "assistant", "message": assistant_reply})

# THEN render the chat history after processing
chat_box = st.container()
with chat_box:
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    for entry in st.session_state.chat_history:
        role = entry.get("role")
        msg = entry.get("message", "")
        def _esc(text: str) -> str:
            return _html.escape(text).replace('\n', '<br>')
        if role == "user":
            st.markdown(f'<div class="row"><div class="spacer"></div><div class="bubble user">{_esc(msg)}</div></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="row"><div class="bubble ai">{_esc(msg)}</div><div class="spacer"></div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# Generate button outside the chat input
generate = st.button("Generate SPC")

if generate:
    # Build a 'need' text from user messages in the chat
    user_msgs = [m["message"] for m in st.session_state.chat_history if m.get("role") == "user"]
    need_text = "\n".join(user_msgs).strip()
    if not need_text:
        st.warning("No user messages found in the conversation to generate an SPC.")
    else:
        try:
            spc = build_spc(need_text)
            st.session_state.spc = spc
            # Log conversation-derived prompt and SPC
            log_prompt_response(
                st.session_state.participant_code,
                need_text,
                format_spc_for_display(spc),
            )
            save_spc(st.session_state.participant_code, spc)
            st.success("Structured Product Concept generated from conversation. Use the chat to refine it.")
        except Exception as exc:
            st.error(str(exc))

st.markdown("---")
# Keep legacy single-message box for compatibility; hidden by default if using whatsapp input
if "legacy_box" not in st.session_state:
    st.session_state.legacy_box = False

if st.session_state.legacy_box:
    chat_input = st.text_area("Ask the AI to refine, explain, or improve the SPC", height=140, key="chat_input")
    if st.button("Send message"):
        if not chat_input.strip():
            st.warning("Please enter a message for the chatbot.")
        else:
            st.session_state.chat_history.append({"role": "user", "message": chat_input.strip()})
            assistant_reply = chat_spc(st.session_state.chat_history, spc=st.session_state.spc)
            st.session_state.chat_history.append({"role": "assistant", "message": assistant_reply})

if st.button("Reset conversation"):
    st.session_state.chat_history = [
        {
            "role": "assistant",
            "message": "Hi! Describe the campus need and I will help you create a Structured Product Concept (SPC).",
        }
    ]
    st.session_state.spc = None
    st.success("Chat reset. Start again with a new campus need.")

if st.session_state.spc:
    spc = st.session_state.spc
    st.subheader("Generated Structured Product Concept")
    st.write(f"**Need:** {spc.get('need', '')}")
    st.write(f"**Problem statement:** {spc.get('problem_statement', '')}")
    st.write(f"**Target user:** {spc.get('target_user', '')}")
    st.write(f"**Solution concept:** {spc.get('solution_concept', '')}")
    st.write(f"**Evidence:** {spc.get('evidence', '')}")

    # Text-to-speech controls
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
