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

UNIVERSAL_EDITORIAL_TOPICS = frozenset({
    "purchase-planning",
    "review-literacy",
    "seller-check",
    "purchase-records",
    "delivery",
    "shipping-and-returns",
})
ALLOWED_EDITORIAL_TOPICS = UNIVERSAL_EDITORIAL_TOPICS | frozenset({
    "product-inspection",
    "total-cost",
    "fit-and-size",
    "device-compatibility",
    "warranty-and-service",
    "maintenance-and-care",
    "product-safety",
    "product-condition",
    "safe-payment",
    "seller-verification",
})
RETIRED_EDITORIAL_IDS = frozenset({
    "app-permissions",
    "privacy-policy",
    "location-sharing",
    "account-password",
})


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
    if editorial_id in RETIRED_EDITORIAL_IDS:
        return False, "retired_off_topic_item"
    if topic not in ALLOWED_EDITORIAL_TOPICS:
        return False, "unsupported_editorial_topic"
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

def _content_ledger_rows(state: dict) -> list[dict]:
    rows = state.get("editorial_content_ledger")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


_EDITORIAL_STOPWORDS = frozenset({
    "از", "به", "در", "و", "را", "برای", "که", "اگر", "با", "هم", "این", "آن",
    "تا", "پیش", "روی", "یک", "شود", "کن", "کنند", "کرد", "است", "هست", "باشد",
    "های", "ها", "هر", "همه", "خود", "فقط", "قبل", "بعد", "اما", "یا", "نیز",
    "چه", "شما", "تو", "می", "می‌شود", "می‌کنند", "می‌تواند", "می‌توانند",
})


