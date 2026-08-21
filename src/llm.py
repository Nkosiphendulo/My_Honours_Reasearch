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
from .db import LOCAL_STORE
from .config import settings

try:
    from groq import Groq
except ImportError:  # pragma: no cover - optional dependency guard
    Groq = None


SYSTEM_PROMPT = (
    "You are a co-design assistant helping a university student turn a rough campus-related idea "
    "into a Structured Product Concept (SPC). Your role is to mediate and teach — ask clarifying "
    "questions (2-4) to build the Overview, Target Users, and Functional Requirements. Offer 1-2 short "
    "suggestions or alternative angles, draft reasonable Non-Functional Requirements, Assumptions & "
    "Constraints, and Expected Benefits, but always ask for confirmation before generating the final SPC. "
    "Use plain, encouraging language and never invent functional requirements that the student hasn't stated."
)

GROQ_FACILITATOR_PROMPT = """
ROLE
You are a co-design facilitator helping a university student at the University of Zululand turn an informal campus idea into a Structured Product Concept (SPC). You are not a generic chatbot.

WORKFLOW
1. The student describes an informal campus idea or problem.
2. Before generating anything, ask exactly ONE simple clarifying question in each response. Ask 2 to 4 questions total across the current idea conversation. Do not ask a second question in the same response. Suitable questions cover who is affected, what has been tried, what a solved version looks like, and relevant constraints. Stop asking once two questions have been answered and the idea is sufficiently clear; never generate before at least two questions have been answered.
3. After the question phase, present an SPC containing exactly these four clearly labelled fields and no additional SPC fields: Problem statement, Target users, Solution concept, Evidence/rationale.
4. Ask whether the SPC accurately reflects the student's idea. If the student disagrees or requests changes, revise the four fields using their feedback and ask for confirmation again. Do not treat casual agreement before an SPC as confirmation.

CONVERSATION RULES
- Respond to the latest message. Greetings, small talk, personal comments, requests for help, confirmations, and unclear messages are not idea evidence. Respond naturally and do not ask an SPC question until the student provides an idea.
- Reflect the student's meaning in plain language. The student is not necessarily a designer, engineer, caretaker, or domain expert.
- Never require technical knowledge, exact numbers, measurements, budgets, policies, or implementation specifications. If the student does not know, record that as unknown evidence or a matter for later investigation.
- Ask only one question per response and wait for the student's answer.
- Never fabricate details, requirements, affected users, evidence, costs, or outcomes. Keep suggestions clearly separate from what the student said.
- Use supportive, plain-language, non-technical wording.

Return valid JSON only with exactly these keys:
{"reply":"...","ready_for_generation":false,"asks_generate":false,"reset_conversation":false,"question_count":0,"spc_confirmed":false}
Set ready_for_generation and asks_generate to true only when the SPC has been presented after at least two answered clarifying questions. Set spc_confirmed to true only after the student confirms the presented SPC.
""".strip()


