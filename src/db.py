"""Data access helpers for the co-design platform."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import settings

try:
    from supabase import create_client
except ImportError:  # pragma: no cover - optional dependency guard
    create_client = None


STORE_FILE_PATH = Path(os.getenv("LOCAL_STORE_PATH") or Path(__file__).resolve().parents[1] / ".co_design_store.json")

LOCAL_STORE: Dict[str, Any] = {
    "accounts": [],
    "participants": [],
    "consent_records": [],
    "prompt_logs": [],
    "chat_histories": [],
    "spc_records": [],
    "rubric_scores": [],
    "survey_responses": [],
    "remembered_user": None,
}


def _save_local_store() -> None:
    try:
        STORE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STORE_FILE_PATH.write_text(json.dumps(LOCAL_STORE, indent=2), encoding="utf-8")
    except Exception:
        pass


def _load_local_store() -> None:
    if not STORE_FILE_PATH.exists():
        return
    try:
        contents = STORE_FILE_PATH.read_text(encoding="utf-8")
        data = json.loads(contents)
        if not isinstance(data, dict):
            return
        for key, default in LOCAL_STORE.items():
            if key in data:
                LOCAL_STORE[key] = data[key]
    except Exception:
        pass


def get_participant_by_user_id(user_id: str) -> Optional[Dict[str, Any]]:
    for participant in LOCAL_STORE.get("participants", []):
        if participant.get("user_id") == user_id:
            return participant
    return None


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
    _save_local_store()
    return payload


def _sanitize_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        k: v for k, v in user.items() if k not in ("password_hash", "password_salt")
    }


def _generate_salt() -> str:
    return secrets.token_hex(16)


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    )
    return base64.b64encode(digest).decode("utf-8")


def _verify_password(password: str, salt: str, expected_hash: str) -> bool:
    return secrets.compare_digest(_hash_password(password, salt), expected_hash)


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    normalized = (username or "").strip().lower()
    for account in LOCAL_STORE.get("accounts", []):
        if account.get("username") == normalized:
            return account
    return None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    for account in LOCAL_STORE.get("accounts", []):
        if account.get("user_id") == user_id:
            return account
    return None


def create_user(username: str, password: str) -> Dict[str, Any]:
    normalized = (username or "").strip().lower()
    if not normalized:
        raise ValueError("Username is required")
    if len(password or "") < 6:
        raise ValueError("Password must be at least 6 characters")
    if get_user_by_username(normalized):
        raise ValueError("Username is already taken")

    salt = _generate_salt()
    password_hash = _hash_password(password, salt)
    user_id = uuid.uuid4().hex
    participant_code = f"user-{user_id[:8]}"
    account = {
        "user_id": user_id,
        "username": normalized,
        "display_name": (username or "").strip(),
        "password_hash": password_hash,
        "password_salt": salt,
        "participant_code": participant_code,
        "created_at": "now",
    }
    LOCAL_STORE.setdefault("accounts", []).append(account)
    LOCAL_STORE["remembered_user"] = normalized
    _save_local_store()
    return _sanitize_user(account)


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    account = get_user_by_username(username)
    if account and _verify_password(password, account["password_salt"], account["password_hash"]):
        LOCAL_STORE["remembered_user"] = account["username"]
        _save_local_store()
        return _sanitize_user(account)
    return None


def get_remembered_user() -> Optional[Dict[str, Any]]:
    username = LOCAL_STORE.get("remembered_user")
    if username:
        account = get_user_by_username(username)
        if account:
            return _sanitize_user(account)
    return None


def logout_user() -> None:
    LOCAL_STORE["remembered_user"] = None
    _save_local_store()


def create_participant(participant_code: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a new anonymised participant record."""
    if user_id and not participant_code:
        participant_code = f"user-{user_id[:8]}"
    code = participant_code or f"anon-{uuid.uuid4().hex[:8]}"
    existing = get_participant_by_user_id(user_id) if user_id else None
    if existing:
        return existing
    payload = {"participant_code": code, "created_at": "now"}
    if user_id:
        payload["user_id"] = user_id
    return _persist("participants", payload)


# Load persisted local state on import so remembered login works between app sessions.
_load_local_store()


def create_consent_record(user_id: str, username: str, consented: bool, notes: Optional[str] = None) -> Dict[str, Any]:
    """Save a consent record without personal data."""
    payload = {
        "user_id": user_id,
        "username": username,
        "consented": consented,
        "notes": _sanitize_text(notes),
    }
    return _persist("consent_records", payload)


def log_prompt_response(user_id: str, username: str, prompt: str, response: str) -> Dict[str, Any]:
    """Log an anonymised prompt-response exchange."""
    payload = {
        "user_id": user_id,
        "username": username,
        "prompt_text": _sanitize_text(prompt),
        "response_text": _sanitize_text(response),
    }
    return _persist("prompt_logs", payload)


