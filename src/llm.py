"""LLM helpers for multi-turn SPC conversation and final SPC assembly.

This module implements a lightweight, deterministic SPC drafting helper that
keeps multi-turn history and only generates a final SPC after explicit
confirmation from the user. It does not require an external LLM to function;
where an LLM is available it can be integrated later.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import re
import json
from .config import settings

try:
    from groq import Groq
except ImportError:  # pragma: no cover - optional dependency guard
    Groq = None


GROQ_FACILITATOR_PROMPT = """
ROLE
You are a co-design facilitator helping a university student at the University of Zululand turn an informal campus idea into a Structured Product Concept (SPC). You are not a generic chatbot.

WORKFLOW
1. The student describes an informal campus idea or problem.
2. Before generating anything, ask exactly ONE simple clarifying question in each response. Do not use a fixed number of questions. Continue until you know who is affected, the current situation, what a solved version would look like, and any relevant constraints.
3. Once those details are clear, send an SPC as its own message using exactly this format and nothing else:
    [SPC_START]
    Problem statement: ...
    Target users: ...
    Solution concept: ...
    Evidence/rationale: ...
    [SPC_END]
4. Ask whether the SPC accurately reflects the student's idea. If the student disagrees or requests changes, revise the four fields using their feedback and ask for confirmation again. Do not treat casual agreement before an SPC as confirmation.

CONVERSATION RULES
- Respond to the latest message. Greetings, small talk, personal comments, requests for help, confirmations, and unclear messages are not idea evidence. Respond naturally and do not ask an SPC question until the student provides an idea.
- Reflect the student's meaning in plain language. The student is not necessarily a designer, engineer, caretaker, or domain expert.
- Never require technical knowledge, exact numbers, measurements, budgets, policies, or implementation specifications. If the student does not know, record that as unknown evidence or a matter for later investigation.
- Ask only one question per response and wait for the student's answer.
- Never repeat a question that has already been asked and answered. Use the conversation history to ask for the next missing detail.
- Never fabricate details, requirements, affected users, evidence, costs, or outcomes. Keep suggestions clearly separate from what the student said.
- Use supportive, plain-language, non-technical wording.
- Keep `reply` under 80 words. Ask one short question or provide the SPC block; do not explain your reasoning.
- Do not output `<think>` tags or any internal reasoning. Return the JSON object immediately.

Return valid JSON only with exactly these keys:
{"reply":"...","ready_for_generation":false,"asks_generate":false,"reset_conversation":false,"question_count":0,"spc_confirmed":false}
Set ready_for_generation and asks_generate to true only when the SPC block has been presented. Set spc_confirmed to true only after the student confirms the presented SPC. Never invent details; the evidence field must refer to the student's words.
""".strip()


_MEANINGLESS_VALUES = {
    "test",
    "none",
    "n/a",
    "na",
    "unknown",
    "asdf",
    "asdfgh",
}


def is_meaningful_text(value: str, minimum_length: int = 8) -> bool:
    """Reject blank, placeholder, repeated-character, and keyboard-smash input."""
    text = re.sub(r"\s+", " ", (value or "").strip().lower())
    if len(text) < minimum_length or text in _MEANINGLESS_VALUES:
        return False

    if re.search(r"(.)\1{2,}", text):
        return False

    letters = re.sub(r"[^a-z]", "", text)
    # Character diversity is useful for short keyboard-smash strings, but
    # normal sentences naturally reuse letters across many words.
    if 6 <= len(letters) <= 20 and len(set(letters)) / len(letters) < 0.4:
        return False
    if len(letters) >= 6 and not re.search(r"[aeiou]", letters):
        return False

    return True


def _repeats_previous_question(reply: str, messages: List[Dict[str, str]]) -> bool:
    """Reject an API reply that repeats an earlier assistant question verbatim."""
    normalise = lambda text: re.sub(r"\s+", " ", text.strip().lower())
    previous_questions = {
        normalise(question)
        for message in messages
        if message.get("role") == "assistant"
        for question in re.findall(r"[^?]{10,}\?", str(message.get("message", "")))
    }
    return any(
        normalise(question) in previous_questions
        for question in re.findall(r"[^?]{10,}\?", reply)
    )


def _api_conversation(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Keep the API context compact while retaining the original idea and latest turns."""
    conversation = [
        message for message in messages
        if message.get("role") in {"user", "assistant"}
    ]
    if len(conversation) <= 8:
        return conversation
    return [conversation[0], *conversation[-7:]]


