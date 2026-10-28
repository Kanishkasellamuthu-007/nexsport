"""
Central configuration loader.

All settings come from environment variables so that no credentials are
ever committed to source code. For local development they are read from
the .env file via python-dotenv.
"""
import os

from dotenv import load_dotenv

# Load .env from the project root if present (development convenience only).
load_dotenv()


class Config:
    """Base configuration shared by all environments."""

    # Supabase project settings. The anon (publishable) key is safe for the
    # frontend; the service-role key must ONLY be used server-side.
    SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.environ.get("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    # Legacy symmetric JWT secret (HS256 fallback). Optional; modern Supabase
    # projects use RS256 keys published at /auth/v1/.well-known/jwks.json.
    SUPABASE_JWT_SECRET: str = os.environ.get("SUPABASE_JWT_SECRET", "")

    # Comma-separated list of origins allowed to call the API.
    CORS_ORIGINS: list = [
        origin.strip()
        for origin in os.environ.get(
            "CORS_ORIGINS",
            "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000",
        ).split(",")
        if origin.strip()
    ]

    # Local Flask settings
    FLASK_PORT: int = int(os.environ.get("FLASK_PORT", "5000"))
    FLASK_DEBUG: bool = os.environ.get("FLASK_DEBUG", "0") == "1"

    # GitHub Models configuration (for open-source LLM chat)
    GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_MODELS_URL: str = os.environ.get(
        "GITHUB_MODELS_URL", "https://models.github.ai/inference/chat/completions"
    )


config = Config()
