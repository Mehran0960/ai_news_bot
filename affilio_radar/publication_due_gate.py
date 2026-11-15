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


def due_publication_slot(
    state: dict | None,
    *,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Return whether a product or editorial slot is due, without inventing cadence."""
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
    parser.add_argument("--github-output", default="")
    args = parser.parse_args()

    state = None
    try:
        state = json.loads(Path(args.state_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # Fail open: discovery remains available if the small projection is unreadable.
        pass

    due, reason = due_publication_slot(state)
    value = "true" if due else "false"
    print(f"PUBLICATION_DUE_GATE has_due_slot={value} reason={reason}")
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as output:
            output.write(f"has_due_slot={value}\n")
            output.write(f"reason={reason}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