def _groq_chat_spc(messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """Ask Groq to facilitate the conversation and return validated metadata."""
    if Groq is None:
        return {"reply": "The Groq client is not installed. API responses are unavailable.", "llm_provider": "groq_error"}
    if not settings.GROQ_API_KEY:
        return {"reply": "GROQ_API_KEY is not configured. API responses are unavailable.", "llm_provider": "groq_error"}

    api_messages = [{"role": "system", "content": GROQ_FACILITATOR_PROMPT}]
    for message in _api_conversation(messages):
        role = message.get("role")
        if role in {"user", "assistant"}:
            api_messages.append({"role": role, "content": str(message.get("message", ""))})

    try:
        client = Groq(api_key=settings.GROQ_API_KEY)
        for attempt in range(2):
            request_messages = list(api_messages)
            if attempt == 1:
                request_messages.append({
                    "role": "system",
                    "content": "Your previous response was invalid or repeated an answered question. Ask only the next unanswered clarifying question, or provide the SPC if the details are complete.",
                })
            request_options = {
                "model": settings.GROQ_MODEL,
                "messages": request_messages,
                "temperature": 0.3,
                "max_tokens": 1000,
                "reasoning_effort": "none",
            }
            if settings.GROQ_MODEL.startswith("qwen/"):
                request_options["reasoning_format"] = "hidden"
            response = client.chat.completions.create(**request_options)
            content = response.choices[0].message.content or ""

            if re.search(r"<think>", content, flags=re.I) and not re.search(r"</think>", content, flags=re.I):
                if attempt == 0:
                    continue
                return None

            parsed = None
            for start in (index for index, character in enumerate(content) if character == "{"):
                try:
                    candidate, _ = json.JSONDecoder().raw_decode(content[start:])
                    if isinstance(candidate, dict) and "reply" in candidate:
                        candidate_reply = str(candidate.get("reply", "")).strip()
                        if candidate_reply and not _repeats_previous_question(candidate_reply, messages):
                            parsed = candidate
                        break
                except json.JSONDecodeError:
                    continue

            if parsed is not None:
                break

            if attempt == 1:
                return None

        if parsed is None:
            visible_content = re.sub(r"<think>.*?</think>", "", content, flags=re.S | re.I).strip()
            if not visible_content:
                return None
            return {
                "reply": visible_content,
                "asks_generate": False,
                "ready_for_generation": False,
                "reset_conversation": False,
                "llm_provider": "groq",
            }
        reply = str(parsed.get("reply", "")).strip()
        if not reply:
            return {"reply": "The Groq API returned an empty response.", "llm_provider": "groq_error"}
        if re.search(r"<think>|</think>", reply, flags=re.I):
            reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.S | re.I).strip()
            if not reply or re.search(r"<think>", reply, flags=re.I):
                return None
        return {
            "reply": reply,
            "asks_generate": bool(parsed.get("asks_generate", False)),
            "ready_for_generation": bool(parsed.get("ready_for_generation", False)),
            "reset_conversation": bool(parsed.get("reset_conversation", False)),
            "question_count": int(parsed.get("question_count", 0) or 0),
            "spc_confirmed": bool(parsed.get("spc_confirmed", False)),
            "llm_provider": "groq",
        }
    except Exception as exc:
        return {
            "reply": f"I could not reach the Groq API: {exc}",
            "asks_generate": False,
            "ready_for_generation": False,
            "llm_provider": "groq_error",
        }


def chat_spc(messages: List[Dict[str, str]], username: Optional[str] = None) -> Dict[str, Any]:
    """Use only the Groq API for facilitator responses."""
    result = _groq_chat_spc(messages)
    if result is None:
        return {
            "reply": "The API response was incomplete, so I could not safely show it. Please send your message again.",
            "asks_generate": False,
            "ready_for_generation": False,
            "llm_provider": "groq_error",
        }
    return result


