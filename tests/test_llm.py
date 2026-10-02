import os
import importlib

os.environ["GROQ_MODEL"] = "llama-3.1-8b-instant"
import src.config as config_module
importlib.reload(config_module)
settings = config_module.settings

from src.llm import (
    format_spc_for_display,
    generate_clarification_questions,
    is_meaningful_text,
    validate_user_inputs,
)


def test_model_default_is_non_reasoning():
    assert settings.GROQ_MODEL == "llama-3.1-8b-instant"


def test_spc_formatting_supports_nine_field_schema():
    spc = {
        "problem_statement": "Students cannot reliably find a quiet place to study near residences.",
        "target_users": "Residence students and library users",
        "user_need": "A dependable quiet study space close to accommodation.",
        "proposed_concept": "A mobile study pod booking and wayfinding service.",
        "functional_requirements": [
            "Show study-space availability near residences",
            "Allow quick booking from a phone",
            "Highlight quiet zones and access routes",
        ],
        "constraints": "Must work with existing campus infrastructure and minimal budget.",
        "expected_benefits": "Less wasted time and more reliable study access.",
        "risks_assumptions": "Assumes the campus can support real-time availability updates.",
        "recommended_next_step": "Pilot with one residence block and measure usage.",
    }

    rendered = format_spc_for_display(spc)
    labels = [
        "Problem statement",
        "Target users",
        "User need",
        "Proposed concept",
        "Functional requirements",
        "Constraints",
        "Expected benefits",
        "Risks and assumptions",
        "Recommended next step",
    ]
    heading_positions = [rendered.index(f"**{label}**") for label in labels]
    assert heading_positions == sorted(heading_positions)

    for label in labels:
        assert f"**{label}**\n\n" in rendered

    assert "**Functional requirements**\n\n- Show study-space availability near residences" in rendered
    assert "\n- Allow quick booking from a phone" in rendered
    assert "\n- Highlight quiet zones and access routes" in rendered
    assert "quick booking from a phone\n- Highlight" in rendered


def test_generate_clarification_questions_falls_back_when_api_returns_empty(monkeypatch):
    monkeypatch.setattr(
        "src.llm._groq_json_call",
        lambda *args, **kwargs: None,
    )

    questions = generate_clarification_questions("Students cannot find quiet study space.", "Residence students")

    assert questions == [
        "What is the main user pain point you want to solve?",
        "Who is most affected by this issue?",
    ]


def test_validate_user_inputs_returns_coherent_cleanup(monkeypatch):
    monkeypatch.setattr(
        "src.llm._groq_json_call",
        lambda *args, **kwargs: {
            "validation_ok": True,
            "issue_summary": "Inputs are coherent after cleaning repeating characters.",
            "refined_problem_statement": "Students cannot reliably find a quiet place to study near residences.",
            "refined_target_users": "Residence students and library users.",
            "refined_user_need": "A consistent, low-friction quiet study space close to accommodation.",
            "refined_constraints": "Must work with existing campus resources and a minimal budget.",
            "refined_success_criteria": "Students can find and access a quiet place quickly without disruption.",
        },
    )

    result = validate_user_inputs(
        "jjkjjk",
        "hhhhkkk",
        ["What is the issue?"],
        "ghhjgh",
        "gkjkjh",
        "hjkgh",
    )

    assert result["validation_ok"] is True
    assert "quiet place" in result["refined_problem_statement"]
    assert "Residence" in result["refined_target_users"]
    assert result["refined_user_need"]


def test_validation_prompt_requires_meaning_preservation(monkeypatch):
    captured = {}

    def fake_json_call(system_prompt, user_payload, **kwargs):
        captured["system_prompt"] = system_prompt
        return {
            "validation_ok": True,
            "refined_problem_statement": "Students need accessible laptop charging between lectures.",
            "refined_target_users": "Students attending back-to-back lectures.",
            "refined_user_need": "Reliable access to laptop charging between lectures.",
            "refined_constraints": "Electrical capacity is not yet known.",
            "refined_success_criteria": "Students can charge without missing class.",
        }

    monkeypatch.setattr("src.llm._groq_json_call", fake_json_call)
    result = validate_user_inputs(
        "Students need laptop charging between lectures.",
        "Students with back-to-back classes",
        [],
        "They need power between lectures.",
        "Electrical capacity is not yet known.",
        "Students can charge without missing class.",
    )

    prompt = captured["system_prompt"]
    assert "preserving exactly the user's intended meaning" in prompt
    assert "Never add, remove, narrow, or broaden factual claims" in prompt
    assert result["refined_problem_statement"] == "Students need accessible laptop charging between lectures."


def test_validation_fallback_does_not_invent_blank_optional_fields(monkeypatch):
    monkeypatch.setattr("src.llm._groq_json_call", lambda *args, **kwargs: None)

    result = validate_user_inputs(
        "Students cannot find laptop charging between lectures.",
        "Students",
        [],
        "Students need reliable laptop power.",
        "",
        "",
    )

    assert result["validation_ok"] is True
    assert result["refined_constraints"] == ""
    assert result["refined_success_criteria"] == ""


def test_validation_fallback_rejects_meaningless_input(monkeypatch):
    monkeypatch.setattr(
        "src.llm._groq_json_call",
        lambda *args, **kwargs: None,
    )

    result = validate_user_inputs(
        "jjkjjk",
        "hhhhkkk",
        [],
        "gkjkjh",
        "",
        "",
    )

    assert result["validation_ok"] is False
    assert "clearer information" in result["issue_summary"]


def test_meaningful_short_target_group_is_accepted():
    assert is_meaningful_text("staff", minimum_length=3) is True
