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


def _editorial_topic_match_score(item: dict, product_context: dict | None) -> int:
    """Prefer an article that helps with the next product, without inventing a match."""
    if not isinstance(product_context, dict):
        return 0
    title = " ".join(str(product_context.get(key) or "") for key in (
        "title", "category", "catalog_category_name", "catalog_category_path",
    ))
    title = title.replace("\\u200c", " ")
    topic = str(item.get("topic") or "").lower()
    rules = {
        "device-compatibility": r"گوشی|موبایل|تبلت|لپ.?تاپ|کامپیوتر|مودم|شارژر|کابل|هدفون|هندزفری|اسپیکر|تلویزیون|دوربین",
        "fit-and-size": r"لباس|پوشاک|کفش|کیف|عینک|میز|صندلی|تشک|پرده|فرش|مبلمان",
        "maintenance-and-care": r"لوازم خانگی|یخچال|لباسشویی|ظرفشویی|جارو|قهوه ساز|قابلمه|ابزار|خودرو|دوچرخه",
        "product-safety": r"کودک|نوزاد|برقی|شارژر|باتری|لوازم پزشکی|سلامت",
        "product-condition": r"کارکرده|دست دوم|بازسازی|استوک",
        "shipping-and-returns": r"سفارشی|ارسال|مرجوع|تعویض",
        "total-cost": r"قیمت|هزینه|قسط|اقساط|پرداخت",
        "seller-verification": r"فروشنده|مارکت.?پلیس|فروشگاه",
        "seller-check": r"فروشنده|مارکت.?پلیس|فروشگاه",
        "privacy-and-security": r"گوشی|موبایل|تبلت|لپ.?تاپ|کامپیوتر|مودم|دوربین|گجت",
    }
    pattern = rules.get(topic)
    if pattern and re.search(pattern, title, re.I):
        return 10
    if topic in {"product-inspection", "review-literacy", "purchase-planning", "safe-payment"}:
        return 2
    return 0


