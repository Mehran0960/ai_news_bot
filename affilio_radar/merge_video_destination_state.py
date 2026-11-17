#!/usr/bin/env python3
"""Merge isolated OfferChin video worker snapshots without overwriting other writers.

Each destination job starts from the same state.json snapshot and writes only its own
platform outcome. This reducer overlays those scoped deltas onto the newest main state.
It never replaces the live state with a stale worker copy.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

DESTINATION_PREFIX = {
    "youtube": "youtube_",
    "aparat": "aparat_",
    "filo": "filo_",
}
SHARED_VIDEO_FIELDS = {
    "video_generation_status",
    "video_generation_attempts",
    "video_generation_last_error",
    "video_generation_next_attempt_at",
    "video_file_name",
    "video_file_names",
    "video_generated_at",
    "video_style_version",
}
PENDING_GENERATION = {"", "pending", "retry", "failed"}
TERMINAL_GENERATION = {"generated", "skipped_after_retries", "skipped_expiring_soon"}


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid_state_snapshot:{path}:{type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"state_snapshot_not_object:{path}")
    return value


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _merge_shared_video_fields(target: dict, base: dict, source: dict) -> None:
    base_status = str(base.get("video_generation_status") or "")
    source_status = str(source.get("video_generation_status") or "")
    target_status = str(target.get("video_generation_status") or "")
    if source_status == "generated":
        target["video_generation_status"] = "generated"
        for key in SHARED_VIDEO_FIELDS:
            if key in source and key != "video_generation_status":
                target[key] = copy.deepcopy(source[key])
    elif target_status != "generated" and source_status != base_status:
        if source_status:
            target["video_generation_status"] = source_status
        for key in SHARED_VIDEO_FIELDS:
            if key in source and source.get(key) != base.get(key):
                target[key] = copy.deepcopy(source[key])
    try:
        target["video_generation_attempts"] = max(
            int(target.get("video_generation_attempts") or 0),
            int(source.get("video_generation_attempts") or 0),
        )
    except (TypeError, ValueError, OverflowError):
        pass


def _merge_published(target_state: dict, base_state: dict, source_state: dict, prefix: str) -> int:
    target_published = target_state.setdefault("published", {})
    base_published = base_state.get("published") if isinstance(base_state.get("published"), dict) else {}
    source_published = source_state.get("published") if isinstance(source_state.get("published"), dict) else {}
    changed_records = 0
    for product_id, source_row in source_published.items():
        if not isinstance(source_row, dict):
            continue
        base_row = base_published.get(product_id) if isinstance(base_published.get(product_id), dict) else {}
        changed_keys = [
            key for key, value in source_row.items()
            if key.startswith(prefix) and value != base_row.get(key)
        ]
        shared_changed = any(
            key in source_row and source_row.get(key) != base_row.get(key)
            for key in SHARED_VIDEO_FIELDS
        )
        if not changed_keys and not shared_changed:
            continue
        target_row = target_published.setdefault(product_id, copy.deepcopy(source_row))
        if not isinstance(target_row, dict):
            target_row = {}
            target_published[product_id] = target_row
        for key in changed_keys:
            target_row[key] = copy.deepcopy(source_row[key])
        if shared_changed:
            _merge_shared_video_fields(target_row, base_row, source_row)
        changed_records += 1
    return changed_records


def _merge_editorial_queue(target_state: dict, base_state: dict, source_state: dict, destination: str) -> int:
    target_queue = target_state.get("editorial_delivery_queue")
    if not isinstance(target_queue, dict):
        target_queue = {}
        target_state["editorial_delivery_queue"] = target_queue
    base_queue = base_state.get("editorial_delivery_queue") if isinstance(base_state.get("editorial_delivery_queue"), dict) else {}
    source_queue = source_state.get("editorial_delivery_queue") if isinstance(source_state.get("editorial_delivery_queue"), dict) else {}
    changed = 0
    for content_id, source_entry in source_queue.items():
        if not isinstance(source_entry, dict):
            continue
        base_entry = base_queue.get(content_id) if isinstance(base_queue.get(content_id), dict) else {}
        source_platforms = source_entry.get("platforms") if isinstance(source_entry.get("platforms"), dict) else {}
        base_platforms = base_entry.get("platforms") if isinstance(base_entry.get("platforms"), dict) else {}
        source_target = source_platforms.get(destination)
        base_target = base_platforms.get(destination)
        if source_target is None or source_target == base_target:
            continue
        target_entry = target_queue.setdefault(content_id, copy.deepcopy(source_entry))
        if not isinstance(target_entry, dict):
            target_entry = {}
            target_queue[content_id] = target_entry
        target_platforms = target_entry.setdefault("platforms", {})
        if not isinstance(target_platforms, dict):
            target_platforms = {}
            target_entry["platforms"] = target_platforms
        target_platforms[destination] = copy.deepcopy(source_target)
        changed += 1
    return changed


def _merge_editorial_history(target_state: dict, source_state: dict, destination: str) -> int:
    target_history = target_state.setdefault("editorial_delivery_history", [])
    if not isinstance(target_history, list):
        target_history = []
        target_state["editorial_delivery_history"] = target_history
    source_history = source_state.get("editorial_delivery_history")
    if not isinstance(source_history, list):
        return 0
    indexed = {
        str(row.get("content_id") or ""): row
        for row in target_history if isinstance(row, dict) and row.get("content_id")
    }
    changed = 0
    for source_row in source_history:
        if not isinstance(source_row, dict):
            continue
        content_id = str(source_row.get("content_id") or "")
        if not content_id:
            continue
        target_row = indexed.get(content_id)
        if target_row is None:
            target_row = {
                key: copy.deepcopy(value)
                for key, value in source_row.items() if key != "destinations"
            }
            target_row["destinations"] = {}
            target_history.append(target_row)
            indexed[content_id] = target_row
        source_destinations = source_row.get("destinations") if isinstance(source_row.get("destinations"), dict) else {}
        source_target = source_destinations.get(destination)
        if source_target is None:
            continue
        target_destinations = target_row.setdefault("destinations", {})
        if not isinstance(target_destinations, dict):
            target_destinations = {}
            target_row["destinations"] = target_destinations
        if target_destinations.get(destination) != source_target:
            target_destinations[destination] = copy.deepcopy(source_target)
            changed += 1
        if not target_row.get("content_fingerprint") and source_row.get("content_fingerprint"):
            target_row["content_fingerprint"] = source_row["content_fingerprint"]
        for key in ("editorial_id", "topic", "related_product_id", "sequence_number"):
            if not target_row.get(key) and source_row.get(key) is not None:
                target_row[key] = copy.deepcopy(source_row[key])
    target_state["editorial_delivery_history"] = target_history[-200:]
    return changed


def _merge_editorial_attempts(target_state: dict, source_state: dict) -> int:
    target = target_state.setdefault("editorial_delivery_attempts", [])
    source = source_state.get("editorial_delivery_attempts")
    if not isinstance(target, list):
        target = []
        target_state["editorial_delivery_attempts"] = target
    if not isinstance(source, list):
        return 0
    seen = {
        (str(row.get("content_id") or ""), str(row.get("updated_at") or ""), str(row.get("terminal_summary") or ""))
        for row in target if isinstance(row, dict)
    }
    added = 0
    for row in source:
        if not isinstance(row, dict):
            continue
        key = (str(row.get("content_id") or ""), str(row.get("updated_at") or ""), str(row.get("terminal_summary") or ""))
        if key not in seen:
            target.append(copy.deepcopy(row))
            seen.add(key)
            added += 1
    target_state["editorial_delivery_attempts"] = target[-200:]
    return added


def merge_destination_snapshot(target_state: dict, base_state: dict, source_state: dict, destination: str) -> dict:
    if destination not in DESTINATION_PREFIX:
        raise ValueError(f"unsupported_destination:{destination}")
    prefix = DESTINATION_PREFIX[destination]
    root_changed = 0
    for key, value in source_state.items():
        if key.startswith(prefix) and value != base_state.get(key):
            target_state[key] = copy.deepcopy(value)
            root_changed += 1
    published_changed = _merge_published(target_state, base_state, source_state, prefix)
    editorial_queue_changed = _merge_editorial_queue(target_state, base_state, source_state, destination)
    editorial_history_changed = _merge_editorial_history(target_state, source_state, destination)
    attempts_added = _merge_editorial_attempts(target_state, source_state)

    # Merge the shared editorial cycle monotonically. A destination cannot undo
    # another worker's confirmed use of an editorial item.
    target_cycle = target_state.setdefault("editorial_cycle", {})
    source_cycle = source_state.get("editorial_cycle") if isinstance(source_state.get("editorial_cycle"), dict) else {}
    if isinstance(target_cycle, dict):
        target_cycle["used_ids"] = sorted(set(map(str, target_cycle.get("used_ids") or [])) | set(map(str, source_cycle.get("used_ids") or [])))
        try:
            target_cycle["cycle_number"] = max(int(target_cycle.get("cycle_number") or 1), int(source_cycle.get("cycle_number") or 1))
        except (TypeError, ValueError, OverflowError):
            pass
    source_confirmed = source_state.get("last_editorial_confirmed_at")
    target_confirmed = target_state.get("last_editorial_confirmed_at")
    if source_confirmed and (not target_confirmed or str(source_confirmed) > str(target_confirmed)):
        target_state["last_editorial_confirmed_at"] = source_confirmed

    return {
        "destination": destination,
        "root_fields": root_changed,
        "published_records": published_changed,
        "editorial_queue_destinations": editorial_queue_changed,
        "editorial_history_destinations": editorial_history_changed,
        "editorial_attempts_added": attempts_added,
    }


def merge_artifact_directory(target_state: dict, artifact_dir: Path) -> dict:
    name = artifact_dir.name
    destination = next((candidate for candidate in DESTINATION_PREFIX if name.endswith(candidate)), None)
    if not destination:
        raise RuntimeError(f"cannot_infer_destination_from_artifact:{name}")
    base_path = artifact_dir / "state.base.json"
    source_path = artifact_dir / "state.json"
    if not base_path.is_file() or not source_path.is_file():
        raise RuntimeError(f"missing_state_pair_in_artifact:{artifact_dir}")
    return merge_destination_snapshot(target_state, _load(base_path), _load(source_path), destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-root", required=True)
    parser.add_argument("--state", default="affilio_radar/state.json")
    parser.add_argument("--sidecar", default="affilio_radar/video_upload_dispatch_state.json")
    args = parser.parse_args()
    state_path = Path(args.state)
    state = _load(state_path)
    root = Path(args.artifacts_root)
    summaries = []
    for artifact_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        summaries.append(merge_artifact_directory(state, artifact_dir))
    if not summaries:
        print("NO_VIDEO_DESTINATION_ARTIFACTS")
        return 0

    _write(state_path, state)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import affilio_radar as radar
    projection = radar.build_video_upload_dispatch_state(state)
    radar.save_json(Path(args.sidecar), projection)
    print(json.dumps({"merged": summaries, "artifacts": len(summaries)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
