"""Safe editorial fallback content contracts for OfferChin."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

EDITORIAL_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
PERSIAN_SCRIPT = re.compile(r"[\u0600-\u06FF]")
LATIN_LETTERS = re.compile(r"[A-Za-z\u00C0-\u024F]")
MAX_TITLE = 110
MAX_BODY = 1800
DEFAULT_COOLDOWN_HOURS = 24
DEFAULT_TOPIC_COOLDOWN_HOURS = 4
FORBIDDEN_COMMERCE_TERMS = re.compile(
    r"(?:\b\d+\s*%\b|قیمت\s*(?:فعلی|روز)|موجودی\s*(?:فعلی|لحظه)|"
    r"تخفیف\s*(?:ویژه|قطعی)|ارزان[ت‌تر]*\s*ترین)",
    re.IGNORECASE,
)


def _utc(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def is_persian_public_text(value: Any) -> bool:
    """True only for non-empty Persian-script copy with no Latin letters."""
    text = str(value or "").strip()
    return bool(text and PERSIAN_SCRIPT.search(text) and not LATIN_LETTERS.search(text))


def _safe_source(source: Any) -> bool:
    if not isinstance(source, dict):
        return False
    url = str(source.get("url") or "").strip()
    title = str(source.get("title") or "").strip()
    display_title_fa = source.get("display_title_fa")
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and bool(title)
        and is_persian_public_text(display_title_fa)
    )


def validate_editorial_item(item: Any, *, now: datetime | None = None) -> tuple[bool, str]:
    """Validate a reviewed evergreen item; no current offer claims are allowed."""
    if not isinstance(item, dict):
        return False, "item_not_object"
    editorial_id = str(item.get("editorial_id") or "").strip()
    if not EDITORIAL_ID.fullmatch(editorial_id):
        return False, "invalid_editorial_id"
    title = str(item.get("title") or "").strip()
    body = str(item.get("body") or "").strip()
    topic = str(item.get("topic") or "").strip().lower()
    if not title or len(title) > MAX_TITLE or not body or len(body) > MAX_BODY:
        return False, "invalid_title_or_body_length"
    if not is_persian_public_text(title):
        return False, "editorial_title_must_be_persian_only"
    if not is_persian_public_text(body):
        return False, "editorial_body_must_be_persian_only"
    if not re.fullmatch(r"[a-z0-9-]{2,40}", topic):
        return False, "invalid_topic"
    if FORBIDDEN_COMMERCE_TERMS.search(title + "\n" + body):
        return False, "unsupported_commercial_claim"
    sources = item.get("sources")
    if not isinstance(sources, list) or not sources or not all(_safe_source(x) for x in sources):
        return False, "missing_or_invalid_sources"
    reviewed_at = _utc(item.get("reviewed_at"))
    review_due_at = _utc(item.get("review_due_at"))
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    if reviewed_at is None or review_due_at is None:
        return False, "missing_review_timestamps"
    if reviewed_at > current + timedelta(minutes=5):
        return False, "review_timestamp_in_future"
    if review_due_at <= current or review_due_at <= reviewed_at:
        return False, "editorial_review_expired"
    claims = item.get("claims")
    if not isinstance(claims, list) or not claims:
        return False, "missing_claim_provenance"
    source_ids = {str(s.get("source_id") or "").strip() for s in sources}
    if "" in source_ids:
        return False, "source_id_missing"
    for claim in claims:
        if not isinstance(claim, dict) or not str(claim.get("text") or "").strip():
            return False, "invalid_claim"
        if not is_persian_public_text(claim.get("text")):
            return False, "editorial_claim_must_be_persian_only"
        refs = claim.get("source_ids")
        if not isinstance(refs, list) or not refs or any(str(ref) not in source_ids for ref in refs):
            return False, "claim_without_source"
    return True, "ok"


def _history_rows(state: dict) -> list[dict]:
    rows = state.get("editorial_delivery_history")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def select_editorial_fallback(
    bank: list[dict],
    state: dict,
    *,
    now: datetime | None = None,
    cooldown_hours: int = DEFAULT_COOLDOWN_HOURS,
    topic_cooldown_hours: int = DEFAULT_TOPIC_COOLDOWN_HOURS,
) -> dict | None:
    """Select a reviewed, non-recent item with a shorter topic cooldown."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    history = _history_rows(state if isinstance(state, dict) else {})
    item_cutoff = current - timedelta(hours=max(1, int(cooldown_hours)))
    topic_cutoff = current - timedelta(hours=max(1, int(topic_cooldown_hours)))
    recent_items = [
        row for row in history
        if (_utc(row.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= item_cutoff
    ]
    recent_topics = [
        row for row in history
        if (_utc(row.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= topic_cutoff
    ]
    recent_ids = {str(row.get("editorial_id") or "") for row in recent_items}
    recent_topic_ids = {str(row.get("topic") or "") for row in recent_topics}
    last_used: dict[str, datetime] = {}
    for row in history:
        topic = str(row.get("topic") or "")
        published_at = _utc(row.get("published_at"))
        if topic and published_at and (topic not in last_used or published_at > last_used[topic]):
            last_used[topic] = published_at
    eligible = []
    for raw in bank if isinstance(bank, list) else []:
        ok, _reason = validate_editorial_item(raw, now=current)
        if not ok:
            continue
        editorial_id = str(raw["editorial_id"])
        topic = str(raw["topic"]).lower()
        if editorial_id in recent_ids or topic in recent_topic_ids:
            continue
        eligible.append(raw)
    if not eligible:
        return None
    eligible.sort(key=lambda row: (
        str(row.get("priority") or "normal"),
        last_used.get(str(row.get("topic") or "").lower(), datetime.min.replace(tzinfo=timezone.utc)),
        str(row["editorial_id"]),
    ))
    chosen = eligible[0]
    canonical = "editorial:" + str(chosen["editorial_id"])
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return {
        "content_type": "editorial",
        "content_id": canonical,
        "idempotency_key": digest,
        "editorial_id": str(chosen["editorial_id"]),
        "title": str(chosen["title"]).strip(),
        "body": str(chosen["body"]).strip(),
        "topic": str(chosen["topic"]).lower(),
        "sources": list(chosen["sources"]),
        "reviewed_at": str(chosen["reviewed_at"]),
        "review_due_at": str(chosen["review_due_at"]),
        "sequence_number": None,
        "delivery_status": "selected_not_published",
    }


def record_editorial_delivery(state: dict, item: dict, *, published_at: datetime, destinations: dict) -> None:
    """Record an editorial publication only after one destination confirms delivery."""
    if not isinstance(state, dict) or not isinstance(item, dict):
        raise ValueError("state_and_item_must_be_objects")
    if not isinstance(destinations, dict) or not any(
        isinstance(value, dict) and value.get("status") == "sent"
        for value in destinations.values()
    ):
        raise ValueError("confirmed_destination_required")
    timestamp = published_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    history = state.setdefault("editorial_delivery_history", [])
    if not isinstance(history, list):
        history = []
        state["editorial_delivery_history"] = history
    if any(str(row.get("content_id") or "") == str(item.get("content_id") or "") for row in history if isinstance(row, dict)):
        return
    history.append({
        "editorial_id": str(item["editorial_id"]),
        "content_id": str(item["content_id"]),
        "sequence_number": item.get("sequence_number"),
        "topic": str(item["topic"]),
        "published_at": timestamp.astimezone(timezone.utc).isoformat(),
        "destinations": destinations,
    })
    state["editorial_delivery_history"] = history[-200:]
