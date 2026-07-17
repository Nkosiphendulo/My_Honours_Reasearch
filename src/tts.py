"""Text-to-speech helpers using Groq API."""

from __future__ import annotations

import io
import logging
from typing import Literal

from .config import settings

try:
    from groq import Groq
except ImportError:
    Groq = None

logger = logging.getLogger(__name__)


def generate_speech(
    text: str,
    voice: str = "diana",
    model: str | None = None,
) -> tuple[bytes | None, str | None]:
    """Generate speech audio from text using Groq TTS.

    Args:
        text: The text to convert to speech.
        voice: The voice to use. Valid voices: autumn, diana, hannah, austin, daniel, troy.
               Defaults to 'diana'.
        model: Optional model override; defaults to Groq TTS model.
               Use 'canopylabs/orpheus-v1-english' for Groq TTS (requires terms acceptance).

    Returns:
        Tuple of (audio_bytes, error_message). Either audio_bytes or error_message will be None.
    """
    if Groq is None:
        return None, "Groq SDK not installed. Install with: pip install groq"

    if not settings.GROQ_API_KEY:
        return None, "GROQ_API_KEY not set in environment variables."

    text = (text or "").strip()
    if not text:
        return None, "Text input is empty."

    try:
        client = Groq(api_key=settings.GROQ_API_KEY)

        # Use Groq's TTS endpoint via the openai-compatible interface
        # Note: The model must have its terms accepted on console.groq.com
        response = client.audio.speech.create(
            model=model or "canopylabs/orpheus-v1-english",
            voice=voice,
            input=text,
            response_format="wav",  # Groq TTS returns WAV format
        )

        # Groq returns audio bytes directly
        if hasattr(response, "content"):
            return response.content, None
        if isinstance(response, bytes):
            return response, None

        # Try to read as a file-like object
        if hasattr(response, "read"):
            return response.read(), None

        return None, f"Unexpected response type from Groq TTS: {type(response)}"
    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"TTS generation failed: {exc}")
        
        if "model_terms_required" in error_msg or "terms acceptance" in error_msg:
            return None, "TTS model terms not accepted. Visit https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english to accept terms."
        elif "401" in error_msg or "Unauthorized" in error_msg or "invalid api key" in error_msg.lower():
            return None, "Invalid Groq API key. Check your GROQ_API_KEY in .env"
        elif "429" in error_msg or "rate limit" in error_msg.lower():
            return None, "Rate limit exceeded. Please try again later."
        else:
            return None, f"TTS generation failed: {error_msg}"