def parse_spc_block(reply: str) -> Dict[str, Any] | None:
    """Parse the legacy 4-field block and the new 9-field SPC format."""
    legacy_match = re.search(
        r"\[SPC_START\]\s*"
        r"Problem statement:\s*(.*?)\s*"
        r"Target users:\s*(.*?)\s*"
        r"Solution concept:\s*(.*?)\s*"
        r"Evidence/rationale:\s*(.*?)\s*"
        r"\[SPC_END\]",
        reply,
        flags=re.S,
    )
    if legacy_match:
        problem, target_users, solution, evidence = (part.strip() for part in legacy_match.groups())
        return {
            "problem_statement": problem,
            "target_users": target_users,
            "user_need": "",
            "proposed_concept": solution,
            "functional_requirements": [{"id": "SC-1", "text": solution}],
            "constraints": "",
            "expected_benefits": evidence,
            "risks_assumptions": "",
            "recommended_next_step": "",
        }

    new_match = re.search(
        r"\[SPC_START\]\s*"
        r"Problem statement:\s*(.*?)\s*"
        r"Target users:\s*(.*?)\s*"
        r"User need:\s*(.*?)\s*"
        r"Proposed concept:\s*(.*?)\s*"
        r"Functional requirements:\s*(.*?)\s*"
        r"Constraints:\s*(.*?)\s*"
        r"Expected benefits:\s*(.*?)\s*"
        r"Risks and assumptions:\s*(.*?)\s*"
        r"Recommended next step:\s*(.*?)\s*"
        r"\[SPC_END\]",
        reply,
        flags=re.S,
    )
    if not new_match:
        return {}

    (
        problem_statement,
        target_users,
        user_need,
        proposed_concept,
        functional_requirements,
        constraints,
        expected_benefits,
        risks_assumptions,
        recommended_next_step,
    ) = (part.strip() for part in new_match.groups())

    fr_items = []
    if functional_requirements:
        for index, item in enumerate(re.split(r"\n+|-\s*", functional_requirements), start=1):
            text = item.strip()
            if text:
                fr_items.append({"id": f"FR-{index}", "text": text})

    return {
        "problem_statement": problem_statement,
        "target_users": target_users,
        "user_need": user_need,
        "proposed_concept": proposed_concept,
        "functional_requirements": fr_items or [{"id": "FR-1", "text": proposed_concept}],
        "constraints": constraints,
        "expected_benefits": expected_benefits,
        "risks_assumptions": risks_assumptions,
        "recommended_next_step": recommended_next_step,
    }


def format_spc_for_display(spc: Dict[str, Any]) -> str:
    """Render legacy or current SPC data as consistently separated Markdown sections."""
    if not spc:
        return ""

    normalized = {
        "problem_statement": spc.get("problem_statement") or spc.get("overview") or spc.get("problem"),
        "target_users": spc.get("target_users") or spc.get("target_user") or spc.get("audience"),
        "user_need": spc.get("user_need") or spc.get("need") or spc.get("user_need_summary"),
        "proposed_concept": spc.get("proposed_concept") or spc.get("solution_concept") or spc.get("solution"),
        "functional_requirements": spc.get("functional_requirements") or [],
        "constraints": spc.get("constraints") or spc.get("assumptions_constraints") or "",
        "expected_benefits": spc.get("expected_benefits") or spc.get("evidence") or "",
        "risks_assumptions": spc.get("risks_assumptions") or spc.get("risks") or "",
        "recommended_next_step": spc.get("recommended_next_step") or spc.get("next_step") or "",
    }

    requirements = normalized["functional_requirements"]
    if isinstance(requirements, str):
        requirement_items = [item.strip() for item in re.split(r"\n+", requirements) if item.strip()]
    else:
        requirement_items = []
        for requirement in requirements:
            if isinstance(requirement, dict):
                text = requirement.get("text") or requirement.get("requirement") or ""
            else:
                text = str(requirement)
            if text.strip():
                requirement_items.append(text.strip())

    sections = [
        ("Problem statement", normalized["problem_statement"]),
        ("Target users", normalized["target_users"]),
        ("User need", normalized["user_need"]),
        ("Proposed concept", normalized["proposed_concept"]),
        (
            "Functional requirements",
            "\n".join(f"- {item}" for item in requirement_items) or "Not provided",
        ),
        ("Constraints", normalized["constraints"]),
        ("Expected benefits", normalized["expected_benefits"]),
        ("Risks and assumptions", normalized["risks_assumptions"]),
        ("Recommended next step", normalized["recommended_next_step"]),
    ]
    return "\n\n".join(
        f"**{label}**\n\n{value or 'Not provided'}"
        for label, value in sections
    )


def _groq_json_call(system_prompt: str, user_payload: Dict[str, Any], *, max_tokens: int = 800) -> Optional[Dict[str, Any]]:
    """Call Groq with a compact JSON prompt and return a parsed object."""
    if Groq is None:
        return None
    if not settings.GROQ_API_KEY:
        return None

    try:
        client = Groq(api_key=settings.GROQ_API_KEY)
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            temperature=0.3,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        payload = json.loads(content)
        if isinstance(payload, dict):
            return payload
    except Exception:
        return None
    return None


def generate_clarification_questions(problem_statement: str, target_users: str) -> List[str]:
    """Create up to two focused follow-up questions for the bounded wizard."""
    fallback_questions = [
        "What is the main user pain point you want to solve?",
        "Who is most affected by this issue?",
    ]

    result = _groq_json_call(
        "You are a campus co-design facilitator. Return JSON only with a 'clarification_questions' list of up to two short, specific questions. Keep them grounded in the participant's problem and affected users.",
        {
            "problem_statement": problem_statement,
            "target_users": target_users,
        },
    )
    if not result:
        return fallback_questions

    questions = result.get("clarification_questions") or []
    cleaned = [str(item).strip() for item in questions[:2] if str(item).strip()]
    if cleaned:
        return cleaned
    return fallback_questions


