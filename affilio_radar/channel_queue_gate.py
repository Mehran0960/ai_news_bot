#!/usr/bin/env python3
"""Fail-closed check for pending core photo-channel delivery before new discovery."""
from __future__ import annotations

import json
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent / "state.json"
TERMINAL_PRODUCT_QUEUE = {"published", "cancelled", "stale_selection"}
TERMINAL_EDITORIAL_QUEUE = TERMINAL_PRODUCT_QUEUE | {"completed", "failed"}
TERMINAL_PRODUCT_CORE = {"sent", "not_connected", "manual_review"}
TERMINAL_EDITORIAL_CORE = TERMINAL_PRODUCT_CORE | {"skipped_limit"}


def pending_core_deliveries(state: dict) -> list[tuple[str, str, list[str]]]:
    pending: list[tuple[str, str, list[str]]] = []
    for collection_name in ("content_delivery_queue", "editorial_delivery_queue"):
        queue = state.get(collection_name, {})
        if queue is None:
            continue
        if not isinstance(queue, dict):
            raise ValueError(f"{collection_name}_not_an_object")
        for content_id, entry in queue.items():
            if not isinstance(entry, dict):
                raise ValueError(f"{collection_name}_entry_not_an_object")
            entry_status = str(entry.get("status") or "").strip().lower()
            terminal_queue = TERMINAL_EDITORIAL_QUEUE if collection_name == "editorial_delivery_queue" else TERMINAL_PRODUCT_QUEUE
            if entry_status in terminal_queue:
                continue
            terminal_core = TERMINAL_EDITORIAL_CORE if collection_name == "editorial_delivery_queue" else TERMINAL_PRODUCT_CORE
            targets = entry.get("platforms") if isinstance(entry.get("platforms"), dict) else {}
            unresolved = [
                name for name in ("telegram", "bale")
                if not (
                    isinstance(targets.get(name), dict)
                    and str(targets[name].get("status") or "pending").strip().lower() in terminal_core
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
