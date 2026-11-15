#!/usr/bin/env python3
"""Fail-open check that skips catalog discovery when a channel/editorial slot is due."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def has_active_core_channel_queue(queue_state: dict | None) -> bool:
    """Keep discovery out of the way while Telegram/Bale slots remain unresolved."""
    if not isinstance(queue_state, dict):
        return False

    product_terminal_queue = {"published", "cancelled", "stale_selection"}
    editorial_terminal_queue = product_terminal_queue | {"completed", "failed"}
    product_terminal_core = {"sent", "not_connected", "manual_review"}
    editorial_terminal_core = product_terminal_core | {"skipped_limit"}

    for collection_name in ("content_delivery_queue", "editorial_delivery_queue"):
        queue = queue_state.get(collection_name)
        if not isinstance(queue, dict):
            continue
        terminal_queue = (
            editorial_terminal_queue
            if collection_name == "editorial_delivery_queue"
            else product_terminal_queue
        )
        terminal_core = (
            editorial_terminal_core
            if collection_name == "editorial_delivery_queue"
            else product_terminal_core
        )
        for entry in queue.values():
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("status") or "").strip().lower()
            if status in terminal_queue:
                continue
            targets = entry.get("platforms") if isinstance(entry.get("platforms"), dict) else {}
            for destination in ("telegram", "bale"):
                target = targets.get(destination)
                target_status = (
                    str(target.get("status") or "pending").strip().lower()
                    if isinstance(target, dict) else "pending"
                )
                if target_status not in terminal_core:
                    return True
    return False


def due_publication_slot(
    state: dict | None,
    *,
    queue_state: dict | None = None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Return whether delivery is due or an active core queue should drain first."""
    if has_active_core_channel_queue(queue_state):
        return True, "active_core_channel_queue"

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    if not isinstance(state, dict):
        return False, "dispatch_sidecar_unavailable_fail_open"

    checks = (
        ("next_channel_content_due_at", "channel_content"),
        ("next_editorial_planning_at", "editorial_midpoint"),
    )
    for field, label in checks:
        due_at = _utc(state.get(field))
        if due_at is not None and due_at <= current:
            return True, f"{label}_due"
    return False, "no_publication_slot_due"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--state-path",
        default="affilio_radar/video_upload_dispatch_state.json",
    )
    parser.add_argument("--queue-state-path", default="affilio_radar/state.json")
    parser.add_argument("--github-output", default="")
    args = parser.parse_args()

    state = None
    queue_state = None
    try:
        state = json.loads(Path(args.state_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # Fail open: discovery remains available if the small projection is unreadable.
        pass

    try:
        queue_state = json.loads(Path(args.queue_state_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # Missing queue state does not corrupt the independent due-time projection.
        pass

    due, reason = due_publication_slot(state, queue_state=queue_state)
    value = "true" if due else "false"
    print(f"PUBLICATION_DUE_GATE has_due_slot={value} reason={reason}")
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as output:
            output.write(f"has_due_slot={value}\n")
            output.write(f"reason={reason}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
