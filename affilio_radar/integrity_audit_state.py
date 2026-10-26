"""Shared state bridge for the independent OfferChin offer-integrity auditor.

The auditor owns its separate ledger file so it can run concurrently with publishing
without editing state.json. The publisher imports only confirmed invalidations and
per-destination removal outcomes from that ledger.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LEDGER_PATH = Path(__file__).resolve().parent / "integrity_audit_state.json"

# These facts describe the actual offer/post, not a particular destination.
RECORD_FIELDS = (
    "posted_current_price",
    "posted_original_price",
    "posted_discount_percent",
    "price_audit_status",
    "price_audit_last_checked_at",
    "price_audit_next_check_at",
    "price_audit_error",
    "price_audit_reason",
    "price_audit_invalidated_at",
    "price_audit_mismatch_fields",
    "price_audit_posted_price",
    "price_audit_live_price",
    "price_audit_posted_original_price",
    "price_audit_live_original_price",
    "last_seen_current_price",
    "last_seen_original_price",
    "last_seen_in_stock",
    "expires_at",
    "expiry_source",
    "expiry_estimated",
    "expiry_deadline_verified_directly",
    "expiry_deadline_verified_from_site_card",
    "expiry_last_direct_verification_at",
    "expiry_last_removal_check_at",
    "expiry_last_removal_check_result",
    "expiry_reason",
)

PLATFORM_SPECS = {
    "telegram": {
        "id_field": "telegram_message_id",
        "status_field": "expiry_status",
        "extra_fields": (
            "expired_deleted_at",
            "expiry_last_absent_at",
            "telegram_expiry_last_delete_error",
        ),
    },
    "bale": {
        "id_field": "bale_message_id",
        "status_field": "bale_expiry_status",
        "extra_fields": (
            "bale_expired_deleted_at",
            "bale_expiry_last_absent_at",
            "bale_expiry_last_delete_error",
        ),
    },
    "youtube": {
        "id_field": "youtube_video_id",
        "status_field": "youtube_expiry_status",
        "extra_fields": (
            "youtube_deleted_at",
            "youtube_already_absent_at",
            "youtube_expiry_next_attempt_at",
            "youtube_expiry_last_error",
            "youtube_expiry_attempts",
            "youtube_visibility",
        ),
    },
    "aparat": {
        "id_field": "aparat_video_hash",
        "status_field": "aparat_expiry_status",
        "extra_fields": (
            "aparat_deleted_at",
            "aparat_already_absent_at",
            "aparat_expiry_next_attempt_at",
            "aparat_expiry_last_error",
            "aparat_expiry_attempts",
            "aparat_visibility",
        ),
    },
}

STATE_META_FIELDS = (
    "expiry_feed_last_attempt_at",
    "expiry_feed_last_checked_at",
    "expiry_feed_last_summary",
    "price_audit_last_summary",
)


def empty_ledger() -> dict[str, Any]:
    return {"version": 1, "posts": {}, "state_meta": {}, "last_run": {}}


def load_ledger(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else LEDGER_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_ledger()
    if not isinstance(payload, dict):
        return empty_ledger()
    posts = payload.get("posts")
    payload["posts"] = posts if isinstance(posts, dict) else {}
    meta = payload.get("state_meta")
    payload["state_meta"] = meta if isinstance(meta, dict) else {}
    payload.setdefault("version", 1)
    payload.setdefault("last_run", {})
    return payload


def save_ledger(ledger: dict[str, Any], path: str | Path | None = None) -> None:
    target = Path(path) if path is not None else LEDGER_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


def post_key(platform: str, post_id: object) -> str:
    return f"{platform}:{str(post_id or '').strip()}"


def _record_refs(published: dict[str, Any]):
    """Yield each active/current record and each historic post record separately."""
    for product_id, record in published.items():
        if not isinstance(record, dict):
            continue
        yield str(product_id), record
        history = record.get("post_history")
        if isinstance(history, list):
            for old in history:
                if isinstance(old, dict):
                    yield str(product_id), old


def _same_post(entry: dict[str, Any], product_id: str, post_id: str) -> bool:
    return (
        str(entry.get("product_id") or "").lower() == str(product_id or "").lower()
        and str(entry.get("post_id") or "").strip() == str(post_id or "").strip()
    )


def apply_integrity_audit_ledger(
    state: dict[str, Any],
    ledger: dict[str, Any] | None = None,
    *,
    include_audit_cadence: bool = False,
) -> bool:
    """Merge exact-post audit results; optionally restore cadence for the audit worker.

    The publisher imports only confirmed invalidations and per-platform removal
    outcomes. The independent audit worker also restores match/unconfirmed timestamps,
    retry times, and refreshed live-offer facts from the same ledger, without writing
    those routine timestamps into the publisher's shared state.json.
    """
    snapshot = ledger if isinstance(ledger, dict) else load_ledger()
    posts = snapshot.get("posts")
    if not isinstance(posts, dict):
        return False
    published = state.get("published")
    if not isinstance(published, dict):
        return False

    changed = False
    terminal = {"deleted", "already_absent"}
    for product_id, record in _record_refs(published):
        for platform, spec in PLATFORM_SPECS.items():
            raw_id = record.get(spec["id_field"])
            if platform in {"telegram", "bale"}:
                if not str(raw_id or "").isdigit():
                    continue
            elif not str(raw_id or "").strip():
                continue
            post_id = str(raw_id).strip()
            entry = posts.get(post_key(platform, post_id))
            if not isinstance(entry, dict) or not _same_post(entry, product_id, post_id):
                continue

            # Routine audit fields are restored only inside the independent monitor.
            # The publisher imports these facts only when a mismatch was confirmed.
            if entry.get("price_audit_status") == "invalidated" or include_audit_cadence:
                fields = entry.get("record_fields")
                fields = fields if isinstance(fields, dict) else {}
                for field in RECORD_FIELDS:
                    desired = fields.get(field)
                    if desired is None:
                        if field in record:
                            record.pop(field, None)
                            changed = True
                    elif record.get(field) != desired:
                        record[field] = desired
                        changed = True

            desired_status = entry.get("platform_status")
            status_field = spec["status_field"]
            if desired_status not in (None, "") and record.get(status_field) != desired_status:
                # Import confirmed terminal results and failures/retry states. A platform
                # deletion failure must stay visible to the next cleanup attempt.
                if desired_status in terminal or desired_status in {
                    "delete_failed", "delete_retry", "pending_credentials",
                    "expired_confirmed", "expired_marked", "deadline_unavailable_delete_failed",
                    "deadline_unavailable_marked", "unknown", "tracked", "tracked_estimated",
                }:
                    record[status_field] = desired_status
                    changed = True

            extra_fields = entry.get("platform_fields")
            extra_fields = extra_fields if isinstance(extra_fields, dict) else {}
            for field in spec["extra_fields"]:
                desired = extra_fields.get(field)
                if desired is None:
                    if field in record and field not in {
                        "youtube_visibility", "aparat_visibility",
                    }:
                        record.pop(field, None)
                        changed = True
                elif record.get(field) != desired:
                    record[field] = desired
                    changed = True

    return changed


def capture_integrity_audit_ledger(
    state: dict[str, Any],
    ledger: dict[str, Any] | None = None,
    *,
    now_iso: str,
    keep_posts: int = 2000,
) -> dict[str, Any]:
    """Capture price-audit facts and per-platform deletion outcomes by exact post ID."""
    snapshot = ledger if isinstance(ledger, dict) else empty_ledger()
    posts = snapshot.get("posts")
    if not isinstance(posts, dict):
        posts = {}
        snapshot["posts"] = posts
    published = state.get("published")
    if not isinstance(published, dict):
        published = {}

    for product_id, record in _record_refs(published):
        for platform, spec in PLATFORM_SPECS.items():
            raw_id = record.get(spec["id_field"])
            if platform in {"telegram", "bale"}:
                if not str(raw_id or "").isdigit():
                    continue
            elif not str(raw_id or "").strip():
                continue
            post_id = str(raw_id).strip()
            entry = {
                "product_id": str(product_id).lower(),
                "platform": platform,
                "post_id": post_id,
                "updated_at": now_iso,
                "price_audit_status": str(record.get("price_audit_status") or ""),
                "record_fields": {
                    field: record.get(field)
                    for field in RECORD_FIELDS
                },
                "platform_status": record.get(spec["status_field"]),
                "platform_fields": {
                    field: record.get(field)
                    for field in spec["extra_fields"]
                },
            }
            posts[post_key(platform, post_id)] = entry

    snapshot["version"] = 1
    snapshot["state_meta"] = {
        field: state[field]
        for field in STATE_META_FIELDS
        if field in state
    }
    # The ledger retains recent outcomes beyond the active state window, but remains bounded.
    if len(posts) > max(100, int(keep_posts)):
        ordered = sorted(
            posts.items(),
            key=lambda item: str((item[1] or {}).get("updated_at") or ""),
        )
        snapshot["posts"] = dict(ordered[-max(100, int(keep_posts)):])
    return snapshot
