#!/usr/bin/env python3
"""One-time, live-checked three-product promo test for @Iran_gajet.

This is intentionally isolated from the Dayan relay and TrendsUploader.
It only publishes the fixed test batch when the tracked JSON flag is enabled.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import affilio_radar as radar

ROOT = Path(__file__).resolve().parent
BATCH_FILE = ROOT / "test_three_product_batch.json"


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    try:
        batch = json.loads(BATCH_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"TEST_BATCH_READ_FAILED: {type(exc).__name__}")
        return 2

    if not isinstance(batch, dict) or not batch.get("enabled"):
        print("TEST_BATCH_DISABLED: no post attempted.")
        return 0

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("PUBLISH_BLOCKED: TELEGRAM_BOT_TOKEN missing; no post attempted.")
        return 2
    if not isinstance(batch.get("products"), list) or len(batch["products"]) != 3:
        print("PUBLISH_BLOCKED: test batch must contain exactly three products.")
        return 2

    # Avoid mixing this one-time test with the regular radar's cooldown logic.
    radar.BOT_TOKEN = token
    target = os.getenv("AFFILIO_TELEGRAM_CHAT_ID", "@Iran_gajet").strip()
    if not target:
        print("PUBLISH_BLOCKED: Telegram target missing.")
        return 2
    radar.TARGET_CHAT = target

    candidates = []
    for entry in batch["products"]:
        raw_url = str((entry or {}).get("product_url", "")).strip()
        canonical = radar.safe_product_url(raw_url)
        if not canonical:
            print("TEST_PRODUCT_SKIP invalid DigiKala product URL")
            continue
        try:
            item = radar.fetch_product_record(canonical)
            if not item.get("title"):
                print(f"TEST_PRODUCT_SKIP id={radar.product_id(canonical)} reason=no_title")
                continue
            item = radar.score_product(item)
            item["product_url"] = canonical
            item["affiliate_url"] = radar.build_affilio_tracking_link(canonical)
            item["has_affiliate_link"] = bool(item["affiliate_url"])
            candidates.append(item)
            print(
                f"TEST_CANDIDATE id={item.get('product_id')} score={item.get('demand_score')} "
                f"stock={item.get('availability')} price={item.get('current_price')} "
                f"reviews={item.get('review_count')} linked={item['has_affiliate_link']} "
                f"title={item.get('title')!r}"
            )
        except Exception as exc:
            print(f"TEST_PRODUCT_FETCH_FAILED id={radar.product_id(canonical)} error={type(exc).__name__}")

    # Do not publish if any fixed product cannot pass the current live checks:
    # the user asked to inspect a three-post test, so a partial batch isn't silently substituted.
    by_id = {item.get("product_id"): item for item in candidates}
    expected_ids = [radar.product_id(radar.safe_product_url(str(x.get("product_url", "")))) for x in batch["products"]]
    selected = [by_id.get(pid) for pid in expected_ids]
    if len(selected) != 3 or any(not item or not radar.is_publish_eligible(item) for item in selected):
        print("PUBLISH_BLOCKED: one or more selected products failed live price/image/stock/affiliate-link checks; zero posts attempted.")
        return 2

    state = radar.load_state()
    state.setdefault("published", {})
    posted = []
    for index, item in enumerate(selected, start=1):
        pid = item["product_id"]
        old = state["published"].get(pid, {})
        try:
            old_ts = float(old.get("ts", 0))
        except (TypeError, ValueError):
            old_ts = 0
        if time.time() - old_ts < radar.PRODUCT_COOLDOWN_DAYS * 86400:
            print(f"PUBLISH_BLOCKED: selected product {pid} already appears in recent publish history; zero new posts attempted.")
            # The next product may have been sent already only if duplicate IDs were supplied.
            return 2

    # All three have passed the preflight before any Telegram post is sent.
    try:
        for index, item in enumerate(selected, start=1):
            pid = item["product_id"]
            image_bytes = radar._fetch_image(item["image_url"])
            with tempfile.TemporaryDirectory(prefix="affilio-three-test-") as td:
                video_path = Path(td) / f"{pid}.mp4"
                radar.build_promo_video(item, image_bytes, video_path)
                result = radar._send_video(video_path, radar.build_caption(item, item["affiliate_url"]))
            msg_id = result.get("message_id")
            posted.append({"product_id": pid, "title": item["title"], "message_id": msg_id})
            now = time.time()
            state["published"][pid] = {
                "ts": now,
                "title": item["title"],
                "product_url": item["product_url"],
                "telegram_message_id": msg_id,
                "test_batch": True,
            }
            state["last_published_at"] = datetime.now(timezone.utc).isoformat()
            radar.save_json(radar.STATE, state)
            print(f"TEST_POSTED {index}/3 product_id={pid} message_id={msg_id} score={item['demand_score']}")
            if index < 3:
                time.sleep(2)
    except Exception as exc:
        # One-shot latch even after a partial send: never auto-repost items already sent.
        batch["enabled"] = False
        batch["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
        batch["posted"] = posted
        batch["last_error_type"] = type(exc).__name__
        batch["result"] = "partial_or_failed"
        write_json(BATCH_FILE, batch)
        print(f"PUBLISH_PARTIAL_OR_FAILED posts_sent={len(posted)} error={type(exc).__name__}")
        return 3

    # One-shot latch: the commit made by the workflow triggers this workflow once more,
    # but this disabled flag makes that second run a no-op.
    batch["enabled"] = False
    batch["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
    batch["posted"] = posted
    batch["result"] = "success"
    write_json(BATCH_FILE, batch)
    print(f"TEST_BATCH_SUCCESS posts_sent={len(posted)} target={target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
