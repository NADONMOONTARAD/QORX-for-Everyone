"""Public-edition qualitative analysis.

This repo intentionally uses standard educational heuristics and broad prompts
that are easy to audit in public. The fuller thesis logic is maintained
separately and can be reviewed on request.
"""

# backend/src/analysis_engine/qualitative.py
# Removed gzip caching: always fetch and clean the SEC filing text
import os, json, re, time, requests, psycopg2, random, tiktoken, email.utils, copy
from psycopg2.extras import Json
from urllib.parse import urlparse
from dotenv import load_dotenv
from datetime import datetime, timezone

# Reuse centralized ai_client for Gemini calls and key rotation
from backend.src.analysis_engine.ai_client import (
    gemini_summarize,
    SINGLE_CALL_TOKEN_THRESHOLD,
    RESERVED_OUTPUT_TOKENS,
    select_available_model_alias,
    resolve_model_name,
)
from backend.src.config import get_env_str

# ========= Load .env & Config =========
load_dotenv()

SUMMARY_MODEL_PREFERENCE = (
    (get_env_str("GEMINI_SUMMARY_MODEL", "flash") or "flash").strip().lower()
)

GEMINI_COOLDOWN_SECONDS = 60.0
_last_gemini_completion_ts = 0.0


class QualitativeAnalysisError(Exception):
    """Custom exception for AI analysis failures."""

    pass


def _wait_for_gemini_cooldown():
    global _last_gemini_completion_ts
    if _last_gemini_completion_ts <= 0:
        return
    elapsed = time.monotonic() - _last_gemini_completion_ts
    if elapsed < GEMINI_COOLDOWN_SECONDS:
        wait_for = GEMINI_COOLDOWN_SECONDS - elapsed
        print(f"[qualitative] Waiting {wait_for:.1f}s before next Gemini request")
        time.sleep(wait_for)


def _update_gemini_cooldown():
    global _last_gemini_completion_ts
    _last_gemini_completion_ts = time.monotonic()


def _gemini_summarize_with_cooldown(prompt: str, *, return_json: bool, model: str):
    _wait_for_gemini_cooldown()
    response = gemini_summarize(prompt, return_json=return_json, model=model)
    _update_gemini_cooldown()
    return response


def parse_db_url(db_url: str):
    result = urlparse(db_url)
    return {
        "dbname": result.path[1:],
        "user": result.username,
        "password": result.password,
        "host": result.hostname,
        "port": result.port or 5432,
    }

from backend.src.config import get_database_url
DATABASE_URL = get_database_url()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not found in .env via config")
DB_CONFIG = parse_db_url(DATABASE_URL)

# ========= Prompts =========
EXTRACTIVE_SUMMARY_PROMPT = """
You are an expert financial analyst. Your task is to perform an extractive summary of the provided section from an SEC filing (e.g., 10-K, N-CSR).
Focus ONLY on the most critical information related to business strategy, competitive advantages, material risks, and financial performance trends.
Do not add any commentary. Return only the condensed, essential information from the text.

Section Text:
{text_content}
"""

