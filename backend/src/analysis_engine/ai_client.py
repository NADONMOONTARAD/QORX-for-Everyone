from __future__ import annotations

import json
import random
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from backend.src.config import get_gemini_keys
from backend.src.utils.throttling import RateLimitedKeyPool

# --- CONFIGURATION FOR GEMINI-3-FLASH ---
# User mandated: RPM=5, TPM=250k.
# SINGLE_CALL_TOKEN_THRESHOLD should safely fit within TPM.
# 250k TPM is the rate limit.
SINGLE_CALL_TOKEN_THRESHOLD = 245000
RESERVED_OUTPUT_TOKENS = 5000
_GEMINI_ENDPOINT_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# Only fetch GEMINI_API_KEY_# keys.
# We ignore PRO keys as requested to "leave only this one".
_BASE_KEYS = get_gemini_keys(prefix="GEMINI_API_KEY_", max_keys=50)

_BASE_POOL: RateLimitedKeyPool | None = None

if _BASE_KEYS:
    # RPM=5 => 60 seconds / 5 requests = 12 seconds per request minimum interval.
    _BASE_POOL = RateLimitedKeyPool(
        _BASE_KEYS,
        min_interval_seconds=12.0,
        jitter_seconds=0.75,
        name="gemini-shared",
    )

MODEL_PROFILES: dict[str, dict[str, object]] = {}

# Register a default profile (can be used by any model name)
if _BASE_POOL:
    MODEL_PROFILES["default"] = {
        "pool": _BASE_POOL,
        "extra_cooldown": 0.0,
    }


def resolve_model_name(model: Optional[str]) -> str:
    # Strictly trust the input. 1 in -> 1 out.
    # Default to the user's preferred new model only if nothing is passed.
    if not model:
        return "gemini-3-flash-preview"
    return model


def _resolve_alias(model: Optional[str]) -> str:
    # We just return "default" because we only have one pool now.
    # The actual model name is handled by resolve_model_name during the API call.
    return "auldeft"


def select_available_model_alias(preferred: Optional[str]) -> Optional[str]:
    # We only have one pool, so we always return "default" if keys exist.
    if _BASE_POOL:
        return "default"
    return None


def _build_endpoint(model_name_resolved: str) -> str:
    return _GEMINI_ENDPOINT_TEMPLATE.format(model=model_name_resolved)


def _parse_retry_after(header_value: Optional[str]) -> Optional[int]:
    if not header_value:
        return None
    try:
        return int(header_value)
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(header_value)
            return max(0, int((dt - datetime.now(timezone.utc)).total_seconds()))
        except Exception:
            return None


def _apply_extra_cooldown(pool: RateLimitedKeyPool, api_key: str, alias: str) -> None:
    # No extra cooldown logic needed for this single-pool setup currently,
    # but keeping the stub if we need to add specifically later.
    pass


def gemini_summarize(
    prompt: str, return_json: bool, model: str = "gemini-3-flash-preview"
):
    # Ensure we have keys
    if not _BASE_POOL:
        print(
            "Gemini API keys are not configured (expected GEMINI_API_KEY_#). Skipping Gemini calls."
        )
        return None

    # Resolve the actual model name to send to Google
    final_model_name = resolve_model_name(model)

    endpoint = _build_endpoint(final_model_name)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1},
    }

    max_retries = 4
    MAX_BACKOFF_SECONDS = 300
    text_out = ""

    # Acquire key from the single shared pool
    pool = _BASE_POOL

    for attempt in range(max_retries):
        api_key = pool.acquire()
        if not api_key:
            print("No Gemini API key available (pool exhausted).")
            return None
        headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=300)

            if resp.status_code == 403:
                print(
                    f"Gemini API returned 403 Forbidden for model {final_model_name}."
                    " Check API key permissions/billing."
                )
                pool.defer(api_key, MAX_BACKOFF_SECONDS)
                return None

            if resp.status_code in (429, 503):
                retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                if retry_after is None:
                    # RDP=20 implication? Maybe just rely on RPM.
                    # With RPM=5, we wait 12s. If we still get 429, backoff aggressively.
                    retry_after = (2**attempt) + random.uniform(0.5, 1.5)
                wait_time = min(MAX_BACKOFF_SECONDS, retry_after)
                pool.defer(api_key, wait_time)
                print(
                    f"Gemini rate limited (status {resp.status_code}). Waiting {wait_time:.2f}s before retry..."
                )
                time.sleep(wait_time)
                continue

            resp.raise_for_status()
            data = resp.json()
            try:
                text_out = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
            except IndexError:
                text_out = ""

            if not text_out:
                print("Warning: Gemini returned an empty text response. Retrying...")
                pool.defer(api_key, 3.0)
                time.sleep(1.0)
                continue

            if return_json:
                parsed = json.loads(
                    text_out.replace("```json", "").replace("```", "").strip()
                )
                return parsed

            return text_out

        except requests.exceptions.RequestException as e:
            print(
                f"Gemini API request failed (Attempt {attempt + 1}/{max_retries}) for model {final_model_name}: {e}"
            )
            wait_time = min(
                MAX_BACKOFF_SECONDS, (2**attempt) + random.uniform(0.5, 1.5)
            )
            pool.defer(api_key, wait_time)
            time.sleep(wait_time)
        except json.JSONDecodeError:
            print(
                f"Fatal Error: Could not parse Gemini JSON. Response text (truncated): {text_out[:500]}..."
            )
            return {} if return_json else ""
        finally:
            pool.release(api_key)
    return None
