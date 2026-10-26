"""Independent audit-state overlay for OfferChin's non-blocking trust monitor.

The monitor writes this small ledger instead of the shared publication state.json.
Records are associated by exact platform post/video IDs, so concurrent publishing
can continue without competing for the same Git-tracked state file.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_PATH = Path(__file__).resolve().parent / "price_audit_state.json"
TERMINAL_STATUSES = {"deleted", "already_absent"}
PLATFORM_IDS = (
    ("telegram", "telegram_message_id"),
    ("bale", "bale_message_id"),
    ("youtube", "youtube_video_id"),
    ("aparat", "aparat_video_hash"),
)
EXACT_PATCH_FIELDS = {
    "title", "product_url", "ts",
    "posted_current_price", "posted_original_price", "posted_discount_percent",
    "expires_at", "expiry_source", "expiry_estimated",
    "expiry_deadline_verified_directly", "expiry_deadline_verified_from_site_card",
    "expiry_last_direct_verification_at", "expiry_last_live_sync_at",
    "expiry_last_site_card_sync_at", "expiry_last_removal_check_at",
    "expiry_last_removal_check_result", "expiry_reason",
    "expiry_status", "bale_expiry_status", "youtube_expiry_status", "aparat_expiry_status",
    "expiry_last_probed_at", "expiry_last_product_check_at",
    "last_seen_current_price", "last_seen_original_price", "last_seen_in_stock",
    "expired_deleted_at", "bale_expired_deleted_at", "youtube_deleted_at",
    "aparat_deleted_at", "youtube_already_absent_at", "aparat_already_absent_at",
    "youtube_visibility", "aparat_visibility",
    "telegram_title_quality_delete_error", "bale_title_quality_delete_error",
    "title_quality_status", "title_quality_checked_at",
}
PATCH_PREFIXES = (
    "price_audit_", "expiry_", "bale_expiry_", "telegram_expiry_",
    "youtube_expiry_", "aparat_expiry_", "title_quality_",
)


def _is_patch_field(key: str) -> bool:
    return key in EXACT_PATCH_FIELDS or key.startswith(PATCH_PREFIXES)


def _read_ledger(path: Path | None = None) -> dict:
    target = path or LEDGER_PATH
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "posts": {}}
    if not isinstance(value, dict) or not isinstance(value.get("posts"), dict):
        return {"version": 1, "posts": {}}
    value.setdefault("version", 1)
    return value


def _id_value(record: dict, platform: str) -> str:
    field = dict(PLATFORM_IDS)[platform]
    raw = str(record.get(field) or "").strip()
    if platform in {"telegram", "bale"}:
        return raw if raw.isdigit() else ""
    return raw


def _identities(product_id: str, record: dict) -> list[str]:
    values = []
    for platform, field in PLATFORM_IDS:
        raw = str(record.get(field) or "").strip()
        if not raw or (platform in {"telegram", "bale"} and not raw.isdigit()):
            continue
        values.append(f"{platform}:{raw}")
    return values


def _record_key(product_id: str, record: dict) -> str:
    ids = sorted(_identities(product_id, record))
    return str(product_id) + "|" + "|".join(ids)


def _minimal_snapshot(record: dict) -> dict:
    keep = EXACT_PATCH_FIELDS | {
        "telegram_message_id", "bale_message_id", "youtube_video_id",
        "youtube_video_url", "aparat_video_hash", "aparat_video_url",
        "price_audit_status", "price_audit_reason", "price_audit_mismatch_fields",
        "price_audit_posted_price", "price_audit_live_price",
        "price_audit_posted_original_price", "price_audit_live_original_price",
    }
    return {
        key: deepcopy(value)
        for key, value in record.items()
        if key in keep and key != "post_history"
    }


def _iter_records(state: dict):
    published = state.get("published")
    if not isinstance(published, dict):
        return
    for product_id, record in published.items():
        if not isinstance(record, dict):
            continue
        yield str(product_id), record
        history = record.get("post_history")
        if isinstance(history, list):
            for previous in history:
                if isinstance(previous, dict):
                    yield str(product_id), previous


def _record_index(state: dict) -> dict[str, tuple[str, dict]]:
    result = {}
    for product_id, record in _iter_records(state):
        for identity in _identities(product_id, record):
            result[identity] = (product_id, record)
    return result


def _apply_patch(record: dict, patch: dict) -> None:
    for key, value in patch.items():
        if not _is_patch_field(key):
            continue
        if isinstance(value, dict) and value == {"$remove": True}:
            record.pop(key, None)
        else:
            record[key] = deepcopy(value)


def _merge_snapshot_group(entries: list[tuple[str, dict]]) -> tuple[str, dict, set[str]]:
    entries = sorted(entries, key=lambda item: item[0])
    base = next((item.get("snapshot") for _identity, item in entries if isinstance(item.get("snapshot"), dict)), {})
    record = deepcopy(base)
    product_id = str(next((item.get("product_id") for _identity, item in entries if item.get("product_id")), ""))
    ids: set[str] = set()
    for identity, item in entries:
        ids.add(identity)
        snapshot = item.get("snapshot")
        if isinstance(snapshot, dict):
            for key, value in snapshot.items():
                record.setdefault(key, deepcopy(value))
        patch = item.get("patch")
        if isinstance(patch, dict):
            _apply_patch(record, patch)
    return product_id, record, ids


def apply_audit_ledger(state: dict, path: Path | None = None) -> dict:
    """Overlay audit fields by exact post ID and restore ledger-only orphan records."""
    if not isinstance(state, dict):
        return {}
    ledger = _read_ledger(path)
    posts = ledger.get("posts", {})
    if not posts:
        return state

    published = state.setdefault("published", {})
    if not isinstance(published, dict):
        published = {}
        state["published"] = published

    # First apply patches to post records that still exist in the shared publication state.
    base_index = _record_index(state)
    for identity, found in base_index.items():
        item = posts.get(identity)
        if not isinstance(item, dict):
            continue
        patch = item.get("patch")
        if isinstance(patch, dict):
            _apply_patch(found[1], patch)

    # An audit may discover a previously untracked public Telegram post. Preserve
    # that record in the separate ledger, without writing state.json from the monitor.
    orphan_entries = [
        (identity, item)
        for identity, item in posts.items()
        if identity not in base_index and isinstance(item, dict) and isinstance(item.get("snapshot"), dict)
    ]
    unused = dict(orphan_entries)
    groups: list[list[tuple[str, dict]]] = []
    while unused:
        identity, item = next(iter(unused.items()))
        unused.pop(identity)
        group = [(identity, item)]
        known_ids = set(_identities(str(item.get("product_id") or ""), item.get("snapshot") or {})) | {identity}
        grew = True
        while grew:
            grew = False
            for other_identity, other in list(unused.items()):
                other_snapshot = other.get("snapshot") if isinstance(other, dict) else None
                other_ids = set(_identities(str(other.get("product_id") or ""), other_snapshot or {})) | {other_identity}
                if known_ids & other_ids:
                    group.append((other_identity, other))
                    unused.pop(other_identity)
                    known_ids.update(other_ids)
                    grew = True
        groups.append(group)

    for group in groups:
        product_id, snapshot, group_ids = _merge_snapshot_group(group)
        if not product_id or not _identities(product_id, snapshot):
            continue

        # If any ID in this ledger snapshot matches a current/history record, merge
        # the missing destination IDs into that record instead of creating a duplicate.
        refreshed_index = _record_index(state)
        matches = [refreshed_index[identity] for identity in group_ids if identity in refreshed_index]
        target_record = matches[0][1] if matches else None
        if target_record is not None:
            for _pid, match_record in matches[1:]:
                if match_record is target_record:
                    continue
                for platform, field in PLATFORM_IDS:
                    if not target_record.get(field) and match_record.get(field):
                        target_record[field] = match_record[field]
            for platform, field in PLATFORM_IDS:
                if not target_record.get(field) and snapshot.get(field):
                    target_record[field] = snapshot[field]
            for _identity, item in group:
                patch = item.get("patch")
                if isinstance(patch, dict):
                    _apply_patch(target_record, patch)
            continue

        current = published.get(product_id)
        if not isinstance(current, dict):
            published[product_id] = snapshot
            continue
        history = current.setdefault("post_history", [])
        if not isinstance(history, list):
            history = []
            current["post_history"] = history
        if not any(
            set(_identities(product_id, old)) & group_ids
            for old in history if isinstance(old, dict)
        ):
            history.append(snapshot)
            current["post_history"] = history[-120:]
    return state


def write_audit_ledger(
    state: dict,
    baseline: dict | None,
    path: Path | None = None,
    *,
    max_terminal_entries: int = 5000,
) -> None:
    """Persist only audit-related deltas; never writes the shared state.json."""
    target = path or LEDGER_PATH
    ledger = _read_ledger(target)
    posts = ledger.setdefault("posts", {})
    current_index = _record_index(state)
    baseline_index = _record_index(baseline or {})
    now_text = datetime.now(timezone.utc).isoformat()

    for identity, (product_id, record) in current_index.items():
        before_tuple = baseline_index.get(identity)
        before = before_tuple[1] if before_tuple else None
        existing = posts.get(identity)
        existing = deepcopy(existing) if isinstance(existing, dict) else {
            "product_id": product_id, "platform_id": identity, "patch": {}
        }
        patch = existing.get("patch")
        patch = deepcopy(patch) if isinstance(patch, dict) else {}

        if before is None:
            for key, value in record.items():
                if _is_patch_field(key):
                    patch[key] = deepcopy(value)
            existing["snapshot"] = _minimal_snapshot(record)
            existing["record_key"] = _record_key(product_id, record)
        else:
            keys = {
                key for key in set(record) | set(before)
                if _is_patch_field(key)
            }
            for key in keys:
                in_current = key in record
                in_before = key in before
                if in_current == in_before and (not in_current or record.get(key) == before.get(key)):
                    continue
                patch[key] = deepcopy(record[key]) if in_current else {"$remove": True}

        # Keep old deltas unless this record explicitly superseded those fields.
        if patch or existing.get("snapshot"):
            existing.update({
                "product_id": product_id,
                "platform_id": identity,
                "patch": patch,
                "updated_at": now_text,
            })
            posts[identity] = existing

    # Never prune an unresolved post; cap only old terminal history in this sidecar.
    active_ids = set()
    for _product_id, record in _iter_records(state):
        for platform, field in PLATFORM_IDS:
            raw_id = str(record.get(field) or "").strip()
            if not raw_id or (platform in {"telegram", "bale"} and not raw_id.isdigit()):
                continue
            status_field = {
                "telegram": "expiry_status",
                "bale": "bale_expiry_status",
                "youtube": "youtube_expiry_status",
                "aparat": "aparat_expiry_status",
            }[platform]
            if record.get(status_field) not in TERMINAL_STATUSES:
                active_ids.add(f"{platform}:{raw_id}")
    recent = sorted(
        posts.items(),
        key=lambda pair: str(pair[1].get("updated_at") or ""),
        reverse=True,
    )
    keep = set(active_ids)
    keep.update(identity for identity, _item in recent[:max(0, int(max_terminal_entries))])
    ledger["version"] = 1
    ledger["updated_at"] = now_text
    ledger["posts"] = {identity: item for identity, item in posts.items() if identity in keep}

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, target)
