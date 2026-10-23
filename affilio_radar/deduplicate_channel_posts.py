#!/usr/bin/env python3
"""Safely remove duplicate active OfferChin product posts.

Telegram history is read from the public channel preview. Duplicate groups are
based on a product ID found in the published purchase URL, or (only when no ID
is present) an exact normalized product title. The newest copy is retained,
preferring a copy whose purchase link is visible. Non-offer posts are ignored.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "state.json"
CHANNEL_USERNAME = re.sub(r"[^A-Za-z0-9_]", "", os.getenv("TELEGRAM_CHANNEL_USERNAME", "OfferChin")) or "OfferChin"
HTTP_TIMEOUT = max(5, int(os.getenv("OFFERCHIN_DUPLICATE_HTTP_TIMEOUT", "20")))
MAX_PAGES = max(1, min(80, int(os.getenv("OFFERCHIN_DUPLICATE_MAX_PAGES", "30"))))
DELETE_DELAY_SECONDS = max(0.2, float(os.getenv("OFFERCHIN_DUPLICATE_DELETE_DELAY", "1.0")))


def _digits(value: str) -> str:
    return (value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def _product_id_from_url(value: str) -> str:
    try:
        parsed = urlsplit(html.unescape(str(value or "").strip()))
    except Exception:
        return ""
    host = (parsed.hostname or "").lower()
    if host == "aflo.ir" or host.endswith(".aflo.ir"):
        for destination in parse_qs(parsed.query, keep_blank_values=True).get("p", []):
            found = _product_id_from_url(unquote(destination))
            if found:
                return found
    match = re.search(r"/product/(dkp-\d+)(?:/|$)", parsed.path, re.I)
    if match:
        return match.group(1).lower()
    match = re.search(r"/p/(dkp-\d+)(?:/|$)", parsed.path, re.I)
    if match and ("workers.dev" in host or host.endswith(".workers.dev")):
        return match.group(1).lower()
    return ""


def _normalise_title(value: str) -> str:
    value = _digits(str(value or "")).lower().replace("ي", "ی").replace("ك", "ک").replace("\u200c", "")
    value = re.sub(r"[\u200b-\u200f\ufeff]", "", value)
    return "".join(re.findall(r"[^\W_]+", value, flags=re.UNICODE))


def _offer_title(caption_text: str) -> str:
    text = " ".join(str(caption_text or "").split())
    if not re.search(r"پیشنهاد\s+شگفت(?:‌| )?انگیز\s+دیجی(?:‌| )?کالا", text):
        return ""
    match = re.search(
        r"🛍️?\s*(.+?)(?=\s*(?:💚\s*قیمت\s*ویژه|⚡️?\s*[\d۰-۹٠-٩]+\s*٪?\s*تخفیف|"
        r"🏷️?\s*قیمت\s*اصلی|📅|⏳|⌛|📣|👇|عضویت\s+در\s+کانال|$))",
        text,
    )
    if not match:
        return ""
    title = match.group(1).strip(" \t:：-–")
    return title if len(_normalise_title(title)) >= 12 else ""


def _entries(state: dict):
    published = state.get("published", {})
    if not isinstance(published, dict):
        return
    for outer_id, record in published.items():
        if not isinstance(record, dict):
            continue
        product_id = str(outer_id or "").lower()
        if not re.fullmatch(r"dkp-\d+", product_id):
            product_id = _product_id_from_url(record.get("product_url", ""))
        yield product_id, record
        history = record.get("post_history")
        if isinstance(history, list):
            for previous in history:
                if isinstance(previous, dict):
                    yield product_id, previous


def _state_message_products(state: dict):
    by_message = {}
    button_known = {}
    for product_id, record in _entries(state) or []:
        for platform, id_field in (("telegram", "telegram_message_id"), ("bale", "bale_message_id")):
            raw_id = record.get(id_field)
            if not str(raw_id or "").isdigit():
                continue
            message_id = int(raw_id)
            entry_product_id = product_id or _product_id_from_url(record.get("product_url", ""))
            if entry_product_id:
                by_message[(platform, message_id)] = entry_product_id
            delivery = record.get("delivery_status")
            button_known[(platform, message_id)] = (
                platform == "telegram" and isinstance(delivery, dict) and delivery.get("telegram") == "sent"
            )
    return by_message, button_known


def _fetch_page(before: int | None = None) -> dict[int, dict]:
    url = f"https://t.me/s/{CHANNEL_USERNAME}"
    if before:
        url += f"?before={int(before)}"
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; OfferChinDuplicateCleanup/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urlopen(request, timeout=HTTP_TIMEOUT) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise RuntimeError("Telegram public history page exceeded 4 MB")
    soup = BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser")
    results = {}
    for wrap in soup.select(".tgme_widget_message_wrap"):
        node = wrap.select_one(".tgme_widget_message") or wrap
        post_ref = str(node.get("data-post") or wrap.get("data-post") or "")
        id_match = re.search(r"/(\d+)$", post_ref)
        if not id_match:
            continue
        message_id = int(id_match.group(1))
        caption_node = wrap.select_one(".tgme_widget_message_text")
        caption_text = caption_node.get_text(" ", strip=True) if caption_node else ""
        product_ids = set()
        button_visible = False
        for anchor in wrap.select("a[href]"):
            product_id = _product_id_from_url(anchor.get("href", ""))
            if product_id:
                product_ids.add(product_id)
                button_visible = True
        title = _offer_title(caption_text)
        # Keep only product offers or a message that exposes an exact DigiKala purchase destination.
        if title or product_ids:
            results[message_id] = {
                "message_id": message_id,
                "caption_text": caption_text,
                "caption_html": caption_node.decode_contents() if caption_node else "",
                "title": title,
                "product_ids": sorted(product_ids),
                "purchase_button_visible": button_visible,
            }
    return results


def fetch_public_channel_posts(max_pages: int | None = None):
    max_pages = max_pages or MAX_PAGES
    all_posts = {}
    before = None
    last_oldest = None
    pages = 0
    reached_end = False
    for page_number in range(1, max_pages + 1):
        page_posts = _fetch_page(before)
        pages += 1
        if not page_posts:
            reached_end = True
            break
        all_posts.update(page_posts)
        oldest = min(page_posts)
        print(f"DUPLICATE_SCAN_PAGE page={page_number} posts={len(page_posts)} oldest_id={oldest} newest_id={max(page_posts)}")
        if oldest <= 1 or oldest == last_oldest:
            reached_end = True
            break
        last_oldest = oldest
        before = oldest
        time.sleep(0.15)
    print(f"DUPLICATE_SCAN_SUMMARY posts={len(all_posts)} pages={pages} history_complete={str(reached_end).lower()} page_limit={max_pages}")
    return all_posts, pages, reached_end


def find_duplicate_groups(posts: dict[int, dict], state: dict | None = None):
    state_product, state_button = _state_message_products(state or {})
    buckets = defaultdict(list)
    for message_id, post in posts.items():
        title = str(post.get("title") or _offer_title(post.get("caption_text", "")))
        product_ids = set(post.get("product_ids") or [])
        for source in ("telegram",):
            known = state_product.get((source, int(message_id)))
            if known:
                product_ids.add(known)
        if len(product_ids) == 1:
            key = ("product", next(iter(product_ids)))
        elif len(product_ids) > 1:
            # Conflicting destination IDs are ambiguous: fail closed.
            continue
        else:
            norm = _normalise_title(title)
            if not title or len(norm) < 12:
                continue
            key = ("title", norm)
        post["has_purchase_button"] = bool(
            post.get("purchase_button_visible") or state_button.get(("telegram", int(message_id)), False)
        )
        buckets[key].append(int(message_id))
    groups = [sorted(set(ids)) for ids in buckets.values() if len(set(ids)) > 1]
    return sorted(groups, key=lambda group: group[0])


def _mark_state_message(state: dict, platform: str, message_id: int, outcome: str):
    changed = False
    status_field = "expiry_status" if platform == "telegram" else "bale_expiry_status"
    timestamp_field = ("expired_deleted_at" if outcome == "deleted" else "expiry_absent_at") if platform == "telegram" else (
        "bale_expired_deleted_at" if outcome == "deleted" else "bale_expiry_absent_at"
    )
    for _product_id, record in _entries(state) or []:
        id_field = "telegram_message_id" if platform == "telegram" else "bale_message_id"
        if str(record.get(id_field) or "").isdigit() and int(record[id_field]) == int(message_id):
            if record.get(status_field) != outcome or not record.get(timestamp_field):
                record[status_field] = outcome
                record[timestamp_field] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
                changed = True
    return changed


def _delete_message(platform: str, message_id: int, token: str, channel_id: str = ""):
    if not token:
        raise RuntimeError(f"{platform.upper()} bot token is missing")
    if platform == "telegram":
        url = f"https://api.telegram.org/bot{token}/deleteMessage"
        target = f"@{CHANNEL_USERNAME}"
    else:
        if not channel_id:
            raise RuntimeError("BALE_CHANNEL_ID is missing")
        url = f"https://tapi.bale.ai/bot{token}/deleteMessage"
        target = channel_id
    payload = json.dumps({"chat_id": target, "message_id": int(message_id)}).encode("utf-8")
    request = Request(url, data=payload, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            description = str(json.loads(raw).get("description") or raw)
        except Exception:
            description = raw or str(exc)
        if any(term in description.lower() for term in ("message to delete not found", "message_id_invalid")):
            return "already_absent"
        retry = re.search(r"retry after\s+(\d+)", description, re.I)
        if retry:
            time.sleep(min(120, int(retry.group(1)) + 1))
            return _delete_message(platform, message_id, token, channel_id)
        raise RuntimeError(description[:220]) from None
    if result.get("ok") is True:
        return "deleted"
    description = str(result.get("description") or f"{platform} deleteMessage failed")
    if any(term in description.lower() for term in ("message to delete not found", "message_id_invalid")):
        return "already_absent"
    raise RuntimeError(description[:220])


def deduplicate_telegram(posts: dict[int, dict], state: dict, apply: bool, token: str):
    groups = find_duplicate_groups(posts, state)
    summary = {"groups": len(groups), "duplicates_found": sum(len(ids) - 1 for ids in groups),
               "deleted": 0, "already_absent": 0, "failed": 0, "deleted_ids": []}
    state_product, state_button = _state_message_products(state)
    for ids in groups:
        winner = max(ids, key=lambda mid: (
            bool(posts.get(mid, {}).get("has_purchase_button") or state_button.get(("telegram", mid), False)),
            int(mid),
        ))
        key = state_product.get(("telegram", winner)) or _normalise_title(posts[winner].get("title", ""))
        print(f"DUPLICATE_GROUP platform=telegram key={key} ids={ids} keep={winner}")
        for message_id in ids:
            if message_id == winner:
                continue
            if not apply:
                print(f"DUPLICATE_WOULD_DELETE platform=telegram message_id={message_id} keep={winner}")
                continue
            try:
                outcome = _delete_message("telegram", message_id, token)
                summary["deleted" if outcome == "deleted" else "already_absent"] += 1
                if outcome == "deleted":
                    summary["deleted_ids"].append(message_id)
                _mark_state_message(state, "telegram", message_id, outcome)
                print(f"DUPLICATE_DELETE_RESULT platform=telegram message_id={message_id} keep={winner} outcome={outcome}")
            except Exception as exc:
                summary["failed"] += 1
                print(f"DUPLICATE_DELETE_FAILED platform=telegram message_id={message_id} keep={winner} error={type(exc).__name__}: {str(exc)[:160]}")
            time.sleep(DELETE_DELAY_SECONDS)
    return summary


def _bale_duplicate_groups(state: dict):
    grouped = defaultdict(list)
    for product_id, record in _entries(state) or []:
        raw_id = record.get("bale_message_id")
        status = str(record.get("bale_expiry_status") or "")
        if not str(raw_id or "").isdigit() or status in {"deleted", "already_absent"} or not product_id:
            continue
        grouped[product_id].append(int(raw_id))
    return [(pid, sorted(set(ids))) for pid, ids in grouped.items() if len(set(ids)) > 1]


def deduplicate_tracked_bale(state: dict, apply: bool, token: str, channel_id: str):
    groups = _bale_duplicate_groups(state)
    summary = {"groups": len(groups), "duplicates_found": sum(len(ids) - 1 for _, ids in groups),
               "deleted": 0, "already_absent": 0, "failed": 0}
    for product_id, ids in groups:
        winner = max(ids)
        print(f"DUPLICATE_GROUP platform=bale product_id={product_id} ids={ids} keep={winner}")
        for message_id in ids:
            if message_id == winner:
                continue
            if not apply:
                print(f"DUPLICATE_WOULD_DELETE platform=bale message_id={message_id} keep={winner}")
                continue
            try:
                outcome = _delete_message("bale", message_id, token, channel_id)
                summary["deleted" if outcome == "deleted" else "already_absent"] += 1
                _mark_state_message(state, "bale", message_id, outcome)
                print(f"DUPLICATE_DELETE_RESULT platform=bale message_id={message_id} keep={winner} outcome={outcome}")
            except Exception as exc:
                summary["failed"] += 1
                print(f"DUPLICATE_DELETE_FAILED platform=bale message_id={message_id} keep={winner} error={type(exc).__name__}: {str(exc)[:160]}")
            time.sleep(DELETE_DELAY_SECONDS)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="delete duplicates (default: report only)")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    args = parser.parse_args(argv)
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    bale_token = os.getenv("BALE_BOT_TOKEN", "").strip()
    bale_channel_id = os.getenv("BALE_CHANNEL_ID", "").strip()
    if args.apply and not telegram_token:
        print("ERROR: TELEGRAM_BOT_TOKEN is required for deletion.", file=sys.stderr)
        return 2
    try:
        raw_state = STATE_PATH.read_text(encoding="utf-8") if STATE_PATH.exists() else "{}"
        state = json.loads(raw_state)
        if not isinstance(state, dict):
            raise ValueError("state root must be an object")
        posts, pages, reached_end = fetch_public_channel_posts(args.max_pages)
    except Exception as exc:
        print(f"DUPLICATE_SCAN_ABORTED error={type(exc).__name__}: {str(exc)[:220]}", file=sys.stderr)
        print("No messages were deleted because channel history could not be safely read.", file=sys.stderr)
        return 2
    if not posts:
        print("DUPLICATE_SCAN_EMPTY; refusing to delete anything.")
        return 2

    before_state = json.dumps(state, ensure_ascii=False, sort_keys=True)
    telegram = deduplicate_telegram(posts, state, args.apply, telegram_token)
    bale = deduplicate_tracked_bale(state, args.apply, bale_token, bale_channel_id)
    after_state = json.dumps(state, ensure_ascii=False, sort_keys=True)
    if args.apply and before_state != after_state:
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("DUPLICATE_STATE_UPDATED=true")
    print("DUPLICATE_CLEANUP_FINAL " + json.dumps({
        "mode": "apply" if args.apply else "dry_run",
        "telegram": telegram,
        "bale_tracked_state_only": bale,
        "pages_fetched": pages,
        "history_complete": reached_end,
        "note": "Telegram is scanned from public history. Bale Bot API has no channel-history listing; Bale cleanup is limited to duplicate message IDs already present in state.",
    }, ensure_ascii=False, sort_keys=True))
    return 1 if telegram["failed"] or bale["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
