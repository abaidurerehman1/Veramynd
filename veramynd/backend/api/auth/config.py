"""Auth settings loaded from environment / .env."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_PATH)


@lru_cache
def settings() -> dict[str, str | int | bool]:
    return {
        "database_url": os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:Abaid_1001@127.0.0.1:5433/veramynd",
        ),
        "jwt_secret": os.getenv("JWT_SECRET", "veramynd-dev-jwt-secret"),
        "jwt_expire_hours": int(os.getenv("JWT_EXPIRE_HOURS", "168")),
        "app_base_url": os.getenv("APP_BASE_URL", "http://localhost:5173").rstrip("/"),
        "api_base_url": os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
        "smtp_host": os.getenv("SMTP_HOST", ""),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "smtp_user": os.getenv("SMTP_USER", ""),
        "smtp_password": os.getenv("SMTP_PASSWORD", ""),
        "smtp_from": os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "noreply@veramynd.local")),
        "smtp_use_tls": os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"},
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        "google_client_secret": os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        "google_redirect_uri": os.getenv(
            "GOOGLE_REDIRECT_URI",
            "http://127.0.0.1:8000/api/auth/oauth/google/callback",
        ),
    }
