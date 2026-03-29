"""Centralized configuration helpers.

This module loads environment variables (via dotenv) and provides
normalized getters for commonly used configuration values.
"""

import os
from dotenv import load_dotenv
from typing import List, Optional


# Load .env early so callers can rely on os.environ
load_dotenv()


def _clean_env_value(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip()
    if len(v) >= 2 and (
        (v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")
    ):
        v = v[1:-1]
    return v.strip()


def get_database_url() -> Optional[str]:
    use_deploy = get_env_bool("USE_DEPLOY_DB", default=False)
    if use_deploy:
        deploy_url = _clean_env_value(os.getenv("DATABASE_URL_DEPLOY"))
        if deploy_url:
            return deploy_url
    return _clean_env_value(os.getenv("DATABASE_URL"))


def get_gemini_keys(prefix: str = "GEMINI_API_KEY_", max_keys: int | None = 40) -> List[str]:
    items: List[tuple[int, str]] = []
    prefix_len = len(prefix)
    for env_key, value in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        suffix = env_key[prefix_len:]
        order = None
        if suffix.isdigit():
            order = int(suffix)
        else:
            try:
                order = int("".join(ch for ch in suffix if ch.isdigit()))
            except Exception:
                order = None
        if order is None:
            order = 10_000
        cleaned = _clean_env_value(value)
        if cleaned:
            items.append((order, cleaned))
    items.sort(key=lambda kv: kv[0])
    keys = [value for _, value in items]
    if max_keys is not None:
        return keys[: int(max_keys)]
    return keys


def get_env_str(name: str, default: Optional[str] = None) -> Optional[str]:
    return _clean_env_value(os.getenv(name, default))


def get_env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip().lower().strip('"').strip("'")
    return v in ("1", "true", "yes", "on")


def get_env_int(name: str, default: int | None = None) -> int | None:
    v = _clean_env_value(os.getenv(name))
    if v is None:
        return default
    try:
        return int(v)
    except Exception:
        return default


def get_env_float(name: str, default: float | None = None) -> float | None:
    v = _clean_env_value(os.getenv(name))
    if v is None:
        return default
    try:
        return float(v)
    except Exception:
        return default

