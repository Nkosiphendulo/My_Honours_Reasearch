# Campus Co-Design Platform Report

**Report date:** 19 September 2026  
**Application:** Streamlit campus co-design platform  
**Local URL:** http://localhost:8501

## 1. Executive Summary

The project is a Streamlit application that guides participants from account access and consent through a structured co-design workshop, concept evaluation, and post-workshop survey. The application uses a local JSON store by default and can use Supabase when credentials are configured. It also supports optional Groq-powered assistance for clarification, validation, and concept generation.

The application started successfully and returned a valid Streamlit page over HTTP. The automated test suite completed successfully with six passing tests.

## 2. Main Functionality

The implemented participant flow is:

1. Login or signup and consent recording.
2. Five-stage workshop covering the campus problem, affected users, clarification, requirements, concept selection, and the final Structured Product Concept.
3. Evaluation using clarity, usefulness, feasibility, and inclusivity scores.
4. Survey feedback covering agency, usefulness, satisfaction, and participation.

The final concept captures a problem statement, target users, user need, proposed concept, functional requirements, constraints, expected benefits, risks or assumptions, and a recommended next step.

## 3. Technical Implementation

- **Frontend and application runtime:** Streamlit.
- **Persistence:** Local `.co_design_store.json` fallback, with optional Supabase persistence.
- **Configuration:** Environment variables loaded through `python-dotenv`.
- **Authentication:** Local username and PBKDF2-SHA256 password hashing.
- **AI integration:** Optional Groq API integration, with JSON response validation and retry handling.
- **Testing:** Pytest tests for storage behavior, SPC formatting, fallback clarification questions, and input validation.

## 4. Verification Results

| Check | Result |
|---|---|
| `pytest -q` | Passed: 6 tests |
| Streamlit startup | Passed |
| HTTP request to `http://localhost:8501/` | Passed |
| Groq availability | Depends on `GROQ_API_KEY` configuration |
| Supabase availability | Depends on `SUPABASE_URL` and `SUPABASE_KEY` configuration |

The test run produced one non-blocking deprecation warning from the installed Supabase dependency (`gotrue`).

## 5. Privacy and Data Governance

The storage layer sanitises obvious email-address and phone-number patterns in free-text fields before persistence. Participant records also use anonymised participant codes. This is aligned with the project specification, but the implementation should receive a further privacy review before production use because account usernames and display names are retained in local account records and several persisted payloads.

The local JSON file should not be committed to source control or exposed through a deployed web server. Supabase deployments should verify Row Level Security policies against the schema before accepting real participant data.

## 6. Limitations and Risks

- The workshop's live AI facilitator cannot provide API responses when `GROQ_API_KEY` is absent or invalid.
- Local fallback storage is convenient for development but is not suitable for multi-user production deployment without access controls, backups, and concurrency handling.
- The current automated tests cover helper and storage functions, but do not exercise the complete Streamlit interaction flow in a browser.
- Sanitisation targets common email and phone patterns; it is not a complete de-identification system.
- The Supabase dependency emits a deprecation warning that should be addressed during dependency maintenance.

## 7. Recommendations

1. Add browser-level smoke tests for signup, consent, workshop progression, evaluation, and survey submission.
2. Define and test the exact identity policy for usernames and display names before collecting participant data.
3. Confirm Supabase Row Level Security, service-role boundaries, and retention rules using a staging project.
4. Add a clear user-facing fallback for workshop operation when the Groq service is unavailable.
5. Replace or update the deprecated Supabase authentication dependency when the project dependency set is next revised.

## 8. Conclusion

The project is runnable in the current environment and its core automated checks pass. It provides a coherent co-design workflow and a useful development fallback, but production readiness depends on stronger end-to-end testing, explicit identity governance, verified Supabase security policies, and a defined behavior for unavailable AI services.