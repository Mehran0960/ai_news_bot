"""Shared OfferChin publication pacing and editorial-mix policy.

The channel clock is shared by product and editorial photo posts. Editorial content
remains a trust/utility layer and is admitted at most once per six confirmed product
channel posts. These rules are intentionally independent of video-platform quotas.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

MIN_CHANNEL_POST_INTERVAL_SECONDS = 31 * 60
PRODUCTS_PER_EDITORIAL_POST = 6
DEFAULT_DAILY_CHANNEL_POST_LIMIT = 55

CHANNEL_DESTINATIONS = ("telegram", "bale", "rubika", "eitaa")
_PRODUCT_ID = re.compile(r"^(?:dkp|snp)-\d{1,12}$", re.IGNORECASE)


def _timestamp(value: Any) -> float:
    """Parse an epoch or ISO timestamp into UTC epoch seconds."""
    try:
        if isinstance(value, (int, float)):
            parsed = float(value)
            return parsed if parsed > 0 else 0.0
        text = str(value or "").strip()
        if not text:
            return 0.0
        try:
            parsed = float(text)
            return parsed if parsed > 0 else 0.0
        except (TypeError, ValueError, OverflowError):
            parsed_dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
            return parsed_dt.astimezone(timezone.utc).timestamp()
    except (TypeError, ValueError, OverflowError, OSError):
        return 0.0


def _has_channel_success(row: dict) -> bool:
    delivery = row.get("delivery_status")
    if not isinstance(delivery, dict):
        delivery = row.get("destinations")
    if not isinstance(delivery, dict):
        delivery = row.get("platforms")
    if not isinstance(delivery, dict):
        return False

    for name in CHANNEL_DESTINATIONS:
        target = delivery.get(name)
        status = target.get("status") if isinstance(target, dict) else target
        if str(status or "").strip().lower() == "sent":
            return True
    return False


def products_published_since_last_editorial(state: dict) -> int:
    """Count distinct confirmed product channel posts after the latest confirmed editorial.

    A multi-platform post is counted once. Video-only editorial uploads do not reset
    the channel editorial ratio.
    """
    if not isinstance(state, dict):
        return 0

    editorial_times = []
    history = state.get("editorial_delivery_history")
    if isinstance(history, list):
        for row in history:
            if isinstance(row, dict) and _has_channel_success(row):
                stamp = _timestamp(row.get("published_at") or row.get("created_at"))
                if stamp > 0:
                    editorial_times.append(stamp)
    last_editorial = max(editorial_times) if editorial_times else 0.0

    product_posts: dict[str, float] = {}
    published = state.get("published")
    if isinstance(published, dict):
        for product_id, row in published.items():
            if not isinstance(row, dict) or not _PRODUCT_ID.fullmatch(str(product_id or "")):
                continue
            if not _has_channel_success(row):
                continue
            stamp = _timestamp(row.get("ts") or row.get("published_at"))
            if stamp > 0:
                product_posts[str(product_id)] = max(product_posts.get(str(product_id), 0.0), stamp)

    delivery_history = state.get("content_delivery_history")
    rows = delivery_history.values() if isinstance(delivery_history, dict) else (
        delivery_history if isinstance(delivery_history, list) else []
    )
    for row in rows:
        if not isinstance(row, dict) or not _has_channel_success(row):
            continue
        product_id = str(row.get("content_id") or row.get("product_id") or "")
        if not _PRODUCT_ID.fullmatch(product_id):
            continue
        stamp = _timestamp(row.get("ts") or row.get("published_at") or row.get("updated_at"))
        if stamp > 0:
            product_posts[product_id] = max(product_posts.get(product_id, 0.0), stamp)

    return sum(1 for stamp in product_posts.values() if stamp > last_editorial)


def editorial_frequency_allowed(state: dict) -> bool:
    """Allow at most one editorial post after each six confirmed product posts."""
    return products_published_since_last_editorial(state) >= PRODUCTS_PER_EDITORIAL_POST
