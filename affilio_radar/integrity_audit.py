#!/usr/bin/env python3
"""Independent OfferChin offer-integrity audit.

This process verifies only source-backed live facts and runs outside the publisher
workflow. It reads state.json but never writes it; its independent ledger stores
audit cadence and per-destination deletion outcomes so auditing cannot contend with
the publisher's state commit or hold up the next publication slot.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import expiration_monitor as monitor
from integrity_audit_state import (
    LEDGER_PATH,
    apply_integrity_audit_ledger,
    capture_integrity_audit_ledger,
    empty_ledger,
    load_ledger,
    save_ledger,
)

ROOT = Path(__file__).resolve().parent


def _integer_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError, OverflowError):
        value = default
    return max(minimum, min(maximum, value))


def run() -> int:
    now = datetime.now(timezone.utc)
    state = monitor._read_state()
    published = state.get("published", {})
    if not isinstance(published, dict):
        raise ValueError("state.json published must be an object")

    ledger = load_ledger()
    state_meta = ledger.get("state_meta")
    if isinstance(state_meta, dict):
        # These cadence markers belong to the audit lane, not the publisher's state.
        for key, value in state_meta.items():
            if key in {
                "expiry_feed_last_attempt_at",
                "expiry_feed_last_checked_at",
                "expiry_feed_last_summary",
                "price_audit_last_summary",
            }:
                state[key] = value
    apply_integrity_audit_ledger(state, ledger, include_audit_cadence=True)

    def checkpoint(phase: str, **metadata) -> None:
        """Durably checkpoint audit facts and deletion outcomes without touching state.json."""
        nonlocal ledger
        checked_at = datetime.now(timezone.utc).isoformat()
        ledger = capture_integrity_audit_ledger(
            state,
            ledger,
            now_iso=checked_at,
        )
        last_run = dict(ledger.get("last_run") or {})
        last_run.update(metadata)
        last_run.update({
            "checked_at": checked_at,
            "phase": phase,
            "publisher_state_write": False,
            "ledger_path": LEDGER_PATH.name,
        })
        ledger["last_run"] = last_run
        save_ledger(ledger)

    sync_changed = False
    try:
        sync_changed = monitor._sync_live_deadline_feed(state, published, now)
    except Exception as exc:
        # Feed/deadline refresh is only one audit source. A feed failure must not
        # prevent the direct price/stock audit or retries for already-invalid posts.
        print(f"INTEGRITY_DEADLINE_SYNC_FAILED error={type(exc).__name__} detail={str(exc)[:140]!r}")

    batch_size = _integer_env("AFFILIO_PRICE_AUDIT_BATCH_SIZE", 8, 1, 30)
    audit_interval = _integer_env("AFFILIO_PRICE_AUDIT_INTERVAL_SECONDS", 60, 60, 21600)
    retry_seconds = _integer_env("AFFILIO_PRICE_AUDIT_RETRY_SECONDS", 300, 60, 3600)
    try:
        changed, summary = monitor._audit_live_prices(
            published,
            now=now,
            batch_size=batch_size,
            interval_seconds=audit_interval,
            retry_seconds=retry_seconds,
        )
    except Exception as exc:
        changed = False
        summary = {
            "products_due": 0,
            "products_checked": 0,
            "price_mismatches": 0,
            "out_of_stock_posts": 0,
            "unconfirmed": 1,
            "remaining_due": 0,
            "error": f"{type(exc).__name__}: {str(exc)[:160]}",
        }
        print(f"INTEGRITY_PRICE_AUDIT_FAILED error={type(exc).__name__} detail={str(exc)[:180]!r}")

    # Use one shared bounded lookup budget across cleanup adapters. Removals are best effort per post
    # and persisted to this lane's ledger; a failure is retried on a later audit run.
    # Checkpoint confirmed mismatches before any destructive network operations.
    # If a later platform call times out, the next run still knows what must be removed.
    checkpoint(
        "price_audit_complete",
        batch_size=batch_size,
        interval_seconds=audit_interval,
        retry_seconds=retry_seconds,
        products_due=int(summary.get("products_due") or 0),
        products_checked=int(summary.get("products_checked") or 0),
        price_mismatches=int(summary.get("price_mismatches") or 0),
        out_of_stock_posts=int(summary.get("out_of_stock_posts") or 0),
        unconfirmed=int(summary.get("unconfirmed") or 0),
        deadline_sync_changed=bool(sync_changed),
    )

    # Give every destination its own bounded source-confirmation budget. This keeps
    # channel cleanup from starving video cleanup, while each request is time-bounded.
    direct_limit = _integer_env("AFFILIO_DIRECT_PRODUCT_DETAIL_CHECK_LIMIT", 1, 1, 10)
    channel_budget = {"remaining": direct_limit}

    def confirm_channel(product_id, record, current_time):
        return monitor._confirm_expiry_for_deletion(
            product_id, record, current_time, budget=channel_budget
        )

    try:
        channel_changed, channel_deleted = monitor._delete_expired_posts(
            published,
            datetime.now(timezone.utc),
            mark_unknown=True,
            direct_confirm=confirm_channel,
        )
    except Exception as exc:
        channel_changed, channel_deleted = False, 0
        print(f"INTEGRITY_CHANNEL_CLEANUP_FAILED error={type(exc).__name__} detail={str(exc)[:150]!r}")

    checkpoint(
        "channel_cleanup_complete",
        channel_cleanup_changed=bool(channel_changed),
        channel_deleted=int(channel_deleted or 0),
    )

    youtube_budget = {"remaining": direct_limit}

    def confirm_youtube(product_id, record, current_time):
        return monitor._confirm_expiry_for_deletion(
            product_id, record, current_time, budget=youtube_budget
        )

    try:
        youtube_changed = monitor._delete_expired_youtube_videos(
            published, datetime.now(timezone.utc), direct_confirm=confirm_youtube
        )
    except Exception as exc:
        youtube_changed = False
        print(f"INTEGRITY_YOUTUBE_CLEANUP_FAILED error={type(exc).__name__} detail={str(exc)[:150]!r}")

    checkpoint(
        "youtube_cleanup_complete",
        youtube_cleanup_changed=bool(youtube_changed),
    )

    aparat_budget = {"remaining": direct_limit}

    def confirm_aparat(product_id, record, current_time):
        return monitor._confirm_expiry_for_deletion(
            product_id, record, current_time, budget=aparat_budget
        )

    try:
        aparat_changed = monitor._delete_expired_aparat_videos(
            published, datetime.now(timezone.utc), direct_confirm=confirm_aparat
        )
    except Exception as exc:
        aparat_changed = False
        print(f"INTEGRITY_APARAT_CLEANUP_FAILED error={type(exc).__name__} detail={str(exc)[:150]!r}")

    checkpoint(
        "aparat_cleanup_complete",
        aparat_cleanup_changed=bool(aparat_changed),
    )

    completed_at = datetime.now(timezone.utc).isoformat()
    ledger = capture_integrity_audit_ledger(
        state,
        ledger,
        now_iso=completed_at,
    )
    ledger["last_run"] = {
        "checked_at": completed_at,
        "batch_size": batch_size,
        "interval_seconds": audit_interval,
        "retry_seconds": retry_seconds,
        "products_due": int(summary.get("products_due") or 0),
        "products_checked": int(summary.get("products_checked") or 0),
        "price_mismatches": int(summary.get("price_mismatches") or 0),
        "out_of_stock_posts": int(summary.get("out_of_stock_posts") or 0),
        "unconfirmed": int(summary.get("unconfirmed") or 0),
        "deadline_sync_changed": bool(sync_changed),
        "channel_cleanup_changed": bool(channel_changed),
        "channel_deleted": int(channel_deleted or 0),
        "youtube_cleanup_changed": bool(youtube_changed),
        "aparat_cleanup_changed": bool(aparat_changed),
        "ledger_path": LEDGER_PATH.name,
    }
    save_ledger(ledger)

    print(
        "INTEGRITY_AUDIT_SUMMARY "
        f"tracked_products={len(published)} "
        f"checked={summary.get('products_checked', 0)} "
        f"price_mismatches={summary.get('price_mismatches', 0)} "
        f"out_of_stock={summary.get('out_of_stock_posts', 0)} "
        f"unconfirmed={summary.get('unconfirmed', 0)} "
        f"channel_deleted={channel_deleted} "
        f"youtube_cleanup_changed={youtube_changed} "
        f"aparat_cleanup_changed={aparat_changed} "
        "publisher_state_write=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
