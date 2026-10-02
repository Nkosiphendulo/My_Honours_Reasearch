"""Bounded 5-stage co-design wizard for generating a structured product concept."""

import streamlit as st

from src.db import create_participant, get_remembered_user, log_prompt_response, save_spc_output
from src.llm import (
    format_spc_for_display,
    generate_clarification_questions,
    generate_concept_options,
    is_meaningful_text,
    validate_user_inputs,
)
from src.tts import generate_speech

current_user = get_remembered_user()
if not current_user:
    st.warning("Please log in or sign up on the Login page before using the workshop.")
    st.stop()


def _empty_wizard_state():
    return {
        "stage": 1,
        "problem_statement": "",
        "target_users": "",
        "clarification_questions": [],
        "clarification_answers": [],
        "user_need": "",
        "constraints": "",
        "success_criteria": "",
        "input_review": None,
        "concept_options": [],
        "selected_concept": "",
        "final_spc": {},
    }


if "participant_code" not in st.session_state:
    participant = create_participant(user_id=current_user["user_id"])
    st.session_state.participant_code = participant["participant_code"]

if "wizard_state" not in st.session_state:
    st.session_state.wizard_state = _empty_wizard_state()

if "spc" not in st.session_state:
    st.session_state.spc = None

state = st.session_state.wizard_state

st.title("Campus Co-Design Wizard")
st.caption("Five bounded stages to turn a campus idea into a structured product concept.")

with st.container():
    st.subheader("Next steps")
    cols = st.columns(2)
    with cols[0]:
        st.page_link("app_pages/evaluation.py", label="Go to Evaluation", icon="📝", use_container_width=True)
    with cols[1]:
        st.page_link("app_pages/survey.py", label="Go to Survey", icon="📋", use_container_width=True)

st.markdown("---")
st.progress(min(1.0, state["stage"] / 5))
st.write(f"Stage {state['stage']} of 5")


if state["stage"] == 1:
    st.subheader("Stage 1 — Campus problem")
    with st.form("stage_1_form"):
        state["problem_statement"] = st.text_area(
            "Describe the campus problem in one or two sentences.",
            value=state["problem_statement"],
            height=120,
        )
        state["target_users"] = st.text_area(
            "Who is affected most by this problem?",
            value=state["target_users"],
            height=80,
        )
        submitted = st.form_submit_button("Continue to Stage 2")
        if submitted:
            if not is_meaningful_text(state["problem_statement"]):
                st.warning("Please describe a real campus problem rather than random or placeholder text.")
            elif not is_meaningful_text(state["target_users"], minimum_length=3):
                st.warning("Please describe who is affected by this problem.")
            else:
                state["stage"] = 2
                st.rerun()

elif state["stage"] == 2:
    st.subheader("Stage 2 — Need clarification")
    if not state["clarification_questions"]:
        if st.button("Generate up to 2 clarification questions"):
            questions = generate_clarification_questions(
                state["problem_statement"],
                state["target_users"],
            )
            state["clarification_questions"] = questions[:2]
            state["clarification_answers"] = [""] * len(state["clarification_questions"])
            st.rerun()

    if not state["clarification_questions"]:
        state["clarification_questions"] = [
            "What is the main user pain point you want to solve?",
            "Who is most affected by this issue?",
        ]
        state["clarification_answers"] = [""] * len(state["clarification_questions"])

    with st.form("stage_2_form"):
        answers = []
        for index, question in enumerate(state["clarification_questions"], start=1):
            answer = st.text_area(
                f"Question {index}: {question}",
                value=state["clarification_answers"][index - 1] if index - 1 < len(state["clarification_answers"]) else "",
                height=70,
            )
            answers.append(answer)
        submitted = st.form_submit_button("Continue to Stage 3")
        if submitted:
            state["clarification_answers"] = answers
            state["stage"] = 3
            st.rerun()