def _editorial_tokens(value: Any) -> set[str]:
    text = str(value or "").strip().lower()
    text = text.translate(str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"}))
    text = re.sub(r"[\u064b-\u065f\u0670]", "", text).replace("\u200c", " ")
    tokens = re.findall(r"[a-z0-9\u0600-\u06ff]+", text, flags=re.IGNORECASE)
    return {
        token for token in tokens
        if len(token) > 1 and token not in _EDITORIAL_STOPWORDS
    }


def editorial_content_fingerprint(item: Any) -> str:
    """Stable fingerprint used to audit and compare delivered editorial copy."""
    if not isinstance(item, dict):
        return ""
    title = re.sub(r"\s+", " ", str(item.get("title") or "").strip())
    body = re.sub(r"\s+", " ", str(item.get("body") or "").strip())
    canonical = f"{title}\n{body}".translate(
        str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"})
    )
    canonical = re.sub(r"[\u064b-\u065f\u0670]", "", canonical).replace("\u200c", " ")
    canonical = re.sub(r"\s+", " ", canonical).strip().lower()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_near_duplicate_editorial(left: Any, right: Any) -> bool:
    """Catch copied or lightly paraphrased copy without blocking shared broad topics."""
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    left_fingerprint = editorial_content_fingerprint(left)
    right_fingerprint = editorial_content_fingerprint(right)
    if left_fingerprint and left_fingerprint == right_fingerprint:
        return True

    left_title = _editorial_tokens(left.get("title"))
    right_title = _editorial_tokens(right.get("title"))
    title_shared = len(left_title & right_title)
    title_union = len(left_title | right_title)
    if title_shared >= 4 and title_union and title_shared / title_union >= 0.82:
        return True

    left_body = _editorial_tokens(left.get("body"))
    right_body = _editorial_tokens(right.get("body"))
    shared = len(left_body & right_body)
    shorter = min(len(left_body), len(right_body))
    union = len(left_body | right_body)
    if shared < 7 or shorter < 8 or not union:
        return False
    jaccard = shared / union
    containment = shared / shorter
    return jaccard >= 0.78 or containment >= 0.92


def editorial_topics_for_product(product: Any) -> set[str]:
    """Return topics that genuinely help with this product's purchase or ownership."""
    factors = product.get("offerchin_four_factor") if isinstance(product, dict) else None
    group = str(factors.get("generality_group") or "").strip().lower() if isinstance(factors, dict) else ""
    mapping = {
        "mobile_productivity": {"device-compatibility", "warranty-and-service", "product-inspection"},
        "audio_visual": {"device-compatibility", "warranty-and-service", "product-inspection"},
        "home_cleaning": {"maintenance-and-care", "product-safety", "total-cost", "product-inspection"},
        "kitchen_food": {"maintenance-and-care", "product-safety", "total-cost", "product-inspection"},
        "grocery_food": {"product-safety", "product-condition", "total-cost"},
        "personal_care": {"product-safety", "product-condition", "product-inspection"},
        "home_living": {"fit-and-size", "product-inspection", "total-cost"},
        "fashion_lifestyle": {"fit-and-size", "product-condition", "product-inspection"},
        "baby_care": {"product-safety", "product-condition"},
        "tools_industrial": {"product-safety", "maintenance-and-care", "warranty-and-service"},
        "automotive": {"maintenance-and-care", "warranty-and-service", "product-safety"},
        "office_study": {"device-compatibility", "fit-and-size", "product-inspection"},
        "books_learning": set(),
    }
    # Purchase planning, seller trust, receipts and delivery are relevant across
    # e-commerce categories. Product-specific topics must match the product group.
    return set(UNIVERSAL_EDITORIAL_TOPICS) | set(mapping.get(group, set()))


def _editorial_source_rank(item: dict) -> int:
    """Prefer useful Iranian retail/editorial sources over generic foreign advice."""
    sources = item.get("sources") if isinstance(item, dict) else None
    for source in sources if isinstance(sources, list) else []:
        if not isinstance(source, dict):
            continue
        host = (urlparse(str(source.get("url") or "")).hostname or "").lower()
        if host == "digikala.com" or host.endswith(".digikala.com"):
            return 0
        if host == "zoomit.ir" or host.endswith(".zoomit.ir"):
            return 1
        if host.endswith(".ir"):
            return 2
    return 3


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

    relevant_topics = editorial_topics_for_product(related_product)
    valid_items = []
    for raw in bank if isinstance(bank, list) else []:
        ok, _reason = validate_editorial_item(raw, now=current)
        if ok and str(raw.get("topic") or "").strip().lower() in relevant_topics:
            valid_items.append(raw)
    # Editorial is a quality gate, not filler. If no reviewed item fits the
    # selected product, skip this editorial slot instead of publishing noise.
    if not valid_items:
        return None

    # A confirmed editorial is a one-time publication, not a reusable rotation slot.
    # The old 24-hour filter let a bank item re-enter after one day; because delivery
    # history was keyed only by content_id, later sends overwrote earlier receipts.
    bank_by_id = {
        str(row.get("editorial_id") or "").strip(): row
        for row in bank if isinstance(row, dict) and str(row.get("editorial_id") or "").strip()
    }
    ledger_rows = _content_ledger_rows(state if isinstance(state, dict) else {})
    previous_rows = history + ledger_rows
    delivered_ids = {
        str(value).strip()
        for value in (state.get("editorial_delivered_ids") or [])
        if str(value).strip()
    }
    delivered_fingerprints = {
        str(value).strip()
        for value in (state.get("editorial_delivered_fingerprints") or [])
        if str(value).strip()
    }
    previous_deliveries: list[dict] = []
    for row in previous_rows:
        previous_id = str(row.get("editorial_id") or "").strip()
        if previous_id:
            delivered_ids.add(previous_id)
        for value in row.get("editorial_ids", []) if isinstance(row.get("editorial_ids"), list) else []:
            if str(value).strip():
                delivered_ids.add(str(value).strip())
        fingerprint = str(row.get("content_fingerprint") or "").strip()
        if fingerprint:
            delivered_fingerprints.add(fingerprint)
        previous = bank_by_id.get(previous_id, {})
        previous_payload = {
            "editorial_id": previous_id,
            "title": row.get("title") or previous.get("title", ""),
            "body": row.get("body") or previous.get("body", ""),
        }
        if previous_payload["title"] or previous_payload["body"]:
            previous_deliveries.append(previous_payload)

    cycle_state = state.get("editorial_cycle") if isinstance(state, dict) else {}
    cycle_used_ids = cycle_state.get("used_ids") if isinstance(cycle_state, dict) else []
    delivered_ids.update(str(value).strip() for value in cycle_used_ids if str(value).strip())

    valid_items = [
        candidate for candidate in valid_items
        if str(candidate.get("editorial_id") or "").strip() not in delivered_ids
        and editorial_content_fingerprint(candidate) not in delivered_fingerprints
        and not any(_is_near_duplicate_editorial(candidate, previous) for previous in previous_deliveries)
    ]
    if not valid_items:
        return None

    # Enforce the configured topic cooldown against every confirmed recent
    # delivery, not only adjacent posts. This may skip an editorial slot, but
    # it never blocks the independent product queue.
    topic_cooldown = timedelta(hours=max(0, int(topic_cooldown_hours)))
    if topic_cooldown.total_seconds() > 0:
        recent_topic_times: dict[str, datetime] = {}
        for row in history:
            if not isinstance(row, dict):
                continue
            topic = str(row.get("topic") or "").strip().lower()
            published_at = _utc(row.get("published_at"))
            if topic and published_at is not None and published_at <= current:
                previous = recent_topic_times.get(topic)
                if previous is None or published_at > previous:
                    recent_topic_times[topic] = published_at
        valid_items = [
            candidate for candidate in valid_items
            if (
                str(candidate.get("topic") or "").strip().lower() not in recent_topic_times
                or current - recent_topic_times[str(candidate.get("topic") or "").strip().lower()] >= topic_cooldown
            )
        ]
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
        # Do not reset a completed cycle and repost its content. Newly approved IDs
        # can still join the rotation; otherwise this editorial slot stays empty.
        return None

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

    priority_rank = {"high": 0, "normal": 1, "low": 2}
    eligible.sort(key=lambda row: (
        -relevance(row),
        _editorial_source_rank(row),
        priority_rank.get(str(row.get("priority") or "normal").lower(), 1),
        last_used.get(str(row.get("topic") or "").lower(), datetime.min.replace(tzinfo=timezone.utc)),
        str(row["editorial_id"]),
    ))

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
    """Record each editorial event and preserve receipts for every destination."""
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
    timestamp = timestamp.astimezone(timezone.utc)

    editorial_id = str(item.get("editorial_id") or "").strip()
    content_id = str(item.get("content_id") or "").strip()
    if not editorial_id or not content_id:
        raise ValueError("editorial_identity_missing")
    fingerprint = editorial_content_fingerprint(item)
    sequence_number = item.get("sequence_number")
    event_id = (
        f"{content_id}:sequence:{sequence_number}"
        if sequence_number not in (None, "")
        else f"{content_id}:published:{timestamp.isoformat()}"
    )

    history = state.setdefault("editorial_delivery_history", [])
    if not isinstance(history, list):
        history = []
        state["editorial_delivery_history"] = history
    event = next(
        (
            row for row in history
            if isinstance(row, dict)
            and (
                str(row.get("delivery_event_id") or "") == event_id
                or (
                    str(row.get("content_id") or "") == content_id
                    and row.get("sequence_number") not in (None, "")
                    and sequence_number not in (None, "")
                    and str(row.get("sequence_number")) == str(sequence_number)
                )
            )
        ),
        None,
    )
    if event is None:
        event = {
            "delivery_event_id": event_id,
            "editorial_id": editorial_id,
            "content_id": content_id,
            "sequence_number": sequence_number,
            "topic": str(item.get("topic") or "").lower(),
            "related_product_id": str(item.get("related_product_id") or ""),
            "title": str(item.get("title") or "").strip(),
            "body": str(item.get("body") or "").strip(),
            "content_fingerprint": fingerprint,
            "published_at": timestamp.isoformat(),
            "destinations": {},
        }
        history.append(event)
    else:
        event.setdefault("delivery_event_id", event_id)
        event.setdefault("published_at", timestamp.isoformat())
        event["last_delivery_update_at"] = timestamp.isoformat()

    # Merge destination receipts: one channel update must not erase another's ID.
    merged_destinations = event.get("destinations")
    if not isinstance(merged_destinations, dict):
        merged_destinations = {}
    for destination, receipt in destinations.items():
        if not isinstance(receipt, dict):
            continue
        previous = merged_destinations.get(destination)
        previous = previous if isinstance(previous, dict) else {}
        if previous.get("status") == "sent" and receipt.get("status") != "sent":
            continue
        merged_destinations[destination] = dict(receipt)
    event["destinations"] = merged_destinations
    state["editorial_delivery_history"] = history[-200:]

    # These compact identity sets remain after the detailed event log is pruned.
    delivered_ids = {
        str(value).strip()
        for value in (state.get("editorial_delivered_ids") or [])
        if str(value).strip()
    }
    delivered_ids.add(editorial_id)
    state["editorial_delivered_ids"] = sorted(delivered_ids)
    delivered_fingerprints = {
        str(value).strip()
        for value in (state.get("editorial_delivered_fingerprints") or [])
        if str(value).strip()
    }
    if fingerprint:
        delivered_fingerprints.add(fingerprint)
    state["editorial_delivered_fingerprints"] = sorted(delivered_fingerprints)

    ledger = state.setdefault("editorial_content_ledger", [])
    if not isinstance(ledger, list):
        ledger = []
        state["editorial_content_ledger"] = ledger
    ledger_row = next(
        (row for row in ledger if isinstance(row, dict) and row.get("content_fingerprint") == fingerprint),
        None,
    )
    if ledger_row is None:
        ledger_row = {
            "editorial_ids": [editorial_id],
            "content_fingerprint": fingerprint,
            "title": str(item.get("title") or "").strip(),
            "body": str(item.get("body") or "").strip(),
            "first_published_at": timestamp.isoformat(),
            "last_published_at": timestamp.isoformat(),
            "delivery_count": 0,
            "delivery_event_ids": [],
        }
        ledger.append(ledger_row)
    editorial_ids = set(
        str(value) for value in ledger_row.get("editorial_ids", []) if str(value).strip()
    )
    editorial_ids.add(editorial_id)
    ledger_row["editorial_ids"] = sorted(editorial_ids)
    event_ids = set(
        str(value) for value in ledger_row.get("delivery_event_ids", []) if str(value).strip()
    )
    if event_id not in event_ids:
        event_ids.add(event_id)
        ledger_row["delivery_count"] = int(ledger_row.get("delivery_count") or 0) + 1
    ledger_row["delivery_event_ids"] = sorted(event_ids)
    ledger_row["last_published_at"] = max(
        str(ledger_row.get("last_published_at") or ""),
        timestamp.isoformat(),
    )
    state["editorial_content_ledger"] = ledger[-500:]

    cycle = state.setdefault("editorial_cycle", {})
    if not isinstance(cycle, dict):
        cycle = {}
        state["editorial_cycle"] = cycle
    used = cycle.setdefault("used_ids", [])
    if not isinstance(used, list):
        used = []
        cycle["used_ids"] = used
    if editorial_id not in used:
        used.append(editorial_id)
    cycle["used_ids"] = sorted(set(str(value) for value in used))
    cycle["last_editorial_id"] = editorial_id
    cycle["last_topic"] = str(item.get("topic") or "").lower()
