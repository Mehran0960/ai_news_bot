#!/usr/bin/env python3
"""Three-way merge concurrent JSON state commits from independent media workers."""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from datetime import datetime
from pathlib import Path
from typing import Any

def _stage_json(stage: int, path: str) -> Any:
    return json.loads(subprocess.check_output(["git", "show", f":{stage}:{path}"], text=True))

def _newer_iso(left: Any, right: Any) -> Any:
    def parsed(value):
        if not isinstance(value, str): return None
        try: return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError: return None
    a, b = parsed(left), parsed(right)
    return left if a and b and a >= b else right if a and b else left

def three_way_merge(base: Any, ours: Any, theirs: Any, path: str = "") -> Any:
    if ours == theirs: return ours
    # Always inspect the root object so active editorial queue keys can be
    # protected from a stale concurrent writer that omitted the whole queue.
    if path != "" and ours == base: return theirs
    if path != "" and theirs == base: return ours
    if isinstance(ours, dict) and isinstance(theirs, dict):
        base_map = base if isinstance(base, dict) else {}
        result = {}
        for key in set(base_map) | set(ours) | set(theirs):
            bp, op, tp = key in base_map, key in ours, key in theirs
            b, o, t = base_map.get(key), ours.get(key), theirs.get(key)
            child = f"{path}.{key}" if path else key
            if not op and not tp: continue
            if not op:
                if not bp or t != b: result[key] = t
                continue
            if not tp:
                if not bp or o != b: result[key] = o
                continue
            result[key] = three_way_merge(b, o, t, child)

        if path == "":
            # A worker can read an older state before another worker reserves or
            # updates an editorial event. If that stale worker later writes a state
            # without the queue key, deletion must not silently strand destinations
            # whose confirmed receipts remain in history.
            attempts = result.get("editorial_delivery_attempts")
            attempts = attempts if isinstance(attempts, list) else []
            terminal_keys = {
                (
                    str(row.get("content_id") or "").strip(),
                    str(row.get("sequence_number") or "").strip(),
                )
                for row in attempts
                if isinstance(row, dict)
                and str(row.get("status") or "").strip().lower()
                in {"completed", "failed", "cancelled"}
            }

            merged_queue = result.get("editorial_delivery_queue")
            if not isinstance(merged_queue, dict):
                merged_queue = {}
                result["editorial_delivery_queue"] = merged_queue
            candidates = []
            for snapshot in (base, ours, theirs):
                queue = snapshot.get("editorial_delivery_queue") if isinstance(snapshot, dict) else None
                if isinstance(queue, dict):
                    candidates.append(queue)
            for content_id in set().union(*(set(queue) for queue in candidates)):
                if content_id in merged_queue:
                    continue
                rows = [
                    queue[content_id] for queue in candidates
                    if isinstance(queue.get(content_id), dict)
                ]
                active = [
                    row for row in rows
                    if str(row.get("status") or "").strip().lower()
                    not in {"completed", "failed", "cancelled"}
                ]
                if not active:
                    continue
                identity = active[-1]
                event_content_id = str(identity.get("content_id") or content_id).strip()
                sequence = str(identity.get("sequence_number") or "").strip()
                if (event_content_id, sequence) in terminal_keys:
                    continue
                # Preserve the latest active snapshot. The queue remains resumable;
                # destination receipt history is merged independently below.
                chosen = active[0]
                for candidate in active[1:]:
                    chosen_at = _newer_iso(
                        chosen.get("updated_at") or chosen.get("last_delivery_update_at"),
                        candidate.get("updated_at") or candidate.get("last_delivery_update_at"),
                    )
                    candidate_at = candidate.get("updated_at") or candidate.get("last_delivery_update_at")
                    if chosen_at == candidate_at and candidate_at:
                        chosen = candidate
                merged_queue[content_id] = chosen
        return result
    if isinstance(ours, list) and isinstance(theirs, list):
        if path in {"editorial_delivery_history", "editorial_content_ledger"}:
            def keyed(rows):
                result = {}
                order = []
                for index, row in enumerate(rows):
                    if not isinstance(row, dict):
                        key = f"row:{index}:{json.dumps(row, ensure_ascii=False, sort_keys=True)}"
                    elif path == "editorial_delivery_history":
                        event_id = str(row.get("delivery_event_id") or "").strip()
                        content_id = str(row.get("content_id") or "").strip()
                        sequence = str(row.get("sequence_number") or "").strip()
                        key = event_id or (f"{content_id}:sequence:{sequence}" if content_id and sequence else f"{content_id}:legacy")
                    else:
                        key = str(row.get("content_fingerprint") or "").strip()
                        if not key:
                            key = f"row:{index}:{json.dumps(row, ensure_ascii=False, sort_keys=True)}"
                    if key not in result:
                        result[key] = row
                        order.append(key)
                    else:
                        result[key] = three_way_merge(None, result[key], row, f"{path}.{key}")
                return result, order

            base_map, _ = keyed(base if isinstance(base, list) else [])
            ours_map, ours_order = keyed(ours)
            theirs_map, theirs_order = keyed(theirs)
            merged = []
            ordered_keys = ours_order + [key for key in theirs_order if key not in ours_map]
            for key in ordered_keys:
                in_ours = key in ours_map
                in_theirs = key in theirs_map
                if in_ours and in_theirs:
                    merged.append(three_way_merge(
                        base_map.get(key), ours_map[key], theirs_map[key], f"{path}.{key}"
                    ))
                elif in_ours:
                    merged.append(ours_map[key])
                elif in_theirs:
                    merged.append(theirs_map[key])
            limit = 200 if path == "editorial_delivery_history" else 500
            return merged[-limit:]
        return ours + [value for value in theirs if value not in ours]
    if path.endswith(("_at", "_timestamp", "_time")) or path in {
        "generated_at", "last_channel_published_at", "last_product_channel_published_at"
    }:
        return _newer_iso(ours, theirs)
    return ours

def resolve_conflicts(paths: list[str]) -> list[str]:
    resolved = []
    for path in paths:
        try:
            base, ours, theirs = (_stage_json(stage, path) for stage in (1, 2, 3))
        except subprocess.CalledProcessError:
            continue
        merged = three_way_merge(base, ours, theirs)
        Path(path).write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "add", path], check=True)
        resolved.append(path)
    return resolved

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paths", nargs="+", required=True)
    args = parser.parse_args()
    unresolved = subprocess.check_output(["git", "diff", "--name-only", "--diff-filter=U"], text=True).splitlines()
    resolved = resolve_conflicts([path for path in args.paths if path in unresolved])
    remaining = subprocess.check_output(["git", "diff", "--name-only", "--diff-filter=U"], text=True).splitlines()
    if remaining or not resolved:
        print("STATE_MERGE_FAILED unresolved=" + ",".join(remaining), file=sys.stderr)
        return 2
    print("STATE_MERGE_RESOLVED files=" + ",".join(resolved))
    subprocess.run(["git", "-c", "core.editor=true", "rebase", "--continue"], check=True,
                   env={**os.environ, "GIT_EDITOR": "true"})
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