elif state["stage"] == 3:
    st.subheader("Stage 3 — Requirements")
    with st.form("stage_3_form"):
        state["user_need"] = st.text_area(
            "What user need or opportunity matters most here?",
            value=state["user_need"],
            height=100,
        )
        state["constraints"] = st.text_area(
            "What constraints, limits, or realities should the solution respect?",
            value=state["constraints"],
            height=100,
        )
        state["success_criteria"] = st.text_area(
            "What would a successful solution look like from the user’s perspective?",
            value=state["success_criteria"],
            height=100,
        )
        submitted = st.form_submit_button("Continue to Stage 4")
        if submitted:
            validation = validate_user_inputs(
                state["problem_statement"],
                state["target_users"],
                state["clarification_answers"],
                state["user_need"],
                state["constraints"],
                state["success_criteria"],
            )
            if validation.get("validation_ok"):
                state["input_review"] = {
                    "problem_statement": validation.get("refined_problem_statement") or state["problem_statement"],
                    "target_users": validation.get("refined_target_users") or state["target_users"],
                    "user_need": validation.get("refined_user_need") or state["user_need"],
                    "constraints": validation.get("refined_constraints") or state["constraints"],
                    "success_criteria": validation.get("refined_success_criteria") or state["success_criteria"],
                }
                st.rerun()
            else:
                st.warning(
                    validation.get("issue_summary")
                    or "The information provided needs more clarity before continuing. Please refine the problem, users, and goals."
                )

    if state.get("input_review"):
        st.markdown("#### Review wording suggestions")
        st.caption("Compare the suggested wording with your original. Accept it only if it keeps your meaning; otherwise keep your wording or edit it above.")
        review_fields = [
            ("Problem statement", "problem_statement"),
            ("Target users", "target_users"),
            ("User need", "user_need"),
            ("Constraints", "constraints"),
            ("Success criteria", "success_criteria"),
        ]
        for label, key in review_fields:
            original_col, suggestion_col = st.columns(2)
            with original_col:
                st.markdown(f"**Your wording: {label}**")
                st.write(state[key] or "Not provided")
            with suggestion_col:
                st.markdown(f"**Suggested wording: {label}**")
                st.write(state["input_review"].get(key) or "Not provided")

        accept_col, keep_col = st.columns(2)
        with accept_col:
            if st.button("Accept suggestions and continue", type="primary", key="accept_input_suggestions"):
                for key, value in state["input_review"].items():
                    state[key] = value
                state["input_review"] = None
                state["stage"] = 4
                st.rerun()
        with keep_col:
            if st.button("Keep my wording and continue", key="keep_original_input"):
                state["input_review"] = None
                state["stage"] = 4
                st.rerun()

elif state["stage"] == 4:
    st.subheader("Stage 4 — Concept generation")
    if not state["concept_options"]:
        if st.button("Generate concept options"):
            options = generate_concept_options(
                state["problem_statement"],
                state["target_users"],
                state["clarification_answers"],
                state["user_need"],
                state["constraints"],
                state["success_criteria"],
            )
            state["concept_options"] = options[:2]
            if state["concept_options"]:
                state["selected_concept"] = state["concept_options"][0]["summary"]
            st.rerun()

    if not state["concept_options"]:
        state["concept_options"] = [
            {
                "title": "Low-friction campus service",
                "summary": "Create a simple service that helps affected students identify the fastest, least disruptive path to a workable solution using existing campus resources.",
            },
            {
                "title": "Student-led pilot concept",
                "summary": "Run a small pilot with a defined user group to test demand, gather feedback, and refine the idea before wider rollout.",
            },
        ]
        state["selected_concept"] = state["concept_options"][0]["summary"]

    if state["concept_options"]:
        options = [f"{option['title']}: {option['summary']}" for option in state["concept_options"]]
        selected = st.radio("Choose a concept to carry forward", options=options, index=0)
        state["selected_concept"] = selected
        if st.button("Continue to Stage 5"):
            state["stage"] = 5
            st.rerun()

