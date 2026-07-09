"""Configuration helpers for environment-based settings."""

import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
    USE_LOCAL_FALLBACK = os.getenv("USE_LOCAL_FALLBACK", "true").lower() == "true"


settings = Settings()
