from src.db import (
    clear_storage,
    create_consent_record,
    log_prompt_response,
    save_rubric_scores,
    save_spc,
    save_survey_responses,
)


def test_storage_layer_handles_anonymised_flow():
    clear_storage()
    participant_code = "demo-participant"

    consent = create_consent_record(participant_code, True, "Test consent")
    prompt_log = log_prompt_response(participant_code, "library has no pods", "prototype idea")
    spc = save_spc(participant_code, {"problem_statement": "Test", "target_user": "students", "solution_concept": "Pods", "evidence": "Needs"})
    rubric = save_rubric_scores(participant_code, {"clarity": 4, "usefulness": 5}, "Good")
    survey = save_survey_responses(participant_code, {"agency": 4, "usefulness": 4, "satisfaction": 4, "participation": 4, "notes": "Great"})

    assert consent["participant_code"] == participant_code
    assert prompt_log["participant_code"] == participant_code
    assert spc["participant_code"] == participant_code
    assert rubric["participant_code"] == participant_code
    assert survey["participant_code"] == participant_code