def select_editorial_fallback(
    bank: list[dict],
    state: dict,
    *,
    now: datetime | None = None,
    cooldown_hours: int = DEFAULT_COOLDOWN_HOURS,
    topic_cooldown_hours: int = DEFAULT_TOPIC_COOLDOWN_HOURS,
    product_context: dict | None = None,
) -> dict | None:
    """Select an approved, unused item; restart the editorial cycle only when exhausted.

    The bank is read afresh by the caller on every selection. Newly reviewed IDs are
    therefore eligible immediately, while only confirmed deliveries consume a cycle slot.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    active_state = state if isinstance(state, dict) else {}
    history = _history_rows(active_state)
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

    rotation = active_state.setdefault("editorial_rotation", {})
    if not isinstance(rotation, dict):
        rotation = {}
        active_state["editorial_rotation"] = rotation
    used_ids = {str(value) for value in rotation.get("used_ids", []) if str(value)}
    active_queue = active_state.get("editorial_delivery_queue")
    active_ids = {
        str(row.get("payload", {}).get("editorial_id") or row.get("content_id") or "").removeprefix("editorial:")
        for row in (active_queue.values() if isinstance(active_queue, dict) else [])
        if isinstance(row, dict) and row.get("status") not in {"completed", "cancelled", "failed"}
    }

    valid_items = []
    for raw in bank if isinstance(bank, list) else []:
        ok, _reason = validate_editorial_item(raw, now=current)
        if ok:
            valid_items.append(raw)
    if not valid_items:
        return None
    bank_ids = {str(row["editorial_id"]) for row in valid_items}

    def available(*, ignore_recent_items: bool = False, ignore_recent_topics: bool = False):
        rows = []
        for raw in valid_items:
            editorial_id = str(raw["editorial_id"])
            topic = str(raw["topic"]).lower()
            if editorial_id in used_ids or editorial_id in active_ids:
                continue
            if not ignore_recent_items and editorial_id in recent_ids:
                continue
            if not ignore_recent_topics and topic in recent_topic_ids:
                continue
            rows.append(raw)
        return rows

    eligible = available()
    if not eligible:
        # A cycle is exhausted only when every currently approved item has been used
        # or is already queued. New bank IDs are always treated as unseen additions.
        unseen = bank_ids - used_ids - active_ids
        if not unseen and not active_ids:
            rotation["cycle_number"] = max(1, int(rotation.get("cycle_number") or 1)) + 1
            rotation["cycle_started_at"] = current.isoformat()
            rotation["used_ids"] = []
            used_ids = set()
            eligible = available()
            if not eligible:
                eligible = available(ignore_recent_items=True)
            if not eligible:
                eligible = available(ignore_recent_items=True, ignore_recent_topics=True)
            print(
                "EDITORIAL_CYCLE_RESTARTED "
                f"cycle={rotation['cycle_number']} approved_items={len(bank_ids)} "
                f"new_items_included={len(bank_ids - {str(row.get('editorial_id') or '') for row in history})}"
            )
        else:
            # When a new item is queued or a topic is cooling down, relax the item
            # cooldown first; never select an ID already queued or used in this cycle.
            eligible = available(ignore_recent_items=True)
            if not eligible:
                eligible = available(ignore_recent_items=True, ignore_recent_topics=True)

    if not eligible:
        return None

    eligible.sort(key=lambda row: (
        -_editorial_topic_match_score(row, product_context),
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
        "topic_match_score": _editorial_topic_match_score(chosen, product_context),
        "rotation_cycle": int(rotation.get("cycle_number") or 1),
        "sequence_number": None,
        "delivery_status": "selected_not_published",
    }


def enqueue_editorial_entry(
    state: dict,
    bank: list[dict],
    *,
    scheduled_at: datetime,
    now: datetime | None = None,
    product_context: dict | None = None,
) -> dict | None:
    """Add one reviewed article to the shared FIFO without performing network delivery."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    scheduled = scheduled_at
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)
    scheduled = max(current, scheduled.astimezone(timezone.utc))
    item = select_editorial_fallback(
        bank, state, now=current, product_context=product_context,
    )
    if not item:
        return None
    from content_delivery import allocate_publication_sequence
    from platform_registry import PLATFORM_NAMES

    sequence_number = allocate_publication_sequence(state)
    item["sequence_number"] = sequence_number
    entry = {
        "content_id": item["content_id"],
        "content_type": "editorial",
        "sequence_number": sequence_number,
        "selected_at": current.isoformat(),
        "scheduled_at": scheduled.isoformat(),
        "next_attempt_at": scheduled.isoformat(),
        "status": "queued",
        "attempt_count": 0,
        "payload": item,
        "platforms": {
            name: {"status": "pending", "attempts": 0}
            for name in PLATFORM_NAMES
        },
    }
    queue = state.setdefault("editorial_delivery_queue", {})
    if not isinstance(queue, dict):
        queue = {}
        state["editorial_delivery_queue"] = queue
    queue[item["content_id"]] = entry
    print(
        "EDITORIAL_FLOATING_SLOT_QUEUED "
        f"content_id={item['content_id']} sequence={sequence_number} "
        f"scheduled_at={scheduled.isoformat()} topic_match={item.get('topic_match_score', 0)}"
    )
    return entry


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
    rotation = state.setdefault("editorial_rotation", {})
    if not isinstance(rotation, dict):
        rotation = {}
        state["editorial_rotation"] = rotation
    used_ids = [str(value) for value in rotation.get("used_ids", []) if str(value)]
    editorial_id = str(item.get("editorial_id") or "")
    if editorial_id and editorial_id not in used_ids:
        used_ids.append(editorial_id)
    rotation["used_ids"] = used_ids
    rotation["last_confirmed_editorial_id"] = editorial_id
    rotation["last_confirmed_at"] = timestamp.astimezone(timezone.utc).isoformat()
