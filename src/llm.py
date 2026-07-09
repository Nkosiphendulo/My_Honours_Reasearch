"""LLM helpers for generating structured product concepts."""

from __future__ import annotations

import json
import re
from typing import Any, Dict

from .config import settings

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - optional dependency guard
    Anthropic = None


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
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                payload = json.loads(match.group(0))
                payload.setdefault("components", [
                    payload.get("problem_statement", ""),
                    payload.get("target_user", ""),
                    payload.get("solution_concept", ""),
                    payload.get("evidence", ""),
                ])
                return payload
        except Exception:
            pass

    return {
        "need": need,
        "problem_statement": f"Students need a better way to address the issue described as: {need}.",
        "target_user": "Students and staff who experience the campus friction",
        "solution_concept": "A lightweight, low-cost intervention that makes the needed support easier to access.",
        "evidence": "The need is grounded in repeated observations from the co-design workshop and local feedback.",
        "components": [
            "Problem statement",
            "Target user",
            "Solution concept",
            "Evidence",
        ],
    }


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