def _most_recent_user_message(messages: List[Dict[str, str]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user" and _is_substantive_user_message(msg.get("message", "")):
            return msg.get("message", "")
    return ""


def _is_substantive_user_message(text: str) -> bool:
    """Return False for conversational turns that are not idea evidence."""
    normalized = re.sub(r"[^a-z\s'-]", "", (text or "").strip().lower())
    return bool(normalized and normalized not in {
        "hey", "hello", "hi", "helo", "yoh", "yes", "yeah", "yep", "no", "okay", "ok",
        "sure", "thanks", "thank you", "what is the date today", "what about time",
    })


def _classify_user_turn(text: str) -> str:
    """Classify a turn before treating it as evidence for an SPC."""
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not normalized:
        return "empty"
    if re.fullmatch(r"(?:hey|hello|hi|helo|yoh|yo|good morning|good afternoon|good evening)[!. ]*", normalized):
        return "greeting"
    if re.search(r"\b(how are you|how is it going|what can you do|who are you)\b", normalized):
        return "small_talk"
    if re.search(r"\b(what day is it|what is the date|what time is it|what's the time|current time)\b", normalized):
        return "small_talk"
    if re.search(r"\b(i had a bad day|bad day|i want to go home|i'm tired|i am tired|i feel)\b", normalized):
        return "personal_talk"
    if re.search(r"\b(does this make sense|do you understand|are you following)\b", normalized):
        return "check_understanding"
    if re.search(r"\b(i have an idea|i've got an idea|i want you to help|help me (translate|formalise|formalize|rewrite)|make it formal)\b", normalized):
        return "request_help"
    if re.search(r"\b(i have not|i haven't|not yet|i am not|i'm not|haven't yet)\b", normalized) and re.search(
        r"\b(idea|solution|problem|provided|given|explained|told)\b", normalized
    ):
        return "not_ready"
    if re.fullmatch(r"[a-z]{1,3}(?:[a-z]{1,3}){2,}[!.? ]*", normalized) and len(normalized.split()) == 1:
        return "unclear"
    if normalized in {"yes", "yeah", "yep", "no", "okay", "ok", "sure", "thanks", "thank you"}:
        return "confirmation"
    return "content" if _is_substantive_user_message(text) else "unclear"


def _current_conversation_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Ignore earlier saved conversations after the user starts a new idea."""
    start = 0
    for index, message in enumerate(messages):
        if message.get("role") == "user" and _classify_user_turn(message.get("message", "")) == "request_help":
            start = index
    return messages[start:]


def _aggregate_user_idea(messages: List[Dict[str, str]]) -> str:
    parts = []
    for msg in messages:
        if msg.get("role") == "user" and _classify_user_turn(msg.get("message", "")) == "content":
            text = (msg.get("message") or "").strip()
            if text:
                parts.append(text)
    return " ".join(parts)


def _extract_requirements_from_text(text: str) -> List[str]:
    # Very simple heuristic: split on sentences and keep those with verbs like 'must', 'should', 'able to', 'allow'
    reqs = []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for s in sentences:
        if re.search(r"\b(must|should|able to|allow|enable|require)\b", s, flags=re.I):
            reqs.append(s.strip())
    # fallback: create a short list from the text if no explicit req sentences
    if not reqs and len(text) > 20:
        teaser = text.strip()
        words = teaser.split()
        # create up to 3 simple functional bullets from clauses
        reqs = ["Provide an interface to: " + " ".join(words[:min(6, len(words))]) + "...",
                "Allow users to submit details and attachments.",
                "Store anonymised participant data for follow-up research."]
    return reqs


def _has_explicit_functional_requirement(text: str) -> bool:
    return bool(re.search(r"\b(must|should|need to|able to|allow|enable|require|provide|support)\b", text or "", re.I))


def _formalise_idea(user_agg: str) -> str:
    """Turn an informal idea into a technician-readable draft without inventing facts."""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", user_agg.strip()) if part.strip()]
    solution_sentences = [
        sentence for sentence in sentences
        if re.search(r"\b(install|add|build|create|provide|introduce|use|should|must|need to|system)\b", sentence, re.I)
    ]
    problem_sentences = [sentence for sentence in sentences if sentence not in solution_sentences]
    problem = " ".join(problem_sentences) or user_agg.strip()
    proposed_solution = " ".join(solution_sentences) or "The user has suggested improving the service in the affected area."
    return (
        "Formalised idea:\n"
        f"- Observed situation: {problem[:700]}\n"
        f"- User-proposed solution: {proposed_solution[:500]}\n"
        "- Formal implementation direction: Investigate the proposed solution and design an appropriate "
        "intervention for the people and setting described by the user.\n"
        "- Investigation required: The relevant practitioners should confirm the cause, feasibility, "
        "resources, risks, cost, implementation approach, and maintenance or follow-up needs."
    )


def _local_chat_spc(messages: List[Dict[str, str]], username: Optional[str] = None) -> Dict[str, Any]:
    """Process a multi-turn conversation and return assistant reply plus flags.

    Returns a dict with:
    - reply: assistant text
    - asks_generate: bool indicating whether assistant asked to generate final SPC
    - ready_for_generation: bool indicating assistant believes it has enough to draft
    """
    latest_user = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            latest_user = message.get("message", "")
            break
    latest_kind = _classify_user_turn(latest_user)
    conversation_messages = _current_conversation_messages(messages)
    user_agg = _aggregate_user_idea(conversation_messages)
    recent = _most_recent_user_message(messages)
    question_count = sum(
        1 for message in conversation_messages
        if message.get("role") == "assistant" and "?" in message.get("message", "")
    )

    if latest_kind == "greeting":
        return {
            "reply": "Hello! I am here when you are ready. You can chat with me, or describe a campus problem or idea when you want help formalising it.",
            "asks_generate": False,
            "ready_for_generation": False,
        }
    if latest_kind == "small_talk":
        return {
            "reply": "I can help turn an informal campus idea into a clear formal concept. Whenever you are ready, tell me what you have noticed or what you think could improve.",
            "asks_generate": False,
            "ready_for_generation": False,
        }
    if latest_kind == "personal_talk":
        return {
            "reply": "I am sorry today has been difficult. We can pause the workshop. When you are ready, you can tell me whether you want to continue with your idea or start again later.",
            "asks_generate": False,
            "ready_for_generation": False,
        }
    if latest_kind == "check_understanding":
        return {
            "reply": "Yes, I understand that you want to give me an informal idea and have me help express it clearly and formally. I will ask only about details that are needed to understand your meaning.",
            "asks_generate": False,
            "ready_for_generation": False,
        }
    if latest_kind == "request_help":
        return {
            "reply": "Of course, I can help you with that. Take your time and tell me the idea just as it comes to you. It does not have to sound formal or complete. I will first listen to what you mean, then help you express it clearly for someone who may need to develop or evaluate it.",
            "asks_generate": False,
            "ready_for_generation": False,
            "reset_conversation": True,
        }
    if latest_kind == "not_ready":
        return {
            "reply": "That is fine. I will wait for your idea. Please describe what problem you have noticed and what you think might improve it.",
            "asks_generate": False,
            "ready_for_generation": False,
        }
    if latest_kind == "unclear":
        return {
            "reply": "I did not understand that message as an idea yet. Please describe a campus problem, who seems affected, or a possible improvement. You can use simple everyday language.",
            "asks_generate": False,
            "ready_for_generation": False,
        }

    # If there is no user content yet
    if not user_agg.strip():
        return {
            "reply": "Tell me the idea in your own words. You do not need technical knowledge or exact numbers; describe what you have noticed and what you think could help.",
            "asks_generate": False,
            "ready_for_generation": False,
        }

    # Require evidence for each core SPC section before offering generation.
    overview_ok = len(user_agg.split()) >= 12 and bool(
        re.search(
            r"\b(problem|need|challenge|difficult|lack|weak|slow|unsafe|unavailable|overcrowded|"
            r"expensive|struggle|unable|cannot|can't|wait|currently|because|not enough|no access)\b",
            user_agg,
            re.I,
        )
    )
    target_ok = any(
        re.search(
            r"student|staff|faculty|visitor|researcher|admin|resident|commuter|lecturer|"
            r"worker|patient|customer|user|community|everyone|people",
            m.get("message", ""),
            flags=re.I,
        )
        for m in conversation_messages
        if m.get("role") == "user"
    )
    functional_reqs = []
    for m in conversation_messages:
        if m.get("role") == "user" and _is_substantive_user_message(m.get("message", "")):
            message = m.get("message", "")
            if _has_explicit_functional_requirement(message):
                functional_reqs.extend(_extract_requirements_from_text(message))

    functional_ok = len(functional_reqs) >= 1

    # Ask for one missing piece at a time so the user can describe the idea naturally.
    if not overview_ok:
        return {"reply": f"I think you are describing this so far: ‘{user_agg[:300]}’\n\nI want to make sure I understand you correctly. What is the main difficulty people experience because of this situation? You can explain it from your own experience, and you can say ‘I don’t know’ if you have not checked.", "asks_generate": False, "ready_for_generation": False}
    if not target_ok:
        return {"reply": f"That helps me understand the situation. In your words, the idea is about: ‘{user_agg[:300]}’\n\nWho do you think would benefit from solving it? You do not need an exact number. Just mention the people you believe are affected, or say that you are not sure.", "asks_generate": False, "ready_for_generation": False}
    if not functional_ok:
        return {"reply": "I understand who may be affected. Now, what change would you like them to experience? You can describe the outcome in everyday language, such as ‘people should connect more reliably’ or ‘students should find help more easily’. You do not need to specify the technical solution.", "asks_generate": False, "ready_for_generation": False}

    # Offer 1-2 short suggestions or alternative angles
    suggestions = [
        "Consider whether this could be piloted with a single faculty department before campus-wide rollout.",
        "Think about integrating with existing campus systems (e.g. timetable or helpdesk) to reduce friction.",
    ]
    suggestion_text = "Here are a couple of short suggestions you might consider:\n- " + "\n- ".join(suggestions[:2])

    # Draft Non-Functional, Assumptions, Expected Benefits from user_agg
    nonfunctional = [
        {"id": "NFR-1", "text": "Protect participant privacy: no direct identifiers stored; data anonymised."},
        {"id": "NFR-2", "text": "Accessible via campus SSO or simple username; mobile-friendly interface."},
        {"id": "NFR-3", "text": "Response latency acceptable for interactive chat (under 3s for UI actions)."},
    ]
    assumptions = "Assume availability of basic campus IT infrastructure and opt-in consent from participants."
    expected_benefits = "Improved capture of campus needs, faster ideation, and stronger evidence for small pilots."

    # If we reach here, we have enough to assemble drafts for NFRs, assumptions, benefits
    reply_lines = [
        f"Thank you, I understand your idea as: ‘{user_agg[:500]}’",
        _formalise_idea(user_agg),
        "This keeps your suggestion as a proposed direction. It does not assume that the suggested equipment is definitely the correct technical solution.",
        "Does this formal version represent what you meant? You can say ‘yes’, correct it, or add more detail. If you do not know a technical answer, say ‘I don’t know’ and I will mark it for technical investigation.",
        suggestion_text,
        "When you confirm the wording, you can generate the full SPC.",
    ]
    reply = "\n\n".join(reply_lines)

    return {
        "reply": reply,
        "asks_generate": question_count >= 2,
        "ready_for_generation": question_count >= 2,
        "question_count": question_count,
    }


def _groq_chat_spc(messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """Ask Groq to facilitate the conversation and return validated metadata."""
    if Groq is None or not settings.GROQ_API_KEY:
        return None

    conversation = _current_conversation_messages(messages)
    api_messages = [{"role": "system", "content": GROQ_FACILITATOR_PROMPT}]
    for message in conversation:
        role = message.get("role")
        if role in {"user", "assistant"}:
            api_messages.append({"role": role, "content": str(message.get("message", ""))})

    try:
        client = Groq(api_key=settings.GROQ_API_KEY)
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=api_messages,
            temperature=0.3,
        )
        content = response.choices[0].message.content or ""
        parsed = None
        for start in (index for index, character in enumerate(content) if character == "{"):
            try:
                candidate, _ = json.JSONDecoder().raw_decode(content[start:])
                if isinstance(candidate, dict) and "reply" in candidate:
                    parsed = candidate
            except json.JSONDecodeError:
                continue

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
            return None
        return {
            "reply": reply,
            "asks_generate": bool(parsed.get("asks_generate", False)),
            "ready_for_generation": bool(parsed.get("ready_for_generation", False)) and int(parsed.get("question_count", 0) or 0) >= 2,
            "reset_conversation": bool(parsed.get("reset_conversation", False)),
            "question_count": int(parsed.get("question_count", 0) or 0),
            "spc_confirmed": bool(parsed.get("spc_confirmed", False)),
            "llm_provider": "groq",
        }
    except Exception:
        if not settings.USE_LOCAL_FALLBACK:
            return {
                "reply": "I could not reach the conversation assistant right now. Please check the Groq connection and try again.",
                "asks_generate": False,
                "ready_for_generation": False,
                "llm_provider": "groq_error",
            }
        return None


def chat_spc(messages: List[Dict[str, str]], username: Optional[str] = None) -> Dict[str, Any]:
    """Use Groq for the facilitator conversation, with an optional local fallback."""
    groq_result = _groq_chat_spc(messages)
    if groq_result is not None:
        return groq_result
    result = _local_chat_spc(messages, username=username)
    result["llm_provider"] = "local_fallback"
    return result


def generate_final_spc(messages: List[Dict[str, str]], username: Optional[str], participant_code: str) -> Dict[str, Any]:
    """Create the final SPC structure with six sections and traced-from notes.

    This function uses simple heuristics over the message history to populate
    each section and includes a short "traced_from" note for traceability.
    """
    user_agg = _aggregate_user_idea(_current_conversation_messages(messages))
    recent_user = _most_recent_user_message(messages)

    overview = (user_agg.strip()[:1000])
    overview_traced = f"From combined user inputs: '{recent_user[:200]}'"

    # target users: search for known roles
    roles = []
    for m in messages:
        if m.get("role") == "user":
            found = re.findall(r"\b(first-year students|students|staff|faculty|researchers|visitors|administrators|admins)\b", m.get("message",""), flags=re.I)
            roles.extend(found)
    target_users = ", ".join(dict.fromkeys([r for r in roles if r])) or "Students and campus staff"
    target_users_traced = f"From user's statements: '{recent_user[:200]}'"

    # functional requirements extracted heuristically
    func_reqs = _extract_requirements_from_text(user_agg)
    if not func_reqs:
        func_reqs = [
            {"id": "FR-1", "text": "Allow users to submit a campus need description."},
            {"id": "FR-2", "text": "Provide a guided chat assistant to refine the need into an SPC."},
            {"id": "FR-3", "text": "Export the SPC for evaluation and survey follow-up."},
        ]
    else:
        # normalize into dicts
        func_reqs = [{"id": f"FR-{i+1}", "text": t} for i, t in enumerate(func_reqs)]

    func_traced = f"Extracted from user messages: '{recent_user[:200]}'"

    # non-functional requirements drafted
    nfrs = [
        {"id": "NFR-1", "text": "Data anonymisation: no direct identifiers stored."},
        {"id": "NFR-2", "text": "Usable on desktop and mobile devices; accessible UI."},
        {"id": "NFR-3", "text": "Reasonable performance for interactive use."},
    ]
    nfr_traced = "Drafted from conversation context and platform defaults."

    assumptions = "Participants consent to anonymous data collection; integration with campus authentication is optional."
    assumptions_traced = "Derived from standard platform assumptions."

    benefits = "Faster ideation, evidence capture for pilots, and better alignment of projects with user needs."
    benefits_traced = "Based on user-provided problem and expected outcomes."

    final = {
        "overview": overview,
        "overview_traced_from": overview_traced,
        "target_users": target_users,
        "target_users_traced_from": target_users_traced,
        "functional_requirements": func_reqs,
        "functional_requirements_traced_from": func_traced,
        "nonfunctional_requirements": nfrs,
        "nonfunctional_requirements_traced_from": nfr_traced,
        "assumptions_constraints": assumptions,
        "assumptions_constraints_traced_from": assumptions_traced,
        "expected_benefits": benefits,
        "expected_benefits_traced_from": benefits_traced,
        "participant_code": participant_code,
    }

    return final


def format_spc_for_display(spc: Dict[str, Any]) -> str:
    """Render either legacy or new SPC structure as a readable display string.

    Supports old keys (`need`, `problem_statement`, `target_user`, `solution_concept`, `evidence`)
    and new structured fields produced by `generate_final_spc`.
    """
    if not spc:
        return ""

    # New-style final SPC
    if "overview" in spc or "functional_requirements" in spc:
        parts = []
        if spc.get("overview"):
            parts.append(f"Overview: {spc.get('overview')}")
        if spc.get("target_users"):
            parts.append(f"Target users: {spc.get('target_users')}")
        if spc.get("functional_requirements"):
            frs = spc.get("functional_requirements")
            if isinstance(frs, list):
                parts.append("Functional requirements:")
                for fr in frs:
                    if isinstance(fr, dict):
                        parts.append(f"- {fr.get('id','')}: {fr.get('text','')}")
                    else:
                        parts.append(f"- {str(fr)}")
        if spc.get("nonfunctional_requirements"):
            nfrs = spc.get("nonfunctional_requirements")
            parts.append("Non-functional requirements:")
            for n in nfrs:
                parts.append(f"- {n.get('id','')}: {n.get('text','')}")
        if spc.get("assumptions_constraints"):
            parts.append(f"Assumptions & Constraints: {spc.get('assumptions_constraints')}")
        if spc.get("expected_benefits"):
            parts.append(f"Expected benefits: {spc.get('expected_benefits')}")
        return "\n".join(parts)

    # Legacy-style SPC
    lines = [
        f"Need: {spc.get('need', '')}",
        f"Problem: {spc.get('problem_statement', '')}",
        f"Target user: {spc.get('target_user', '')}",
        f"Solution: {spc.get('solution_concept', '')}",
        f"Evidence: {spc.get('evidence', '')}",
    ]
    return "\n".join(lines)
