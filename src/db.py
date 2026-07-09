"""Data access helpers for the co-design platform."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional

from .config import settings

try:
    from supabase import create_client
except ImportError:  # pragma: no cover - optional dependency guard
    create_client = None


LOCAL_STORE: Dict[str, List[Dict[str, Any]]] = {
    "participants": [],
    "consent_records": [],
    "prompt_logs": [],
    "spc_records": [],
    "rubric_scores": [],
    "survey_responses": [],
}


def _sanitize_text(value: Optional[str]) -> Optional[str]:
    """Remove obvious PII patterns from free-text before persistence."""
    if value is None:
        return None
    text = value.strip()
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]", text)
    text = re.sub(r"\b(?:\+?\d[\d\s-]{7,}\d)\b", "[REDACTED_PHONE]", text)
    return text


def _get_client():
    """Return a Supabase client when credentials are available."""
    if create_client is None or not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        return None
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def _persist(table: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a payload to Supabase when available, else use the local fallback store."""
    client = _get_client()
    if client is not None:
        try:
            response = client.from_(table).insert(payload).execute()
            if response.data:
                return response.data[0]
        except Exception:
            pass

    LOCAL_STORE.setdefault(table, []).append(payload)
    return payload


def create_participant(participant_code: Optional[str] = None) -> Dict[str, Any]:
    """Create a new anonymised participant record."""
    code = participant_code or f"anon-{uuid.uuid4().hex[:8]}"
    payload = {"participant_code": code, "created_at": "now"}
    return _persist("participants", payload)


def create_consent_record(participant_code: str, consented: bool, notes: Optional[str] = None) -> Dict[str, Any]:
    """Save a consent record without personal data."""
    payload = {
        "participant_code": participant_code,
        "consented": consented,
        "notes": _sanitize_text(notes),
    }
    return _persist("consent_records", payload)


def log_prompt_response(participant_code: str, prompt: str, response: str) -> Dict[str, Any]:
    """Log an anonymised prompt-response exchange."""
    payload = {
        "participant_code": participant_code,
        "prompt_text": _sanitize_text(prompt),
        "response_text": _sanitize_text(response),
    }
    return _persist("prompt_logs", payload)


def save_spc(participant_code: str, spc: Dict[str, Any]) -> Dict[str, Any]:
    """Save a generated structured product concept."""
    payload = {
        "participant_code": participant_code,
        "need_summary": _sanitize_text(spc.get("need")),
        "spc_json": spc,
    }
    return _persist("spc_records", payload)


def save_rubric_scores(participant_code: str, scores: Dict[str, Any], notes: Optional[str] = None) -> Dict[str, Any]:
    """Save rubric evaluation scores."""
    payload = {
        "participant_code": participant_code,
        "scores": scores,
        "notes": _sanitize_text(notes),
    }
    return _persist("rubric_scores", payload)


def save_survey_responses(participant_code: str, responses: Dict[str, Any]) -> Dict[str, Any]:
    """Save survey responses."""
    payload = {
        "participant_code": participant_code,
        "responses": responses,
    }
    return _persist("survey_responses", payload)


def clear_storage() -> None:
    """Clear the in-memory fallback store for tests."""
    for table in LOCAL_STORE:
        LOCAL_STORE[table] = []
