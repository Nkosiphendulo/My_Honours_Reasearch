"""LLM helpers for generating structured product concepts."""

from __future__ import annotations

import json
import re
from typing import Any, Dict

from .config import settings
from .db import LOCAL_STORE

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - optional dependency guard
    Anthropic = None
try:
    import openai
except ImportError:
    openai = None
try:
    import groq
except ImportError:
    groq = None


def _extract_message_content(response: Any) -> str:
    """Extract text content from Anthropic/OpenAI/Groq-style responses."""
    if not response:
        return ""

    # Groq/OpenAI-style object with .choices[0].message.content
    if hasattr(response, "choices"):
        first_choice = response.choices[0] if getattr(response, "choices", None) else None
        if first_choice is None:
            return ""
        message = getattr(first_choice, "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                pieces = []
                for item in content:
                    if isinstance(item, str):
                        pieces.append(item)
                    elif isinstance(item, dict):
                        text = item.get("text") or item.get("content") or ""
                        if isinstance(text, str):
                            pieces.append(text)
                    else:
                        text = getattr(item, "text", None)
                        if isinstance(text, str):
                            pieces.append(text)
                return "".join(pieces)
            if isinstance(content, dict):
                return content.get("text") or content.get("content") or ""
            return str(content or "")
        return getattr(first_choice, "text", "") or ""

    # Anthropic-style response with .content[0].text
    if hasattr(response, "content"):
        content = getattr(response, "content", None)
        if isinstance(content, list):
            texts = []
            for item in content:
                if hasattr(item, "text"):
                    texts.append(getattr(item, "text", ""))
                elif isinstance(item, str):
                    texts.append(item)
            return "".join(texts)
        return str(content or "")

    return str(response or "")


def _parse_json_payload(text: str) -> Dict[str, Any] | None:
    """Extract and parse the first JSON object from a model response."""
    if not text:
        return None

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE)

    start = cleaned.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(cleaned)):
        char = cleaned[idx]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start:idx + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
    return None


