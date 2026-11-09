#!/usr/bin/env python3
"""Run a small window of serial, independently adaptive DigiKala scan batches.

Each microbatch keeps the existing 480-page ceiling and the crawler's own
AIMD worker controller. Only the gap between microbatches changes: clean
batches continue quickly; rate limits and transient failures trigger a pause.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Callable

try:
    from . import parallel_catalog_sweep as scanner
except ImportError:  # pragma: no cover - direct script compatibility
    import parallel_catalog_sweep as scanner


MAX_BATCHES_PER_WINDOW = 3
DEFAULT_PAGES_PER_BATCH = 480
DEFAULT_WORKERS = 16


def _cooldown_from_state(state: Any) -> tuple[int, str]:
    """Return a conservative inter-batch pause from the last batch telemetry."""
    if not isinstance(state, dict):
        return 30, "state_unavailable"
    required = (
        "parallel_last_batch_rate_limited",
        "parallel_last_batch_retries",
    )
    if any(key not in state for key in required):
        return 30, "telemetry_unavailable"

    rate_limited = max(
        0, scanner.base._normal_int(state.get("parallel_last_batch_rate_limited"))
    )
    retries = max(0, scanner.base._normal_int(state.get("parallel_last_batch_retries")))

    if rate_limited >= 3 or retries >= 3:
        return 30, "heavy_backoff"
    if rate_limited:
        return 20, "rate_limited"
    if retries:
        return 10, "transient_retry"
    return 3, "clean_batch"


def run_batch_window(
    *,
    pages_per_batch: int = DEFAULT_PAGES_PER_BATCH,
    workers: int = DEFAULT_WORKERS,
    batches: int = MAX_BATCHES_PER_WINDOW,
    state_path: Path | str | None = None,
    run_batch: Callable[..., int] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> int:
    """Run up to three 480-page microbatches without raising worker concurrency."""
    if pages_per_batch < 1:
        raise ValueError("pages_per_batch must be positive")
    if workers < 1:
        raise ValueError("workers must be positive")
    if not 1 <= batches <= MAX_BATCHES_PER_WINDOW:
        raise ValueError(f"batches must be between 1 and {MAX_BATCHES_PER_WINDOW}")

    state_file = Path(state_path) if state_path is not None else scanner.STATE_PATH
    batch_runner = run_batch or scanner.run_parallel_sweep
    sleeper = sleep_fn or time.sleep

    for index in range(1, batches + 1):
        print(
            "CATALOG_BATCH_WINDOW_START "
            f"batch={index}/{batches} pages_per_batch={pages_per_batch} workers_ceiling={workers}"
        )
        try:
            exit_code = int(
                batch_runner(pages_per_run=pages_per_batch, workers=workers)
            )
        except Exception as exc:
            print(
                "CATALOG_BATCH_WINDOW_ABORTED "
                f"batch={index}/{batches} error={type(exc).__name__}:{str(exc)[:160]}"
            )
            return 1

        if exit_code != 0:
            print(
                "CATALOG_BATCH_WINDOW_ABORTED "
                f"batch={index}/{batches} exit_code={exit_code}"
            )
            return exit_code

        if index == batches:
            continue

        try:
            state = scanner.base._read_json(state_file, {})
        except Exception as exc:
            print(
                "CATALOG_BATCH_WINDOW_ABORTED "
                f"reason=state_read_failed error={type(exc).__name__}:{str(exc)[:160]}"
            )
            return 1

        cooldown, reason = _cooldown_from_state(state)
        print(
            "CATALOG_BATCH_WINDOW_COOLDOWN "
            f"after_batch={index} seconds={cooldown} reason={reason}"
        )
        sleeper(cooldown)

    print(
        "CATALOG_BATCH_WINDOW_COMPLETE "
        f"batches={batches} pages_per_batch={pages_per_batch} "
        f"page_attempt_budget={batches * pages_per_batch}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a bounded window of serial DigiKala catalog batches"
    )
    parser.add_argument("--pages-per-batch", type=int, default=DEFAULT_PAGES_PER_BATCH)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--batches", type=int, default=MAX_BATCHES_PER_WINDOW)
    args = parser.parse_args()
    return run_batch_window(
        pages_per_batch=args.pages_per_batch,
        workers=args.workers,
        batches=args.batches,
    )


if __name__ == "__main__":
    sys.exit(main())
