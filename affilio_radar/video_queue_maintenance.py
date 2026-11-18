#!/usr/bin/env python3
"""Reconcile stale and credential-blocked OfferChin video queue entries.

Public uploads are allowed only while the product hand-off is fresh. Old pending
entries are moved to a terminal status (their published product record is retained)
so they cannot block newer editorial videos. A recent credential-blocked item is
requeued only when its own destination credentials and all offer-eligibility gates
are currently valid.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from typing import Any

import affilio_radar as radar

DESTINATIONS = ("youtube", "aparat", "filo")
ACTIVE_STATUSES = {
    "pending",
    "pending_credentials",
    "retry",
    "failed",
    "skipped_unverified_deadline",
}


def _utc(value: Any) -> datetime | None:
    try:
        if isinstance(value, (int, float)):
            stamp = float(value)
            return datetime.fromtimestamp(stamp, timezone.utc) if stamp > 0 else None
        text = str(value or "").strip()
        if not text:
            return None
        try:
            stamp = float(text)
            return datetime.fromtimestamp(stamp, timezone.utc) if stamp > 0 else None
        except (TypeError, ValueError, OverflowError):
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def destination_credentials_ready(destination: str, state: dict, now: datetime) -> bool:
    """Check destination credentials without exposing or logging their values."""
    if destination == "youtube":
        try:
            from short_video import youtube_credentials_available
            return bool(youtube_credentials_available())
        except Exception:
            return False

    if destination == "aparat":
        try:
            import aparat_uploader
            return bool(radar.APARAT_UPLOAD_ENABLED and aparat_uploader.aparat_credentials_available())
        except Exception:
            return False

    if destination == "filo":
        try:
            import filo_uploader
            return bool(
                filo_uploader.filo_credentials_available()
                and radar._filo_login_verified(state, now)
            )
        except Exception:
            return False

    return False


def maintain_video_queue_state(
    state: dict,
    destination: str,
    *,
    now: datetime | None = None,
    max_age_hours: int = 24,
    credentials_ready: bool = False,
) -> dict:
    """Move stale work out of one destination queue and safely recover recent auth skips.

    This function is deterministic and performs no network publishing. Offer expiry
    and canonical hand-off checks are delegated to the existing video eligibility gate.
    """
    platform = str(destination or "").strip().lower()
    if platform not in DESTINATIONS:
        raise ValueError("unsupported_video_destination")
    if not isinstance(state, dict):
        raise ValueError("state_must_be_object")
    try:
        freshness_hours = max(1, min(72, int(max_age_hours)))
    except (TypeError, ValueError, OverflowError):
        freshness_hours = 24

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    published = state.get("published")
    if not isinstance(published, dict):
        return {
            "destination": platform,
            "stale": 0,
            "requeued": 0,
            "untouched": 0,
            "pending_after": 0,
        }

    status_key = f"{platform}_upload_status"
    next_key = f"{platform}_next_attempt_at"
    reason_key = f"{platform}_skip_reason"
    recorded_key = f"{platform}_skip_recorded_at"
    stale = 0
    requeued = 0
    untouched = 0
    pending_after = 0
    cutoff_seconds = freshness_hours * 3600

    for product_id, record in published.items():
        if not isinstance(record, dict) or not radar._has_video_dispatch_eligibility(record):
            untouched += 1
            continue

        status = str(record.get(status_key) or "").strip().lower()
        record_time = _utc(record.get("ts"))
        age_seconds = (current - record_time).total_seconds() if record_time else None
        too_old = record_time is None or age_seconds is None or age_seconds < 0 or age_seconds > cutoff_seconds

        # Keep confirmed uploads and external submissions untouched. In particular,
        # Filo "submitted" states are not safe to retry because acceptance may already
        # have occurred even when public visibility has not yet been confirmed.
        if status in {"uploaded", "published", "submitted_pending_approval", "submitted_unconfirmed",
                      "rejected_by_filo", "manual_review", "not_connected", "skipped_after_retries",
                      "skipped_generation_failed", "skipped_expiring_soon", "skipped_offer_expired",
                      "skipped_stale_after_freshness_window"}:
            untouched += 1
            continue

        if too_old:
            actionable = status in ACTIVE_STATUSES or status == "skipped_unavailable"
            if actionable:
                reason = "publication_timestamp_missing" if record_time is None else "selection_outside_freshness_window"
                record[status_key] = "skipped_stale_after_freshness_window"
                record[reason_key] = reason
                record[recorded_key] = current.isoformat()
                record.pop(next_key, None)
                stale += 1
            else:
                untouched += 1
            continue

        if status == "skipped_unavailable" and credentials_ready:
            # Reuse the production eligibility helper so an expired deal, invalid
            # generation state, or missing canonical hand-off is never reactivated.
            candidate = dict(record)
            candidate[status_key] = "pending"
            if radar._has_pending_video_destination(candidate, {platform}, now=current):
                record[status_key] = "pending"
                record.pop(reason_key, None)
                record.pop(recorded_key, None)
                record.pop(next_key, None)
                requeued += 1
            else:
                untouched += 1
            continue

        # An unexpired retry/skip still obeys the destination's persisted retry time.
        if status in ACTIVE_STATUSES:
            pending_after += 1
        else:
            untouched += 1

    return {
        "destination": platform,
        "max_age_hours": freshness_hours,
        "stale": stale,
        "requeued": requeued,
        "untouched": untouched,
        "pending_after": pending_after,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", choices=DESTINATIONS, required=True)
    parser.add_argument("--max-age-hours", type=int, default=24)
    args = parser.parse_args()

    state = radar.load_state()
    now = datetime.now(timezone.utc)
    ready = destination_credentials_ready(args.destination, state, now)
    result = maintain_video_queue_state(
        state,
        args.destination,
        now=now,
        max_age_hours=args.max_age_hours,
        credentials_ready=ready,
    )
    if result["stale"] or result["requeued"]:
        radar.save_json(radar.STATE, state)
        projection = radar.build_video_upload_dispatch_state(state, now=now)
        radar.save_json(radar.VIDEO_DISPATCH_STATE, projection)
    print(
        "VIDEO_QUEUE_MAINTENANCE "
        f"destination={result['destination']} credentials_ready={str(ready).lower()} "
        f"max_age_hours={result['max_age_hours']} stale={result['stale']} "
        f"requeued={result['requeued']} untouched={result['untouched']} "
        f"pending_after={result['pending_after']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