FINAL_ANALYSIS_PROMPT = """
You are producing a public educational summary of an SEC filing for a GitHub
edition of this project.

Important rules:
- Keep the output broad, conservative, and easy to audit.
- Do not invent proprietary heuristics or unusually specific analyst language.
- If the filing is unclear, prefer simple labels and empty lists rather than speculation.
- Only use canonical business risk tags when the filing explicitly supports them.

Return your analysis ONLY as a single, valid JSON object in the following format:
{
    "business_model": {"value": "...", "confidence": 0.95},
    "risks": {"value": ["..."], "confidence": 0.9},
    "moats_identified": {
        "value": [{"type": "Switching Cost", "strength": "Moderate", "rationale": "Broad filing evidence only."}],
        "confidence": 0.88
    },
    "ham_sandwich_test": {"value": "Simple", "confidence": 0.8, "rationale": "Operational complexity appears limited."},
    "management_quality": {
        "intelligence": {"value": "Medium", "confidence": 0.8, "rationale": "Broad filing evidence only."},
        "energy": {"value": "Medium", "confidence": 0.7, "rationale": "Broad filing evidence only."},
        "rationality": {"value": "Medium", "confidence": 0.75, "rationale": "Broad filing evidence only."},
        "notes": {"value": "Use broad educational summaries only.", "confidence": 0.7}
    },
    "pricing_power": {"rating": "Medium", "evidence": "Broad filing evidence only.", "confidence": 0.75},
    "management_candor": {"value": "Moderate", "confidence": 0.8, "rationale": "Broad filing evidence only."},
    "institutional_imperative_assessment": {"rating": "Resists", "evidence": "...", "confidence": 0.7},
    "business_risk_tags": {"value": ["GEOPOLITICAL_RISK", "CUSTOMER_CONCENTRATION"], "confidence": 0.9},
    "governance_flags": {"value": [], "confidence": 0.85},
    "revenue_by_segment": {"value": [{"year": 2024, "segment": "...", "value": 12.3, "unit": "usd millions"}], "confidence": 0.95},
    "revenue_by_region": {"value": [{"year": 2024, "region": "...", "value": 9.8, "unit": "usd millions"}], "confidence": 0.95},
    "buyback_analysis": {"value": [
        {"year": 2024, "shares_repurchased": {"value": 310, "unit": "millions of shares"}, "total_cost_of_buybacks": {"value": 34.0, "unit": "billions"}, "avg_buyback_price": {"value": 109.7, "unit": "usd per share"}, "confidence": 0.9}
    ], "confidence": 0.9}
}

Field guidance:
- `business_model.value`: 2-4 sentence plain-language description of how the business makes money.
- `risks.value`: short list of explicitly discussed risks only.
- `moats_identified.value`: at most 3 broad moat items. Use empty list if unclear.
- `ham_sandwich_test.value`: choose from `Simple`, `Moderate`, `Complex`.
- `management_quality`: use only `High`, `Medium`, `Low`.
- `pricing_power.rating`: use only `High`, `Medium`, `Low`.
- `management_candor.value`: use only `High`, `Moderate`, `Low`.
- `institutional_imperative_assessment.rating`: use only `Resists`, `Neutral`, `Follows`.
- `business_risk_tags.value`: use only these canonical tags when explicit:
  [ZERO_SUM_BUSINESS, REGULATORY_UNPREDICTABLE, GEOPOLITICAL_RISK, SANCTION_RISK, CURRENCY_CONTROLS, CAPITAL_CONTROLS, CUSTOMER_CONCENTRATION, KEY_PERSON_RISK, DISRUPTION_RISK, BLACK_BOX_ACCOUNTING]
- `governance_flags.value`: use only these canonical tags when explicit:
  [POOR_MD&A, AGGRESSIVE_M&A, OPAQUE_DISCLOSURE, INSTITUTIONAL_IMPERATIVE, POOR_CAPITAL_ALLOCATION]
- `revenue_by_segment` and `revenue_by_region`: extract only reported values; otherwise return empty lists.
- `buyback_analysis`: extract only the latest clearly reported annual buyback entry; otherwise return empty list.

Filing text to analyze:
{text_content}
"""

FUND_ANALYSIS_PROMPT = """
You are producing a public educational summary for a fund or ETF profile.

Important rules:
- Keep the output broad and non-proprietary.
- Prefer plain-language summaries over nuanced analyst judgments.
- If uncertain, return empty lists or neutral labels.

Return your analysis ONLY as a single, valid JSON object following the same schema used by the main prompt. Use default empty lists for revenue and buybacks.

Fund Overview text to analyze:
{text_content}
"""

# ========= Core Helper Functions (Upgraded) =========


def fetch_sec_filing(url: str) -> str:
    headers = {
        "User-Agent": os.getenv("SEC_USER_AGENT", "My Project <my_email@example.com>")
    }
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.text