else:
    st.subheader("Stage 5 — Structured Product Concept")
    final_spc = {
        "problem_statement": state["problem_statement"].strip(),
        "target_users": state["target_users"].strip(),
        "user_need": state["user_need"].strip() or " ".join(filter(None, state["clarification_answers"])),
        "proposed_concept": state["selected_concept"].split(": ", 1)[1] if ": " in state["selected_concept"] else state["selected_concept"],
        "functional_requirements": [
            "Help the user find a workable solution quickly",
            "Design for the actual user context and constraints",
            "Support a clear next step for validation",
        ],
        "constraints": state["constraints"].strip() or "Not provided",
        "expected_benefits": state["success_criteria"].strip() or "Not provided",
        "risks_assumptions": "Assumes the initial problem and user need are valid and that a pilot can test feasibility before scaling.",
        "recommended_next_step": "Pilot the concept with a small group of affected users and collect feedback for one cycle.",
    }

    with st.form("final_spc_form"):
        final_spc["problem_statement"] = st.text_area("Problem statement", value=final_spc["problem_statement"], height=100)
        final_spc["target_users"] = st.text_area("Target users", value=final_spc["target_users"], height=80)
        final_spc["user_need"] = st.text_area("User need", value=final_spc["user_need"], height=90)
        final_spc["proposed_concept"] = st.text_area("Proposed concept", value=final_spc["proposed_concept"], height=100)
        final_spc["functional_requirements"] = st.text_area(
            "Functional requirements (one per line)",
            value="\n".join(final_spc["functional_requirements"]),
            height=120,
        ).splitlines()
        final_spc["constraints"] = st.text_area("Constraints", value=final_spc["constraints"], height=90)
        final_spc["expected_benefits"] = st.text_area("Expected benefits", value=final_spc["expected_benefits"], height=90)
        final_spc["risks_assumptions"] = st.text_area("Risks and assumptions", value=final_spc["risks_assumptions"], height=90)
        final_spc["recommended_next_step"] = st.text_area("Recommended next step", value=final_spc["recommended_next_step"], height=90)
        submitted = st.form_submit_button("Save SPC")

        if submitted:
            state["final_spc"] = final_spc
            st.session_state.spc = final_spc
            save_spc_output(
                current_user["user_id"],
                current_user["username"],
                st.session_state.participant_code,
                problem_statement=final_spc["problem_statement"],
                target_users=final_spc["target_users"],
                user_need=final_spc["user_need"],
                proposed_concept=final_spc["proposed_concept"],
                functional_requirements=[{"id": f"FR-{index + 1}", "text": item.strip()} for index, item in enumerate(final_spc["functional_requirements"]) if item.strip()],
                constraints=final_spc["constraints"],
                expected_benefits=final_spc["expected_benefits"],
                risks_assumptions=final_spc["risks_assumptions"],
                recommended_next_step=final_spc["recommended_next_step"],
            )
            log_prompt_response(
                current_user["user_id"],
                current_user["username"],
                "5-stage SPC wizard",
                format_spc_for_display(final_spc),
            )
            st.success("SPC saved successfully.")

st.markdown("---")
if st.session_state.get("spc"):
    st.subheader("Saved SPC preview")
    st.write(format_spc_for_display(st.session_state["spc"]))
    st.markdown("---")
    st.subheader("Listen to SPC")
    col1, col2 = st.columns([3, 1])
    with col1:
        speech_text = format_spc_for_display(st.session_state["spc"]).replace("**", "")
        tts_text = st.text_area("Text to read aloud", value=speech_text, height=120)
    with col2:
        if st.button("🔊 Generate Audio"):
            with st.spinner("Generating audio..."):
                audio_bytes, error_msg = generate_speech(tts_text)
                if audio_bytes:
                    st.audio(audio_bytes, format="audio/wav")
                    st.success("Audio generated successfully!")
                else:
                    st.error(error_msg or "Could not generate audio. Please check your configuration.")
