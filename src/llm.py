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
                "max_tokens": 8000,
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
    """Parse the four-field SPC block returned by the API."""
    match = re.search(
        r"\[SPC_START\]\s*"
        r"Problem statement:\s*(.*?)\s*"
        r"Target users:\s*(.*?)\s*"
        r"Solution concept:\s*(.*?)\s*"
        r"Evidence/rationale:\s*(.*?)\s*"
        r"\[SPC_END\]",
        reply,
        flags=re.S,
    )
    if not match:
        return {}

    problem, target_users, solution, evidence = (part.strip() for part in match.groups())
    return {
        "overview": problem,
        "target_users": target_users,
        "functional_requirements": [{"id": "SC-1", "text": solution}],
        "nonfunctional_requirements": [],
        "assumptions_constraints": "",
        "expected_benefits": evidence,
    }


def format_spc_for_display(spc: Dict[str, Any]) -> str:
    """Render either legacy or new SPC structure as a readable display string.

    Supports old keys (`need`, `problem_statement`, `target_user`, `solution_concept`, `evidence`)
    and the four-field SPC block returned by the API.
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
