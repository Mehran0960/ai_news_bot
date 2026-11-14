"""Safe editorial fallback content contracts for OfferChin."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

EDITORIAL_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
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


def _safe_source(source: Any) -> bool:
    if not isinstance(source, dict):
        return False
    url = str(source.get("url") or "").strip()
    title = str(source.get("title") or "").strip()
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc) and bool(title)


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
        refs = claim.get("source_ids")
        if not isinstance(refs, list) or not refs or any(str(ref) not in source_ids for ref in refs):
            return False, "claim_without_source"
    return True, "ok"


def _history_rows(state: dict) -> list[dict]:
    rows = state.get("editorial_delivery_history")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def editorial_topics_for_product(product: Any) -> set[str]:
    """Return reviewed editorial topics that can support a nearby product decision."""
    if not isinstance(product, dict):
        return set()
    factors = product.get("offerchin_four_factor")
    group = str(factors.get("generality_group") or "").strip().lower() if isinstance(factors, dict) else ""
    mapping = {
        "mobile_productivity": {"device-compatibility", "warranty-and-service", "privacy-and-security", "product-inspection", "purchase-planning"},
        "audio_visual": {"device-compatibility", "warranty-and-service", "privacy-and-security", "product-inspection", "review-literacy"},
        "home_cleaning": {"maintenance-and-care", "product-safety", "total-cost", "product-inspection"},
        "kitchen_food": {"maintenance-and-care", "product-safety", "total-cost", "product-inspection"},
        "grocery_food": {"product-safety", "product-condition", "total-cost", "seller-check"},
        "personal_care": {"product-safety", "product-condition", "product-inspection", "purchase-planning"},
        "home_living": {"fit-and-size", "product-inspection", "total-cost", "purchase-planning"},
        "fashion_lifestyle": {"fit-and-size", "product-condition", "product-inspection", "purchase-planning"},
        "baby_care": {"product-safety", "product-condition", "seller-check"},
        "tools_industrial": {"product-safety", "maintenance-and-care", "warranty-and-service"},
        "automotive": {"maintenance-and-care", "warranty-and-service", "product-safety"},
        "office_study": {"device-compatibility", "fit-and-size", "product-inspection"},
        "books_learning": {"review-literacy", "purchase-planning"},
    }
    return set(mapping.get(group, {"purchase-planning", "review-literacy", "seller-check"}))


def select_editorial_fallback(
    bank: list[dict],
    state: dict,
    *,
    now: datetime | None = None,
    cooldown_hours: int = DEFAULT_COOLDOWN_HOURS,
    topic_cooldown_hours: int = DEFAULT_TOPIC_COOLDOWN_HOURS,
    related_product: dict | None = None,
) -> dict | None:
    """Select a reviewed item from a repeating bank cycle, preferring product relevance.

    Each valid item is used once per cycle. When the current bank is exhausted, all
    currently valid items become eligible again. New IDs are added to the active cycle
    immediately, so approved additions are not lost behind an older rotation.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    history = _history_rows(state if isinstance(state, dict) else {})

    valid_items = []
    for raw in bank if isinstance(bank, list) else []:
        ok, _reason = validate_editorial_item(raw, now=current)
        if ok:
            valid_items.append(raw)
    if not valid_items:
        return None

    current_ids = sorted({str(item["editorial_id"]) for item in valid_items})
    cycle = state.setdefault("editorial_cycle", {})
    if not isinstance(cycle, dict):
        cycle = {}
        state["editorial_cycle"] = cycle
    old_used = cycle.get("used_ids")
    old_used = old_used if isinstance(old_used, list) else []
    used_ids = set(str(value) for value in old_used).intersection(current_ids)
    cycle["bank_ids"] = current_ids
    cycle["used_ids"] = sorted(used_ids)
    cycle.setdefault("cycle_number", 1)

    eligible = [item for item in valid_items if str(item["editorial_id"]) not in used_ids]
    if not eligible:
        try:
            cycle["cycle_number"] = max(1, int(cycle.get("cycle_number") or 1)) + 1
        except (TypeError, ValueError, OverflowError):
            cycle["cycle_number"] = 2
        cycle["used_ids"] = []
        cycle["cycle_started_at"] = current.isoformat()
        eligible = list(valid_items)

    recent_topics = {
        str(row.get("topic") or "").lower()
        for row in history[-3:]
        if isinstance(row, dict)
    }
    last_id = str(cycle.get("last_editorial_id") or "")
    if len(eligible) > 1:
        eligible = [
            item for item in eligible
            if str(item.get("editorial_id") or "") != last_id
        ] or eligible

    relevant_topics = editorial_topics_for_product(related_product)
    last_used: dict[str, datetime] = {}
    for row in history:
        topic = str(row.get("topic") or "").lower()
        published_at = _utc(row.get("published_at"))
        if topic and published_at and (
            topic not in last_used or published_at > last_used[topic]
        ):
            last_used[topic] = published_at

    def relevance(item: dict) -> int:
        topic = str(item.get("topic") or "").lower()
        if not related_product:
            return 0
        return 2 if topic in relevant_topics else 0

    eligible.sort(key=lambda row: (
        relevance(row),
        str(row.get("priority") or "normal"),
        last_used.get(str(row.get("topic") or "").lower(), datetime.min.replace(tzinfo=timezone.utc)),
        str(row["editorial_id"]),
    ), reverse=True)

    # Avoid adjacent topics where alternatives exist, but never strand the queue
    # because a topic cooldown or the finite bank has been exhausted.
    if len(eligible) > 1 and str(eligible[0].get("topic") or "").lower() in recent_topics:
        alternative = next(
            (row for row in eligible if str(row.get("topic") or "").lower() not in recent_topics),
            None,
        )
        if alternative is not None:
            eligible.remove(alternative)
            eligible.insert(0, alternative)

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
        "related_product_id": str((related_product or {}).get("product_id") or ""),
        "editorial_cycle_number": int(cycle.get("cycle_number") or 1),
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
    cycle = state.setdefault("editorial_cycle", {})
    if not isinstance(cycle, dict):
        cycle = {}
        state["editorial_cycle"] = cycle
    used = cycle.setdefault("used_ids", [])
    if not isinstance(used, list):
        used = []
        cycle["used_ids"] = used
    editorial_id = str(item["editorial_id"])
    if editorial_id not in used:
        used.append(editorial_id)
    cycle["used_ids"] = sorted(set(str(value) for value in used))
    cycle["last_editorial_id"] = editorial_id
    cycle["last_topic"] = str(item["topic"]).lower()

    history.append({
        "editorial_id": str(item["editorial_id"]),
        "content_id": str(item["content_id"]),
        "sequence_number": item.get("sequence_number"),
        "topic": str(item["topic"]),
        "published_at": timestamp.astimezone(timezone.utc).isoformat(),
        "destinations": destinations,
    })
    state["editorial_delivery_history"] = history[-200:]