def build_spc(need: str, model: str | None = None) -> Dict[str, Any]:
    """Create a structured product concept from a campus need."""
    need = (need or "").strip()
    if not need:
        raise ValueError("A campus need is required")

    if settings.ANTHROPIC_API_KEY and Anthropic is not None:
        try:
            client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            prompt = (
                "Convert this campus need into a structured product concept. "
                "Return JSON with keys: need, problem_statement, target_user, "
                "solution_concept, evidence, components."
                f"\nNeed: {need}"
            )
            response = client.messages.create(
                model=model or settings.ANTHROPIC_MODEL,
                max_tokens=400,
                temperature=0.2,
                system="You are a helpful design assistant for student co-design workshops.",
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text if getattr(response, "content", None) else ""
            payload = _parse_json_payload(content)
            if payload is not None:
                payload.setdefault("components", [
                    payload.get("problem_statement", ""),
                    payload.get("target_user", ""),
                    payload.get("solution_concept", ""),
                    payload.get("evidence", ""),
                ])
                return payload
        except Exception as exc:
            raise RuntimeError(
                f"Anthropic SPC generation failed: {exc}. "
                "Please check your Anthropic API key, model selection, and billing/credits."
            ) from exc

    # Fallback to Groq if configured
    if groq is not None and settings.GROQ_API_KEY and not settings.ANTHROPIC_API_KEY:
        try:
            client = groq.Groq(api_key=settings.GROQ_API_KEY)
            prompt = (
                "Convert this campus need into a structured product concept. "
                "Return a single valid JSON object with keys: need, problem_statement, target_user, "
                "solution_concept, evidence, components. Do not wrap it in markdown or add any extra text."
                f"\nNeed: {need}"
            )
            messages = [{"role": "user", "content": prompt}]
            resp = client.chat.completions.create(
                model=model or settings.GROQ_MODEL,
                messages=messages,
                max_tokens=400,
                temperature=0.2,
            )
            content = _extract_message_content(resp)
            payload = _parse_json_payload(content)
            if payload is not None:
                payload.setdefault("components", [
                    payload.get("problem_statement", ""),
                    payload.get("target_user", ""),
                    payload.get("solution_concept", ""),
                    payload.get("evidence", ""),
                ])
                return payload
            return {
                "need": need,
                "problem_statement": content.strip() or "Campus need captured for further refinement.",
                "target_user": "",
                "solution_concept": "",
                "evidence": "",
                "components": [content.strip() or "Campus need captured for further refinement."],
            }
        except Exception as exc:
            raise RuntimeError(
                f"AI generation failed while building SPC: {exc}. "
                "Ensure GROQ_API_KEY or ANTHROPIC_API_KEY is configured and valid."
            ) from exc

    raise RuntimeError(
        "No AI provider configured for SPC generation. "
        "Set GROQ_API_KEY or ANTHROPIC_API_KEY in your environment."
    )


def chat_spc(messages: list[dict[str, str]], spc: Dict[str, Any] | None = None, model: str | None = None) -> str:
    """Return chatbot guidance for SPC generation and refinement.

    This function augments the assistant's system prompt with recent survey and
    evaluation (rubric) data when available in the local fallback store so the
    assistant can ground suggestions in empirical feedback.
    """
    # Gather local context if available
    survey_entries = LOCAL_STORE.get("survey_responses", []) or []
    rubric_entries = LOCAL_STORE.get("rubric_scores", []) or []

    # Compute a simple average evaluation score if numeric rubric values are present
    eval_avg = None
    eval_count = 0
    total = 0.0
    for e in rubric_entries:
        scores = e.get("scores") or {}
        numeric_vals = [v for v in scores.values() if isinstance(v, (int, float))]
        if numeric_vals:
            eval_count += 1
            total += sum(numeric_vals) / len(numeric_vals)
    if eval_count:
        eval_avg = total / eval_count

    # Prepare Anthropic/system prompt if available
    if Anthropic is not None and settings.ANTHROPIC_API_KEY:
        try:
            client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            system = (
                "You are a helpful design assistant for student co-design workshops. "
                "Help the user generate and refine a Structured Product Concept (SPC) from a campus need. "
                "Ask clarifying questions when needed and keep the conversation focused on need, problem, target user, solution, and evidence."
            )

            # Add lightweight survey/eval context to the system prompt
            if survey_entries:
                recent = [s.get("responses") for s in survey_entries[-3:]]
                system += f" Recent survey snippets: {recent}."
            if eval_avg is not None:
                system += f" Recent average evaluation score: {round(eval_avg,2)}."

            formatted_messages = [
                {"role": message["role"], "content": message["message"]}
                for message in messages
            ]
            if spc is not None:
                formatted_messages.insert(0, {
                    "role": "system",
                    "content": f"Current SPC context: {format_spc_for_display(spc)}",
                })
            response = client.messages.create(
                model=model or settings.ANTHROPIC_MODEL,
                max_tokens=400,
                temperature=0.3,
                system=system,
                messages=formatted_messages,
            )
            return response.content[0].text if getattr(response, "content", None) else ""
        except Exception as exc:
            return f"AI chat failed with Anthropic: {exc}"

    # Groq chat fallback only when Anthropic is not configured
    if groq is not None and settings.GROQ_API_KEY and not settings.ANTHROPIC_API_KEY:
        try:
            client = groq.Groq(api_key=settings.GROQ_API_KEY)
            system = (
                "You are a helpful design assistant for student co-design workshops. "
                "Help the user generate and refine a Structured Product Concept (SPC) from a campus need. "
                "Ask clarifying questions when needed and keep the conversation focused on need, problem, target user, solution, and evidence."
            )
            if survey_entries:
                recent = [s.get("responses") for s in survey_entries[-3:]]
                system += f" Recent survey snippets: {recent}."
            if eval_avg is not None:
                system += f" Recent average evaluation score: {round(eval_avg,2)}."

            formatted_messages = [
                {"role": message["role"], "content": message["message"]}
                for message in messages
            ]
            if spc is not None:
                formatted_messages.insert(0, {
                    "role": "system",
                    "content": f"Current SPC context: {format_spc_for_display(spc)}",
                })
            resp = client.chat.completions.create(
                model=model or settings.GROQ_MODEL,
                messages=formatted_messages,
                max_tokens=400,
                temperature=0.3,
            )
            content = _extract_message_content(resp)
            return content
        except Exception as exc:
            return f"AI chat failed with Groq: {exc}"


    # Fallback behaviour when no Anthropic client is configured
    latest = messages[-1]["message"] if messages else ""
    if not latest.strip():
        return "Tell me about the campus need and I will help you generate the SPC."

    if spc is None:
        # If there are survey or evaluation signals, hint at them in the assistant reply
        ctx = []
        if survey_entries:
            ctx.append(f"{len(survey_entries)} survey responses available")
        if eval_avg is not None:
            ctx.append(f"avg eval score {round(eval_avg,2)}")
        ctx_text = (" Using recent survey/eval context: " + ", ".join(ctx)) if ctx else ""
        return (
            "I can help you turn the campus need into an SPC. "
            "Please describe the need clearly and I will suggest a problem statement, target user, solution concept, and evidence." + ctx_text
        )

    # When an SPC exists, include it and any survey/eval summary to ground refinement suggestions
    survey_note = f"Recent survey responses: {len(survey_entries)}" if survey_entries else "No recent survey data"
    eval_note = f"Average eval score: {round(eval_avg,2)}" if eval_avg is not None else "No evaluation scores"
    return (
        "Here is the current SPC:\n"
        + format_spc_for_display(spc)
        + "\n\n" + survey_note + "; " + eval_note +
        "\n\nIf you want to refine the SPC, ask me to improve one section or share more details about the target user or evidence."
    )


def format_spc_for_display(spc: Dict[str, Any]) -> str:
    """Render a structured concept as a readable display string."""
    lines = [
        f"Need: {spc.get('need', '')}",
        f"Problem: {spc.get('problem_statement', '')}",
        f"Target user: {spc.get('target_user', '')}",
        f"Solution: {spc.get('solution_concept', '')}",
        f"Evidence: {spc.get('evidence', '')}",
    ]
    return "\n".join(lines)