def generate_concept_options(
    problem_statement: str,
    target_users: str,
    clarification_answers: List[str],
    user_need: str,
    constraints: str,
    success_criteria: str,
) -> List[Dict[str, str]]:
    """Generate up to two bounded solution alternatives in compact structured JSON."""
    fallback_options = [
        {
            "title": "Low-friction campus service",
            "summary": "Create a simple service that helps affected students identify the fastest, least disruptive path to a workable solution using existing campus resources.",
        },
        {
            "title": "Student-led pilot concept",
            "summary": "Run a small pilot with a defined user group to test demand, gather feedback, and refine the idea before wider rollout.",
        },
    ]

    result = _groq_json_call(
        "You are a campus co-design facilitator. Return JSON only with a 'concept_options' array of 1 to 2 objects. Each object must include 'title' and 'summary' and stay grounded in the user's need and constraints.",
        {
            "problem_statement": problem_statement,
            "target_users": target_users,
            "clarification_answers": clarification_answers,
            "user_need": user_need,
            "constraints": constraints,
            "success_criteria": success_criteria,
        },
    )
    if not result:
        return fallback_options

    raw_options = result.get("concept_options") or []
    options: List[Dict[str, str]] = []
    for option in raw_options[:2]:
        if isinstance(option, dict):
            title = str(option.get("title") or "Concept option").strip()
            summary = str(option.get("summary") or option.get("concept") or "").strip()
            if title and summary:
                options.append({"title": title, "summary": summary})
    if options:
        return options
    return fallback_options


def validate_user_inputs(
    problem_statement: str,
    target_users: str,
    clarification_answers: List[str],
    user_need: str,
    constraints: str,
    success_criteria: str,
) -> Dict[str, Any]:
    """Ask the LLM to validate and refine the user inputs before final SPC generation."""
    result = _groq_json_call(
        "You are a careful proofreader and co-design facilitator. Validate whether the user's inputs are coherent and useful for a campus product concept. Return JSON only with these keys: validation_ok, issue_summary, refined_problem_statement, refined_target_users, refined_user_need, refined_constraints, refined_success_criteria. Correct spelling, grammar, and readability while preserving exactly the user's intended meaning. You may paraphrase only when the replacement is strictly equivalent. Never add, remove, narrow, or broaden factual claims, affected groups, causes, frequency, severity, constraints, or success criteria. Preserve uncertainty and qualifiers. Do not turn suggestions or assumptions into facts. If any field is ambiguous or you cannot confidently preserve its meaning, return that field unchanged and explain what needs clarification in issue_summary. Do not replace missing user information with generic content. Set validation_ok to false only when the information is too unclear or contradictory to proceed.",
        {
            "problem_statement": problem_statement,
            "target_users": target_users,
            "clarification_answers": clarification_answers,
            "user_need": user_need,
            "constraints": constraints,
            "success_criteria": success_criteria,
        },
    )

    if not result:
        fields = {
            "problem statement": problem_statement,
            "target users": target_users,
            "user need": user_need,
        }
        invalid_fields = [
            name for name, value in fields.items()
            if not is_meaningful_text(value, minimum_length=3 if name == "target users" else 8)
        ]
        if invalid_fields:
            return {
                "validation_ok": False,
                "issue_summary": (
                    "Please provide clearer information for: "
                    + ", ".join(invalid_fields)
                    + ". Avoid random characters or placeholder text."
                ),
                "refined_problem_statement": (problem_statement or "").strip(),
                "refined_target_users": (target_users or "").strip(),
                "refined_user_need": (user_need or "").strip(),
                "refined_constraints": (constraints or "").strip(),
                "refined_success_criteria": (success_criteria or "").strip(),
            }

        return {
            "validation_ok": True,
            "issue_summary": "The API was unavailable, so the original information was retained.",
            "refined_problem_statement": problem_statement.strip(),
            "refined_target_users": target_users.strip(),
            "refined_user_need": user_need.strip(),
            "refined_constraints": (constraints or "").strip(),
            "refined_success_criteria": (success_criteria or "").strip(),
        }

    validation_ok = bool(result.get("validation_ok", False))
    return {
        "validation_ok": validation_ok,
        "issue_summary": str(result.get("issue_summary") or "Inputs were reviewed.").strip(),
        "refined_problem_statement": str(result.get("refined_problem_statement") or problem_statement or "").strip(),
        "refined_target_users": str(result.get("refined_target_users") or target_users or "").strip(),
        "refined_user_need": str(result.get("refined_user_need") or user_need or "").strip(),
        "refined_constraints": str(result.get("refined_constraints") or constraints or "").strip(),
        "refined_success_criteria": str(result.get("refined_success_criteria") or success_criteria or "").strip(),
    }
