"""RAG-owned Supabase client configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class SupabaseConfigurationError(RuntimeError):
    """Raised when required Supabase connection settings are unavailable."""


@dataclass(frozen=True, slots=True)
class SupabaseSettings:
    url: str
    key: str


def load_supabase_settings(
    environ: Mapping[str, str] | None = None,
) -> SupabaseSettings:
    """Load required settings without exposing their values in errors."""

    if environ is None:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=ENV_FILE, override=False)
        environ = os.environ

    values = {
        "SUPABASE_URL": environ.get("SUPABASE_URL", "").strip(),
        "SUPABASE_KEY": environ.get("SUPABASE_KEY", "").strip(),
    }
    missing = tuple(name for name, value in values.items() if not value)
    if missing:
        raise SupabaseConfigurationError(
            f"Missing required environment variable(s): {', '.join(missing)}"
        )
    return SupabaseSettings(values["SUPABASE_URL"], values["SUPABASE_KEY"])


def create_supabase_client(settings: SupabaseSettings | None = None):
    """Create the SDK client after configuration has been validated."""

    resolved = settings or load_supabase_settings()
    from supabase import create_client

    return create_client(resolved.url, resolved.key)
