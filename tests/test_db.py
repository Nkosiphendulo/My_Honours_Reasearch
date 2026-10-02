from src.db import (
    clear_storage,
    create_consent_record,
    log_prompt_response,
    save_rubric_scores,
    save_survey_responses,
    save_spc_output,
)


def test_storage_layer_handles_anonymised_flow():
    clear_storage()
    participant_code = "demo-participant"

    consent = create_consent_record("user-123", "demo", True, "Test consent")
    prompt_log = log_prompt_response("user-123", "demo", "library has no pods", "prototype idea")
    spc = save_spc_output(
        "user-123",
        "demo",
        participant_code,
        "Library study spaces are unreliable.",
        "Student-reported issue",
        "Residence students",
        "Residence users",
        [
            {"id": "FR-1", "text": "Show quiet study spaces"},
            {"id": "FR-2", "text": "Allow fast booking"},
        ],
        "Stage 3 requirements",
        [{"id": "NFR-1", "text": "Mobile-friendly"}],
        "Budget constraints",
        "No budget assumptions",
        "Users can book study space quickly",
        "Benefits observed",
        "risk",
        "assumption",
        "Pilot with one residence",
        "Next step",
    )
    rubric = save_rubric_scores("user-123", "demo", {"clarity": 4, "usefulness": 5}, "Good")
    survey = save_survey_responses("user-123", "demo", {"agency": 4, "usefulness": 4, "satisfaction": 4, "participation": 4, "notes": "Great"})

    assert consent["user_id"] == "user-123"
    assert prompt_log["user_id"] == "user-123"
    assert spc["participant_code"] == participant_code
    assert rubric["user_id"] == "user-123"
    assert survey["user_id"] == "user-123"