def clean_filing_text(raw_text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", raw_text)
    cleaned = re.sub(r"(\n\s*)+\n", "\n", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def get_token_count(text: str) -> int:
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text.split())


def _parse_retry_after(header_value: str) -> int | None:
    # kept for compatibility with the ai_client implementation and potential uses
    if not header_value:
        return None
    try:
        return int(header_value)
    except ValueError:
        try:
            dt = email.utils.parsedate_to_datetime(header_value)
            return max(0, int((dt - datetime.now(timezone.utc)).total_seconds()))
        except (TypeError, ValueError):
            return None


def _validate_final_json(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    required_keys = [
        "business_model",
        "risks",
        "moats_identified",
    ]

    # Basic presence checks for required keys
    if not all(key in data for key in required_keys):
        return False

    # Accept (but not require) revenue_by_segment and revenue_by_region.
    # If present they must be dicts with a 'value' list.
    for optional_key in ("revenue_by_segment", "revenue_by_region"):
        if optional_key in data:
            if not isinstance(data[optional_key], dict):
                return False
            if "value" not in data[optional_key]:
                return False
            if not isinstance(data[optional_key]["value"], list):
                return False

    return True


def _base_section(value):
    return {"value": value, "confidence": 0.0}


def _default_final_json_template() -> dict:
    return {
        "business_model": _base_section(""),
        "risks": _base_section([]),
        "moats_identified": _base_section([]),
        "long_term_prospects": _base_section(""),
        "ham_sandwich_test": _base_section(""),
        "pricing_power_evidence": _base_section(""),
        "management_candor": _base_section(""),
        "company_type": _base_section("Unknown"),
        "business_risk_tags": _base_section([]),
        "governance_flags": _base_section([]),
        "revenue_by_segment": _base_section([]),
        "revenue_by_region": _base_section([]),
    }


def _ensure_final_json(data: dict) -> dict:
    template = _default_final_json_template()
    if not isinstance(data, dict):
        return copy.deepcopy(template)

    result = copy.deepcopy(data)

    for key, default_val in template.items():
        if key not in result:
            result[key] = copy.deepcopy(default_val)
            continue

        current_val = result[key]

        if isinstance(default_val, dict) and "value" in default_val:
            if not isinstance(current_val, dict):
                result[key] = copy.deepcopy(default_val)
                continue
            expected_type = type(default_val["value"])
            if not isinstance(current_val.get("value"), expected_type):
                result[key]["value"] = copy.deepcopy(default_val["value"])
            if not isinstance(current_val.get("confidence"), (int, float)):
                result[key]["confidence"] = 0.0
            if "rationale" in default_val and not isinstance(
                current_val.get("rationale"), str
            ):
                result[key]["rationale"] = copy.deepcopy(default_val["rationale"])

    for revenue_key in ("revenue_by_segment", "revenue_by_region"):
        if revenue_key not in result:
            result[revenue_key] = copy.deepcopy(template[revenue_key])
            continue
        if not isinstance(result[revenue_key], dict):
            result[revenue_key] = copy.deepcopy(template[revenue_key])
            continue
        if not isinstance(result[revenue_key].get("value"), list):
            result[revenue_key]["value"] = []
        if not isinstance(result[revenue_key].get("confidence"), (int, float)):
            result[revenue_key]["confidence"] = 0.0

    return result


def chunk_by_sec_items(text: str) -> dict:
    """Robustly splits SEC text (10-K, N-CSR) by 'Item' sections using re.finditer."""
    pattern = re.compile(
        r"^\s*item\s+(1a?|1b?|2|3|4|5|6|7a?|7b?|8|9a?|9b?|10|11|12|13|14|15)\b[.:]?",
        re.IGNORECASE | re.MULTILINE,
    )

    sections = {}
    matches = list(pattern.finditer(text))

    if not matches:
        print("Warning: Semantic chunking failed. No 'Item' headers found.")
        return {"FULL_DOCUMENT": text}

    for i, match in enumerate(matches):
        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        section_key = f"ITEM {match.group(1).strip().upper()}"
        section_content = text[start_pos:end_pos].strip()

        if len(section_content) > 250:
            sections[section_key] = section_content

    # Final check: if the process found matches but no content was long enough, still treat it as a failure
    if not sections:
        print(
            "Warning: Semantic chunking found headers but no substantial content. Reverting."
        )
        return {"FULL_DOCUMENT": text}

    print(f"Document semantically split into {len(sections)} sections.")
    return sections


_CURRENCY_UNIT_DEFAULTS = {
    "usd": "usd millions",
    "$": "usd millions",
    "us dollar": "usd millions",
    "us dollars": "usd millions",
    "u.s. dollar": "usd millions",
    "u.s. dollars": "usd millions",
    "dollar": "usd millions",
    "dollars": "usd millions",
}


def _normalize_value_unit_label(unit: str | None) -> str:
    """Normalize unit strings so downstream scaling logic can infer magnitude.

    If the unit is a bare currency (e.g. "usd"), assume the filing uses millions,
    matching common SEC filing conventions.
    """
    raw = (unit or "").strip().lower()
    if not raw:
        return "units"
    mapped = _CURRENCY_UNIT_DEFAULTS.get(raw)
    if mapped:
        return mapped
    return raw


def _sanitize_revenue_fields(final_json: dict) -> dict:
    """Ensure revenue_by_segment and revenue_by_region are present and normalized.

    - Always create the structure if missing.
    - Guarantee each entry has 'segment' or 'region' field (explicitly insert).
    - Guarantee value is numeric and confidence is float.
    """
    if not isinstance(final_json, dict):
        return final_json

    for rev_key, name_key in ("revenue_by_segment", "segment"), (
        "revenue_by_region",
        "region",
    ):
        rv = final_json.get(rev_key)
        if rv is None or not isinstance(rv, dict):
            final_json[rev_key] = {"value": [], "confidence": 0.0}
            continue

        vals = rv.get("value")
        if not isinstance(vals, list):
            final_json[rev_key] = {"value": [], "confidence": 0.0}
            continue

        clean_list = []
        for entry in vals:
            if not isinstance(entry, dict):
                continue

            # normalize name
            name = (
                entry.get("segment")
                or entry.get("region")
                or entry.get("segment_original_name")
                or entry.get("name")
            ) or "unknown"

            # normalize value block
            val_block = entry.get("value") or entry.get("amount") or {}
            if not isinstance(val_block, dict):
                try:
                    numeric = float(val_block)
                    val_block = {"value": numeric, "unit": "units"}
                except Exception:
                    val_block = {"value": 0, "unit": "units"}

            vnum = val_block.get("value")
            try:
                vnum = float(vnum) if vnum is not None else 0.0
            except Exception:
                vnum = 0.0

            unit = _normalize_value_unit_label(val_block.get("unit"))

            # preserve optional year field when present; coerce to int when possible
            year = (
                entry.get("year")
                or entry.get("fiscal_year")
                or entry.get("year_reported")
            )
            try:
                year = int(year) if year is not None else None
            except Exception:
                year = None

            confidence = entry.get("confidence")
            try:
                confidence = float(confidence) if confidence is not None else 0.0
            except Exception:
                confidence = 0.0

            clean_entry = {
                name_key: name,  # <== ใส่ key "segment"/"region" ชัดเจน
                "value": {"value": vnum, "unit": unit},
                "confidence": confidence,
            }
            if year is not None:
                clean_entry["year"] = year
            clean_list.append(clean_entry)

        final_json[rev_key]["value"] = clean_list
        final_json[rev_key]["confidence"] = float(rv.get("confidence") or 0.0)

    return final_json


def _map_segment_group(name: str) -> str:
    """Normalize segment name to a snake_case format.
    """
    if not name:
        return "unknown"
    low = (name or "").strip().lower()
    # fallback: replace spaces with underscore and remove non-alnum
    s = re.sub(r"[^a-z0-9_]+", "_", low)
    s = re.sub(r"__+", "_", s).strip("_")
    return s or low


def _normalize_ai_revenue(final_json: dict) -> dict:
    """Normalize AI-provided revenue-by-segment data into the canonical structure.

    Transforms entries in `revenue_by_segment.value` into objects with
    keys expected downstream: segment, segment_original_name, segment_group,
    value, confidence, revenue_growth_pct, data_source.
    """
    if not isinstance(final_json, dict):
        return final_json

    # Accept multiple shapes for revenue_by_segment: dict with 'value', plain list, or other
    rv = final_json.get("revenue_by_segment")
    segs = []
    parent_confidence = 0.0
    if isinstance(rv, dict):
        segs = rv.get("value")
        try:
            parent_confidence = float(rv.get("confidence") or 0.0)
        except Exception:
            parent_confidence = 0.0
    elif isinstance(rv, list):
        segs = rv
    else:
        # If AI returned a string, number, or None, treat as no segments
        segs = []

    if not isinstance(segs, list):
        segs = []

    clean = []
    for entry in segs:
        if not isinstance(entry, dict):
            try:
                print(
                    f"[qualitative] Skipping non-dict entry in revenue_by_segment: {entry}"
                )
            except Exception:
                pass
            continue
        seg_name = (
            entry.get("segment")
            or entry.get("segment_original_name")
            or entry.get("name")
        )
        if not seg_name:
            continue

        # Normalize value block
        val_block = entry.get("value") or entry.get("amount") or {}
        if not isinstance(val_block, dict):
            try:
                numeric = float(val_block)
                val_block = {"value": numeric, "unit": "USD"}
            except Exception:
                val_block = {"value": 0, "unit": "USD"}

        try:
            vnum = float(val_block.get("value", 0) or 0)
        except Exception:
            vnum = 0

        unit = _normalize_value_unit_label(val_block.get("unit"))

        try:
            confidence = float(entry.get("confidence") or 0.0)
        except Exception:
            confidence = 0.0

        # Fallback to parent confidence if item confidence is 0.0
        if confidence == 0.0 and parent_confidence > 0.0:
            confidence = parent_confidence

        # Preserve any year/report metadata for downstream processing
        year_val = (
            entry.get("year") or entry.get("fiscal_year") or entry.get("report_year")
        )
        report_date_val = entry.get("report_date")

        clean_entry = {
            "segment": seg_name,
            "segment_original_name": seg_name,
            "segment_group": _map_segment_group(seg_name),
            "value": {"value": vnum, "unit": unit},
            "confidence": confidence,
            "revenue_growth_pct": entry.get("revenue_growth_pct"),
            "data_source": "AI",
        }
        if year_val is not None:
            try:
                clean_entry["year"] = int(str(year_val)[:4])
            except Exception:
                clean_entry["year"] = year_val
        if report_date_val is not None:
            clean_entry["report_date"] = report_date_val
        clean.append(clean_entry)

    if clean:
        # Don't print full normalized structures to avoid noisy logs and potential PII leakage.
        final_json["revenue_by_segment"] = {"value": clean, "confidence": 0.9}
    else:
        try:
            print("[qualitative] No AI revenue segments found to normalize.")
        except Exception:
            pass
    return final_json


def _normalize_ai_regions(final_json: dict) -> dict:
    """Normalize AI-provided revenue_by_region entries to a stable shape.

    Expected to produce entries like:
      {"region": "United States", "year": 2024, "value": {"value": 61257, "unit": "millions"}, "confidence": 0.95}
    Accepts: dict with 'value' list, or plain list, or mixed partials.
    """
    if not isinstance(final_json, dict):
        return final_json

    rv = final_json.get("revenue_by_region")
    regions = []
    parent_confidence = 0.0
    if isinstance(rv, dict):
        regions = rv.get("value")
        try:
            parent_confidence = float(rv.get("confidence") or 0.0)
        except Exception:
            parent_confidence = 0.0
    elif isinstance(rv, list):
        regions = rv
    else:
        regions = []

    if not isinstance(regions, list):
        regions = []

    clean = []
    for entry in regions:
        if not isinstance(entry, dict):
            continue
        region_name = (
            entry.get("region") or entry.get("name") or entry.get("region_original")
        )
        if not region_name:
            continue

        val_block = entry.get("value") or entry.get("amount") or {}
        if not isinstance(val_block, dict):
            try:
                numeric = float(val_block)
                val_block = {"value": numeric, "unit": "USD"}
            except Exception:
                val_block = {"value": 0, "unit": "USD"}

        try:
            vnum = float(val_block.get("value", 0) or 0)
        except Exception:
            vnum = 0

        unit = _normalize_value_unit_label(val_block.get("unit"))

        try:
            confidence = float(entry.get("confidence") or 0.0)
        except Exception:
            confidence = 0.0

        if confidence == 0.0 and parent_confidence > 0.0:
            confidence = parent_confidence

        year = entry.get("year") or entry.get("fiscal_year") or None
        try:
            year = int(year) if year is not None else None
        except Exception:
            year = None

        clean_entry = {
            "region": region_name,
            "value": {"value": vnum, "unit": unit},
            "confidence": confidence,
            "data_source": "AI",
        }
        if year is not None:
            clean_entry["year"] = year
        clean.append(clean_entry)

    if clean:
        final_json["revenue_by_region"] = {"value": clean, "confidence": 0.9}
    else:
        # leave as-is; sanitize will create empty structure
        pass
    return final_json


def _normalize_buyback_analysis(final_json: dict) -> dict:
    """Ensure buyback_analysis entries are available in a consistent numeric shape."""
    if not isinstance(final_json, dict):
        return final_json

    # Prefer explicit top-level key but allow fallbacks under financial_extracts
    section = final_json.get("buyback_analysis")
    if not section and isinstance(final_json.get("financial_extracts"), dict):
        extracts = final_json["financial_extracts"]
        section = (
            extracts.get("buyback_analysis")
            or extracts.get("buyback_activity")
            or extracts.get("buyback_metrics")
        )

    entries_raw = []
    section_conf = 0.0
    if isinstance(section, dict):
        entries_raw = section.get("value") or section.get("entries") or []
        try:
            section_conf = float(section.get("confidence") or 0.0)
        except Exception:
            section_conf = 0.0
    elif isinstance(section, list):
        entries_raw = section
    else:
        entries_raw = []

    def _to_float(val):
        if val is None:
            return None
        if isinstance(val, (int, float)):
            try:
                return float(val)
            except Exception:
                return None
        if isinstance(val, str):
            cleaned = val.replace(",", " ").strip().lower()
            match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
            if match:
                try:
                    return float(match.group())
                except Exception:
                    return None
        return None

    def _scale_units(value, unit: str) -> float | None:
        num = _to_float(value)
        if num is None:
            return None
        unit_l = (unit or "").lower()
        if "trillion" in unit_l or unit_l.endswith("t"):
            num *= 1_000_000_000_000
        elif "billion" in unit_l or unit_l.endswith("b"):
            num *= 1_000_000_000
        elif "million" in unit_l or unit_l.endswith("m"):
            num *= 1_000_000
        elif "thousand" in unit_l or unit_l.endswith("k"):
            num *= 1_000
        return num

    normalized = []
    for entry in entries_raw:
        if not isinstance(entry, dict):
            continue

        year = entry.get("year") or entry.get("fiscal_year") or entry.get("report_year")
        try:
            year = int(str(year)[:4]) if year is not None else None
        except Exception:
            year = None

        shares_block = entry.get("shares_repurchased") or entry.get("shares_buyback")
        cost_block = (
            entry.get("total_cost_of_buybacks")
            or entry.get("buyback_cost")
            or entry.get("total_buyback_cost")
        )
        avg_block = entry.get("avg_buyback_price") or entry.get("average_buyback_price")

        def _extract(block, default_unit):
            if isinstance(block, dict):
                unit = block.get("unit") or default_unit
                value = block.get("value")
            else:
                unit = default_unit
                value = block
            numeric = _to_float(value)
            if numeric is not None and numeric < 0:
                numeric = abs(numeric)
            scaled = _scale_units(value, unit)
            if scaled is not None and scaled < 0:
                scaled = abs(scaled)
            return numeric, (unit or default_unit), scaled

        shares_value, shares_unit, shares_scaled = _extract(shares_block, "shares")
        cost_value, cost_unit, cost_scaled = _extract(cost_block, "usd")
        avg_value, avg_unit, avg_scaled = _extract(avg_block, "usd per share")

        if avg_value is None and shares_scaled and cost_scaled:
            try:
                avg_value = cost_scaled / shares_scaled if shares_scaled else None
                avg_unit = avg_unit or "usd per share"
            except Exception:
                avg_value = None

        if shares_value is None and cost_value is None and avg_value is None:
            continue

        entry_conf = entry.get("confidence")
        try:
            entry_confidence = (
                float(entry_conf) if entry_conf is not None else section_conf
            )
        except Exception:
            entry_confidence = section_conf

        normalized_entry = {
            "year": year,
            "shares_repurchased": {
                "value": shares_value if shares_value is not None else None,
                "unit": shares_unit or "shares",
            },
            "total_cost_of_buybacks": {
                "value": cost_value if cost_value is not None else None,
                "unit": cost_unit or "usd",
            },
            "avg_buyback_price": {
                "value": avg_value if avg_value is not None else None,
                "unit": avg_unit or "usd_per_share",
            },
            "confidence": float(entry_confidence or 0.0),
        }
        normalized.append(normalized_entry)

    if section_conf:
        overall_conf = section_conf
    else:
        overall_conf = (
            max((e.get("confidence") or 0.0) for e in normalized) if normalized else 0.0
        )

    buyback_payload = {"value": normalized, "confidence": float(overall_conf or 0.0)}
    final_json["buyback_analysis"] = buyback_payload
    return final_json


# ========= The Final Main Pipeline =========
def process_filing(filing_id: str, sec_url: str):
    print("--- Starting Robust Hybrid Qualitative Pipeline ---")
    # Always fetch the SEC filing and clean text. Do not store or read gzip cache.
    try:
        raw_text = fetch_sec_filing(sec_url)
        cleaned_text = clean_filing_text(raw_text)
    except Exception as e:
        raise QualitativeAnalysisError(f"Failed to fetch or clean filing: {e}")

    token_count = get_token_count(cleaned_text)
    model_alias = select_available_model_alias(SUMMARY_MODEL_PREFERENCE)
    if not model_alias:
        raise QualitativeAnalysisError(
            "No Gemini model configured for qualitative analysis."
        )
    # FIX: Get the actual model name here (e.g. "gemini-3-flash") to pass to the API
    # instead of passing "default" which causes 404s.
    actual_model_name = resolve_model_name(SUMMARY_MODEL_PREFERENCE)
    # Also keep model_name for DB logging (can be same)
    model_name = actual_model_name

    print(f"Approximate token count: {token_count}")

    final_json = None

    if (token_count * 1.15) < SINGLE_CALL_TOKEN_THRESHOLD:
        print(
            "--- Document is within threshold. Attempting direct analysis strategy. ---"
        )
        safe_prompt = FINAL_ANALYSIS_PROMPT.replace("{text_content}", cleaned_text)
        final_json = _gemini_summarize_with_cooldown(
            safe_prompt, return_json=True, model=actual_model_name
        )
        if not _validate_final_json(final_json):
            print(
                "\n!!! Direct analysis failed. Falling back to sequential chunk summarization. !!!\n"
            )
            final_json = None

    if final_json is None:
        print(
            "--- Document is large or fallback triggered. Using sequential chunk summarization with cooldown. ---"
        )
        chunks = chunk_text(cleaned_text, max_tokens=120000)
        partials = []
        for i, chunk in enumerate(chunks):
            print(
                f"Dispatching chunk {i + 1}/{len(chunks)} to Gemini (60s cooldown enforced)..."
            )
            safe_prompt = FINAL_ANALYSIS_PROMPT.replace("{text_content}", chunk)
            response = _gemini_summarize_with_cooldown(
                safe_prompt, return_json=True, model=actual_model_name
            )
            if response:
                partials.append(response)
        if not partials:
            print(
                "!!! Chunked summarization failed. Falling back to lightweight heuristic summary. !!!"
            )
            final_json = _default_final_json_template()
        else:
            final_json = merge_partials(partials)

    final_json = _ensure_final_json(final_json)

    if not _validate_final_json(final_json):
        raise QualitativeAnalysisError(
            "Final analysis pass returned an invalid JSON object."
        )
    # Normalize AI revenue shapes to match the canonical schema, then sanitize
    try:
        final_json = _normalize_ai_revenue(final_json)
    except Exception as e:
        print(f"[qualitative] Warning: failed to normalize AI revenue: {e}")
    # Normalize region entries as well (multi-year support)
    try:
        final_json = _normalize_ai_regions(final_json)
    except Exception as e:
        print(f"[qualitative] Warning: failed to normalize AI regions: {e}")
    # Normalize buyback analysis entries for downstream consumption
    try:
        final_json = _normalize_buyback_analysis(final_json)
    except Exception as e:
        print(f"[qualitative] Warning: failed to normalize buyback analysis: {e}")
    # Normalize revenue-related fields to prevent downstream KeyErrors
    try:
        final_json = _sanitize_revenue_fields(final_json)
    except Exception as e:
        print(f"[qualitative] ERROR while sanitizing revenue fields: {e}")
        # fallback: reset revenue fields ป้องกัน pipeline ล้ม
        final_json["revenue_by_segment"] = {"value": [], "confidence": 0.0}
        final_json["revenue_by_region"] = {"value": [], "confidence": 0.0}

    # --- THIS IS THE RESTORED DATABASE SAVING LOGIC ---
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO document_summaries (filing_id, gemini_summary_json, ai_model, last_updated)
                    VALUES (%s, %s, %s, %s) ON CONFLICT (filing_id) DO UPDATE
                    SET gemini_summary_json = EXCLUDED.gemini_summary_json,
                        ai_model = EXCLUDED.ai_model,
                        last_updated = EXCLUDED.last_updated
                    """,
                    (
                        filing_id,
                        Json(final_json),
                        model_name,
                        datetime.now(timezone.utc),
                    ),
                )
            conn.commit()
            print("Successfully saved final AI summary to DB.")
    except Exception as e:
        print(f"Error saving final AI summary to DB: {e}")
        # Optionally re-raise the exception if saving is critical
        raise QualitativeAnalysisError(f"Failed to save summary to DB: {e}")
    # --- END OF RESTORED LOGIC ---

    return final_json, cleaned_text


def process_fund_profile(filing_id: str, profile_text: str):
    """
    Alternative AI pathway for Funds and ETFs that lack SEC 10-K filings.
    Instead of fetching from sec_url, it digests the profile text and returns the JSON analysis.
    """
    print("--- Starting Fund/ETF Qualitative Pipeline ---")
    
    token_count = get_token_count(profile_text)
    actual_model_name = resolve_model_name(SUMMARY_MODEL_PREFERENCE)
    model_name = actual_model_name

    print(f"Approximate token count for fund profile: {token_count}")
    
    safe_prompt = FUND_ANALYSIS_PROMPT.replace("{text_content}", profile_text or "No business summary available.")
    final_json = _gemini_summarize_with_cooldown(
        safe_prompt, return_json=True, model=actual_model_name
    )
    
    if not _validate_final_json(final_json):
        print("!!! Direct fund analysis failed. Falling back to default skeleton. !!!")
        final_json = _default_final_json_template()

    final_json = _ensure_final_json(final_json)

    try:
        final_json = _normalize_ai_revenue(final_json)
        final_json = _normalize_ai_regions(final_json)
        final_json = _normalize_buyback_analysis(final_json)
        final_json = _sanitize_revenue_fields(final_json)
    except Exception as e:
        print(f"[fund_qualitative] WARNING: Field normalization failed: {e}")

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO document_summaries (filing_id, gemini_summary_json, ai_model, last_updated)
                    VALUES (%s, %s, %s, %s) ON CONFLICT (filing_id) DO UPDATE
                    SET gemini_summary_json = EXCLUDED.gemini_summary_json,
                        ai_model = EXCLUDED.ai_model,
                        last_updated = EXCLUDED.last_updated
                    """,
                    (
                        filing_id,
                        Json(final_json),
                        model_name,
                        datetime.now(timezone.utc),
                    ),
                )
            conn.commit()
            print("Successfully saved fund AI summary to DB.")
    except Exception as e:
        print(f"Error saving fund AI summary to DB: {e}")
        raise QualitativeAnalysisError(f"Failed to save summary to DB: {e}")

    return final_json, profile_text

# ========= Tier 3 Helpers =========
def chunk_text(text: str, max_tokens=120000):
    """Length-based chunking function using tiktoken."""
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks = []
    for i in range(0, len(tokens), max_tokens):
        chunk_tokens = tokens[i : i + max_tokens]
        chunks.append(enc.decode(chunk_tokens))
    return chunks


def merge_partials(partials: list[dict]) -> dict:
    """Merge multiple partial JSON outputs into one coherent JSON."""
    if not any(p for p in partials):
        return {}
    base_index = next((i for i, p in enumerate(partials) if p), 0)
    merged = partials[base_index].copy()

    # Keys that should not be concatenated, but rather "first wins" or "majority vote" (simplified to first wins)
    SINGLE_VALUE_KEYS = {
        "INDUSTRY_ASSET",
        "ham_sandwich_test",
        "pricing_power",
        "management_candor",
        "stock_option_alignment",
        "institutional_imperative_assessment",
        "company_type",
    }

    for p in partials[base_index + 1 :]:
        if not p:
            continue
        for key, base_data in merged.items():
            new_data = p.get(key)
            if isinstance(base_data, dict) and isinstance(new_data, dict):
                base_value = base_data.get("value")
                new_value = new_data.get("value")

                # Handling for single-label fields: keep existing if present, else take new
                if key in SINGLE_VALUE_KEYS:
                    if not base_value and new_value:
                        merged[key]["value"] = new_value
                        # Also update metadata like confidence/rationale if we switched
                        if "confidence" in new_data:
                            merged[key]["confidence"] = new_data["confidence"]
                        if "rationale" in new_data:
                            merged[key]["rationale"] = new_data["rationale"]
                    continue

                if new_value is not None:
                    if isinstance(base_value, str) and isinstance(new_value, str):
                        # Smart String Dedup
                        b_clean = base_value.strip()
                        n_clean = new_value.strip()

                        if not b_clean:
                            merged[key]["value"] = n_clean
                        elif not n_clean:
                            pass  # Keep base
                        elif b_clean.lower() == n_clean.lower():
                            pass  # Identical, ignore
                        elif n_clean in b_clean:
                            pass  # New is subset, ignore
                        elif b_clean in n_clean:
                            merged[key]["value"] = n_clean  # Base is subset, upgrade
                        else:
                            # Genuine Append
                            merged[key]["value"] = (b_clean + " " + n_clean).strip()

                    elif isinstance(base_value, list) and isinstance(new_value, list):
                        # List dedup happens naturally later for some keys, but let's be safe
                        # For simple lists of strings (e.g. risks), extend and set-dedup
                        extended = base_value + new_value
                        try:
                            deduped = []
                            seen_primitives = set()
                            seen_objects = {}

                            for item in extended:
                                if isinstance(item, (str, int, float)):
                                    # Normalize primitive strings for dedup
                                    val_str = str(item).strip()
                                    key_primitive = val_str.lower()
                                    if key_primitive not in seen_primitives:
                                        seen_primitives.add(key_primitive)
                                        deduped.append(item)
                                elif isinstance(item, dict):
                                    # Try to find a primary identifier for the object
                                    ident = (
                                        item.get("type") or
                                        item.get("risk_category") or
                                        item.get("category") or
                                        item.get("label") or
                                        item.get("name") or
                                        item.get("title") or
                                        item.get("risk")
                                    )
                                    
                                    if ident and isinstance(ident, str):
                                        ident_key = ident.strip().lower()
                                        if ident_key in seen_objects:
                                            # We already have an object for this identifier. Merge rationale/description.
                                            existing = seen_objects[ident_key]
                                            for text_field in ["rationale", "description", "detail", "details", "reasoning"]:
                                                if item.get(text_field):
                                                    if not existing.get(text_field):
                                                        existing[text_field] = item[text_field]
                                                    elif item[text_field] not in str(existing[text_field]):
                                                        existing[text_field] = str(existing[text_field]) + "\n\n" + str(item[text_field])
                                        else:
                                            # First time seeing this identifier
                                            item_copy = item.copy()
                                            seen_objects[ident_key] = item_copy
                                            deduped.append(item_copy)
                                    else:
                                        # No clear identifier, fallback to json dump dedup
                                        s_rep = json.dumps(item, sort_keys=True)
                                        if s_rep not in seen_primitives:
                                            seen_primitives.add(s_rep)
                                            deduped.append(item)
                                else:
                                    deduped.append(item)
                                    
                            merged[key]["value"] = deduped
                        except Exception:
                            merged[key]["value"] = extended  # Fallback

        # Special handling for revenue lists which may be present in some partials
        for revenue_key in ("revenue_by_segment", "revenue_by_region"):
            if revenue_key not in merged:
                if p.get(revenue_key) is not None:
                    merged[revenue_key] = p[revenue_key]
                continue
            # both exist: merge lists and deduplicate by segment/region name
            base_list = merged.get(revenue_key, {}).get("value", []) or []
            new_list = p.get(revenue_key, {}).get("value", []) or []
            combined = base_list + new_list
            deduped = []
            seen = set()
            for entry in combined:
                # Deduplicate by (name, year) when possible so multi-year entries are kept.
                name_part = entry.get("segment") or entry.get("region")
                if not name_part:
                    name_part = json.dumps(entry)
                year_part = (
                    entry.get("year")
                    or entry.get("fiscal_year")
                    or entry.get("year_reported")
                )
                try:
                    year_part = str(int(year_part)) if year_part is not None else ""
                except Exception:
                    year_part = str(year_part) if year_part is not None else ""

                key_name = (
                    f"{name_part}::{year_part}" if year_part else f"{name_part}::"
                )
                if key_name in seen:
                    continue
                seen.add(key_name)
                deduped.append(entry)
            if revenue_key not in merged:
                merged[revenue_key] = {"value": deduped, "confidence": 0.0}
            else:
                merged[revenue_key]["value"] = deduped
    return merged
