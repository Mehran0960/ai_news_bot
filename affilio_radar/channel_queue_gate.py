#!/usr/bin/env python3
"""Fail-closed check for pending core photo-channel delivery before new discovery."""
from __future__ import annotations

import json
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent / "state.json"
TERMINAL_QUEUE = {"published", "cancelled", "stale_selection"}
TERMINAL_CORE = {"sent", "not_connected", "manual_review"}


def pending_core_deliveries(state: dict) -> list[tuple[str, str, list[str]]]:
    pending: list[tuple[str, str, list[str]]] = []
    for collection_name in ("content_delivery_queue", "editorial_delivery_queue"):
        queue = state.get(collection_name)
        if not isinstance(queue, dict):
            continue
        for content_id, entry in queue.items():
            if not isinstance(entry, dict):
                continue
            if str(entry.get("status") or "").strip().lower() in TERMINAL_QUEUE:
                continue
            targets = entry.get("platforms") if isinstance(entry.get("platforms"), dict) else {}
            unresolved = [
                name for name in ("telegram", "bale")
                if not (
                    isinstance(targets.get(name), dict)
                    and str(targets[name].get("status") or "pending").strip().lower() in TERMINAL_CORE
                )
            ]
            if unresolved:
                pending.append((collection_name, str(content_id), unresolved))
    return pending


def main() -> int:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("publisher_state_not_object")
    except Exception as exc:
        print(f"OFFERCHIN_DISCOVERY_DEFERRED reason=publisher_state_unavailable error={type(exc).__name__}")
        return 2

    pending = pending_core_deliveries(state)
    if pending:
        collection, content_id, unresolved = pending[0]
        print(
            "OFFERCHIN_DISCOVERY_DEFERRED reason=active_core_channel_queue "
            f"pending_entries={len(pending)} collection={collection} "
            f"sample={content_id} unresolved={','.join(unresolved)}"
        )
        return 1
    print("OFFERCHIN_DISCOVERY_ALLOWED reason=core_channel_queues_drained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