def save_chat_history(user_id: str, chat_history: List[Dict[str, str]]) -> Dict[str, Any]:
    """Save or replace the user's complete chat history."""
    existing = next(
        (item for item in LOCAL_STORE.setdefault("chat_histories", []) if item.get("user_id") == user_id),
        None,
    )
    if existing:
        existing["chat_history"] = chat_history
        payload = existing
    else:
        payload = {"user_id": user_id, "chat_history": chat_history}
        LOCAL_STORE["chat_histories"].append(payload)
    _save_local_store()
    return payload


def get_chat_history(user_id: str) -> List[Dict[str, str]]:
    item = next(
        (entry for entry in LOCAL_STORE.get("chat_histories", []) if entry.get("user_id") == user_id),
        None,
    )
    return item.get("chat_history", []) if item else []


def append_chat_message(user_id: str, role: str, message: str) -> None:
    history = get_chat_history(user_id)
    history.append({"role": role, "message": message})
    save_chat_history(user_id, history)


def save_spc(user_id: str, username: str, spc: Dict[str, Any]) -> Dict[str, Any]:
    """Save a generated structured product concept."""
    payload = {
        "user_id": user_id,
        "username": username,
        "need_summary": _sanitize_text(spc.get("need")),
        "spc_json": spc,
    }
    return _persist("spc_records", payload)


def save_spc_output(
    user_id: str,
    username: str,
    participant_code: str,
    *args,
    problem_statement: str | None = None,
    target_users: str | None = None,
    user_need: str | None = None,
    proposed_concept: str | None = None,
    functional_requirements: list[dict] | list[str] | None = None,
    constraints: str | None = None,
    expected_benefits: str | None = None,
    risks_assumptions: str | None = None,
    recommended_next_step: str | None = None,
    **kwargs,
) -> Dict[str, Any]:
    """Save SPC outputs using the current 9-field schema while keeping legacy aliases for older callers."""
    if args:
        if len(args) == 9 and problem_statement is None:
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
            ) = args
        elif len(args) >= 12 and problem_statement is None:
            legacy_overview, _, legacy_target_users, _, legacy_functional_requirements, _, legacy_nonfunctional_requirements, _, legacy_assumptions_constraints, _, legacy_expected_benefits, _ = args[:12]
            problem_statement = legacy_overview
            target_users = legacy_target_users
            proposed_concept = legacy_functional_requirements[0].get("text", str(legacy_functional_requirements[0])) if isinstance(legacy_functional_requirements, list) and legacy_functional_requirements else ""
            functional_requirements = legacy_functional_requirements
            constraints = legacy_assumptions_constraints
            expected_benefits = legacy_expected_benefits
            user_need = ""
            risks_assumptions = ""
            recommended_next_step = ""

    if functional_requirements is None:
        functional_requirements = []

    payload = {
        "user_id": user_id,
        "username": username,
        "participant_code": participant_code,
        "problem_statement": _sanitize_text(problem_statement),
        "target_users": _sanitize_text(target_users),
        "user_need": _sanitize_text(user_need),
        "proposed_concept": _sanitize_text(proposed_concept),
        "functional_requirements": functional_requirements,
        "constraints": _sanitize_text(constraints),
        "expected_benefits": _sanitize_text(expected_benefits),
        "risks_assumptions": _sanitize_text(risks_assumptions),
        "recommended_next_step": _sanitize_text(recommended_next_step),
        "overview": _sanitize_text(problem_statement),
        "target_user": _sanitize_text(target_users),
        "solution_concept": _sanitize_text(proposed_concept),
        "evidence": _sanitize_text(expected_benefits),
    }
    return _persist("spc_outputs", payload)


def get_last_spc(user_id: str) -> Optional[Dict[str, Any]]:
    matching = [record for record in LOCAL_STORE.get("spc_records", []) if record.get("user_id") == user_id]
    if not matching:
        return None
    return matching[-1]


def save_rubric_scores(user_id: str, username: str, scores: Dict[str, Any], notes: Optional[str] = None) -> Dict[str, Any]:
    """Save rubric evaluation scores."""
    payload = {
        "user_id": user_id,
        "username": username,
        "scores": scores,
        "notes": _sanitize_text(notes),
    }
    return _persist("rubric_scores", payload)


def save_survey_responses(user_id: str, username: str, responses: Dict[str, Any]) -> Dict[str, Any]:
    """Save survey responses."""
    payload = {
        "user_id": user_id,
        "username": username,
        "responses": responses,
    }
    return _persist("survey_responses", payload)


def clear_storage() -> None:
    """Clear the in-memory fallback store for tests."""
    for table in LOCAL_STORE:
        if isinstance(LOCAL_STORE[table], list):
            LOCAL_STORE[table] = []
        else:
            LOCAL_STORE[table] = None
    _save_local_store()
