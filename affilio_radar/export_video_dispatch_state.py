#!/usr/bin/env python3
"""Export a tiny, deterministic video-dispatch snapshot from the full OfferChin state.

The Cloudflare minute dispatcher must never download the multi-megabyte state.json.
This sidecar contains only the next-upload clocks and the newest six published
records needed to decide whether YouTube or Aparat has eligible video work.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "state.json"
DESTINATION = ROOT / "video_dispatch_state.json"
SCHEMA_VERSION = 1
PUBLISHED_LIMIT = 6

ROOT_FIELDS = (
    "youtube_next_upload_at",
    "youtube_uploads_paused_until",
    "aparat_next_upload_at",
)
POST_FIELDS = (
    "ts",
    "delivery_status",
    "telegram_message_id",
    "bale_message_id",
    "expires_at",
    "youtube_upload_status",
    "youtube_next_attempt_at",
    "aparat_upload_status",
    "aparat_next_attempt_at",
    "video_generation_status",
    "video_generation_next_attempt_at",
    "expiry_deadline_verified_directly",
    "expiry_source",
    "expiry_deadline_verified_from_site_card",
)


def _timestamp(record: dict[str, Any]) -> float:
    try:
        value = float(record.get("ts") or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return value if math.isfinite(value) and value > 0 else 0.0


def build_dispatch_state(state: dict[str, Any]) -> dict[str, Any]:
    """Build the compact snapshot without mutating the full persistent state."""
    if not isinstance(state, dict):
        raise ValueError("OfferChin state root must be a JSON object")

    published = state.get("published")
    if not isinstance(published, dict):
        published = {}

    candidates = [
        (str(product_id), record)
        for product_id, record in published.items()
        if isinstance(record, dict)
    ]
    candidates.sort(key=lambda row: _timestamp(row[1]), reverse=True)

    compact_posts: dict[str, dict[str, Any]] = {}
    for product_id, record in candidates[:PUBLISHED_LIMIT]:
        compact = {}
        for field in POST_FIELDS:
            if field not in record:
                continue
            value = record[field]
            if field == "delivery_status" and isinstance(value, dict):
                value = {
                    key: status for key, status in value.items()
                    if key in {"telegram", "bale"}
                }
            if isinstance(value, (str, int, float, bool)) or value is None or isinstance(value, dict):
                compact[field] = value
        compact_posts[product_id] = compact

    result: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "published": compact_posts,
    }
    for field in ROOT_FIELDS:
        value = state.get(field)
        if isinstance(value, (str, int, float, bool)) or value is None:
            if field in state:
                result[field] = value
    return result


def export_dispatch_state(source: Path = SOURCE, destination: Path = DESTINATION) -> dict[str, Any]:
    """Validate input and atomically replace the sidecar only after a complete parse."""
    try:
        state = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot_read_valid_state_json:{type(exc).__name__}") from exc

    compact = build_dispatch_state(state)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(compact, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return compact


if __name__ == "__main__":
    snapshot = export_dispatch_state()
    size = DESTINATION.stat().st_size
    print(
        "OFFERCHIN_VIDEO_DISPATCH_STATE_EXPORTED "
        f"products={len(snapshot['published'])} bytes={size} schema={SCHEMA_VERSION}"
    )
