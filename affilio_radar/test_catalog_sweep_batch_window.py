"""Regression tests for the bounded catalog batch-window runner."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from affilio_radar import catalog_sweep_batch_window as window


class CatalogSweepBatchWindowTests(unittest.TestCase):
    def test_runs_three_serial_batches_and_uses_short_clean_cooldown(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            calls = []

            def fake_batch(*, pages_per_run, workers):
                calls.append((pages_per_run, workers))
                state_path.write_text(json.dumps({
                    "parallel_last_batch_rate_limited": 0,
                    "parallel_last_batch_retries": 0,
                }), encoding="utf-8")
                return 0

            sleep = Mock()
            result = window.run_batch_window(
                pages_per_batch=480,
                workers=16,
                batches=3,
                state_path=state_path,
                run_batch=fake_batch,
                sleep_fn=sleep,
            )

        self.assertEqual(result, 0)
        self.assertEqual(calls, [(480, 16), (480, 16), (480, 16)])
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [3, 3])

    def test_rate_limits_trigger_longer_cooldown_between_batches(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"

            def fake_batch(*, pages_per_run, workers):
                state_path.write_text(json.dumps({
                    "parallel_last_batch_rate_limited": 2,
                    "parallel_last_batch_retries": 2,
                }), encoding="utf-8")
                return 0

            sleep = Mock()
            result = window.run_batch_window(
                batches=2,
                state_path=state_path,
                run_batch=fake_batch,
                sleep_fn=sleep,
            )

        self.assertEqual(result, 0)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [20])

    def test_heavy_failures_trigger_maximum_cooldown(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"

            def fake_batch(*, pages_per_run, workers):
                state_path.write_text(json.dumps({
                    "parallel_last_batch_rate_limited": 0,
                    "parallel_last_batch_retries": 3,
                }), encoding="utf-8")
                return 0

            sleep = Mock()
            result = window.run_batch_window(
                batches=2,
                state_path=state_path,
                run_batch=fake_batch,
                sleep_fn=sleep,
            )

        self.assertEqual(result, 0)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [30])

    def test_failed_batch_stops_the_window_without_cooldown(self):
        calls = []
        sleep = Mock()

        def fake_batch(*, pages_per_run, workers):
            calls.append((pages_per_run, workers))
            return 1

        result = window.run_batch_window(
            batches=3,
            run_batch=fake_batch,
            sleep_fn=sleep,
        )

        self.assertEqual(result, 1)
        self.assertEqual(calls, [(480, 16)])
        sleep.assert_not_called()

    def test_window_cannot_exceed_three_batches(self):
        with self.assertRaises(ValueError):
            window.run_batch_window(batches=4, run_batch=lambda **_: 0)


if __name__ == "__main__":
    unittest.main()
