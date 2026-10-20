#!/usr/bin/env python3
"""Withdraw recent regular-feed Aparat uploads while the Shorts-only route is unavailable.

A vertical MP4 uploaded through the generic website endpoint is not guaranteed to enter
Aparat Shorts. This script does not invent a Shorts flag; it privately unshares recent
regular uploads and records them for manual/verified Shorts migration without re-uploading
or resurrecting offers whose deadlines have passed.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from aparat_uploader import aparat_credentials_available, set_aparat_video_private

STATE_PATH = Path(__file__).with_name("state.json")
DEFAULT_CUTOFF_UTC = "2026-10-19T22:00:00+00:00"


def parse_utc(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _mark_withdrawn(record: dict, now: datetime) -> None:
    deadline = parse_utc(record.get("expires_at"))
    expired = deadline is None or deadline <= now
    record["aparat_visibility"] = "private_waiting_for_shorts"
    record["aparat_shorts_migration_status"] = (
        "withdrawn_expired_or_unverified_offer"
        if expired
        else "withdrawn_waiting_for_shorts_upload"
    )
    record["aparat_shorts_migration_at"] = now.isoformat()
    record.pop("aparat_shorts_migration_next_attempt_at", None)
    record.pop("aparat_shorts_migration_last_error", None)


def migrate_recent_regular_uploads(
    published: dict,
    *,
    private_video: Callable[[str], bool],
    now: datetime,
    cutoff: datetime,
    max_items: int = 30,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict:
    """Privately unshare recent public regular-feed uploads, with retry metadata."""
    counts = {"eligible": 0, "hidden": 0, "already_private": 0, "retry": 0, "changed": False}
    candidates = []
    for product_id, record in published.items():
        if not isinstance(record, dict):
            continue
        if record.get("aparat_shorts_migration_status") in {
            "withdrawn_expired_or_unverified_offer",
            "withdrawn_waiting_for_shorts_upload",
        }:
            continue
        if str(record.get("aparat_upload_status") or "") != "uploaded":
            continue
        uploaded_at = parse_utc(record.get("aparat_uploaded_at"))
        video_hash = str(record.get("aparat_video_hash") or "").strip()
        if not uploaded_at or uploaded_at < cutoff or not video_hash:
            continue
        visibility = str(record.get("aparat_visibility") or "").strip().lower()
        if visibility not in {"public", "unknown"}:
            continue
        retry_at = parse_utc(record.get("aparat_shorts_migration_next_attempt_at"))
        if retry_at and now < retry_at:
            continue
        candidates.append((uploaded_at, str(product_id), record, video_hash))

    candidates.sort(key=lambda item: (item[0], item[1]))
    counts["eligible"] = len(candidates)
    limit = max(1, min(100, int(max_items)))
    for index, (_, product_id, record, video_hash) in enumerate(candidates[:limit]):
        # If expiry monitoring already made the video private, update our tracking without
        # issuing another edit request.
        if str(record.get("aparat_expiry_status") or "").lower() in {"private", "already_private"}:
            _mark_withdrawn(record, now)
            counts["already_private"] += 1
            counts["changed"] = True
            continue
        try:
            ok = private_video(video_hash)
            if ok is False:
                raise RuntimeError("Aparat did not confirm that the video was made private")
            _mark_withdrawn(record, now)
            counts["hidden"] += 1
            counts["changed"] = True
            print(f"APARAT_SHORTS_MIGRATION_HIDDEN product_id={product_id}")
        except Exception as exc:
            attempts = int(record.get("aparat_shorts_migration_attempts", 0) or 0) + 1
            record["aparat_shorts_migration_attempts"] = attempts
            record["aparat_shorts_migration_status"] = "retry"
            record["aparat_shorts_migration_last_error"] = type(exc).__name__
            record["aparat_shorts_migration_next_attempt_at"] = (
                now + timedelta(minutes=min(60, 5 * (2 ** min(attempts - 1, 3))))
            ).isoformat()
            counts["retry"] += 1
            counts["changed"] = True
            print(f"APARAT_SHORTS_MIGRATION_RETRY product_id={product_id} error={type(exc).__name__}")
        if index < min(len(candidates), limit) - 1:
            sleep_fn(0.8)

    return counts


def main() -> int:
    if not aparat_credentials_available():
        print("APARAT_SHORTS_MIGRATION_SKIPPED reason=missing_aparat_session")
        return 0

    cutoff = parse_utc(os.getenv("APARAT_SHORTS_MIGRATION_CUTOFF_UTC", DEFAULT_CUTOFF_UTC))
    if cutoff is None:
        print("APARAT_SHORTS_MIGRATION_SKIPPED reason=invalid_cutoff")
        return 0
    try:
        max_items = max(1, min(100, int(os.getenv("APARAT_SHORTS_MIGRATION_MAX_PER_RUN", "30"))))
    except (TypeError, ValueError, OverflowError):
        max_items = 30

    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"APARAT_SHORTS_MIGRATION_SKIPPED reason=state_read_failed error={type(exc).__name__}")
        return 0
    published = state.get("published") if isinstance(state, dict) else None
    if not isinstance(published, dict):
        print("APARAT_SHORTS_MIGRATION_SKIPPED reason=published_state_invalid")
        return 0

    counts = migrate_recent_regular_uploads(
        published,
        private_video=set_aparat_video_private,
        now=datetime.now(timezone.utc),
        cutoff=cutoff,
        max_items=max_items,
    )
    if counts["changed"]:
        temp = STATE_PATH.with_suffix(".json.tmp")
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(STATE_PATH)
    print(
        "APARAT_SHORTS_MIGRATION_SUMMARY "
        f"eligible={counts['eligible']} hidden={counts['hidden']} "
        f"already_private={counts['already_private']} retry={counts['retry']} "
        f"limit={max_items}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
