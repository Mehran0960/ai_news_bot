#!/usr/bin/env python3
"""Delete OfferChin deal posts after a verified DigiKala offer deadline.

This monitor is intentionally conservative: it deletes only messages that have an
explicit expiry timestamp (from DigiKala's live Incredible Offers feed or an
explicitly marked approximate deadline already recorded for a manually sent post).
Unavailable price/feed data alone never triggers deletion.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state.json"
CHAT_ID = os.getenv("AFFILIO_TELEGRAM_CHAT_ID", "@OfferChin").strip()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
BALE_BOT_TOKEN = os.getenv("BALE_BOT_TOKEN", "").strip()
BALE_CHANNEL_ID = os.getenv("BALE_CHANNEL_ID", "").strip()
DEAL_LIST_PAGES = max(1, min(5, int(os.getenv("AFFILIO_DEAL_LIST_PAGES", "3"))))
FEED_URL = "https://api.digikala.com/v1/incredible-offers/products/"
HTTP_TIMEOUT = 18
PROBE_INTERVAL_SECONDS = 900
UNKNOWN_PROBE_INTERVAL_SECONDS = 900


def walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def parse_expiry(value):
    """Parse an explicit absolute deadline to UTC; naive timestamps use Tehran time."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000_000:
            number /= 1000.0
        if number >= 1_000_000_000:
            try:
                return datetime.fromtimestamp(number, tz=timezone.utc).isoformat()
            except (OverflowError, OSError, ValueError):
                return ""
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{10,16}(?:\.\d+)?", text):
        return parse_expiry(float(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        try:
            from zoneinfo import ZoneInfo
            parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Tehran"))
        except Exception:
            parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def extract_expiry(obj):
    """Read the explicit countdown fields used by DigiKala's Incredible Offers cards."""
    absolute_keys = ("ends_at", "endsAt", "deal_ends_at", "dealEndsAt", "expires_at", "expiresAt")
    seconds_keys = ("ends_in_seconds", "endsInSeconds", "remaining_seconds", "remainingSeconds")
    nodes = list(walk_dicts(obj))
    for node in nodes:
        for key in absolute_keys:
            expiry = parse_expiry(node.get(key))
            if expiry:
                return expiry
    now = datetime.now(timezone.utc)
    for node in nodes:
        for key in seconds_keys:
            try:
                seconds = float(node.get(key))
            except (TypeError, ValueError, OverflowError):
                seconds = -1
            if 0 <= seconds <= 7 * 24 * 3600:
                return (now + timedelta(seconds=seconds)).isoformat()
    return ""


def _product_id(node):
    raw = node.get("product_id") or node.get("id")
    if isinstance(raw, (str, int)) and str(raw).isdigit():
        # Product IDs are accepted only alongside product-like card fields.
        if any(key in node for key in ("title_fa", "product_title", "title", "default_variant", "variants", "is_incredible")):
            return f"dkp-{int(raw)}"
    url = node.get("url") or node.get("product_url") or node.get("web_url")
    if isinstance(url, dict):
        url = url.get("url") or url.get("uri")
    if isinstance(url, str):
        match = re.search(r"/product/(dkp-\d+)", url)
        if match:
            return match.group(1)
    return ""


def _mcp_call_incredible_offers_page(page):
    """Ask the public Digikala MCP feed for cards with the site's countdown metadata."""
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": page,
        "method": "tools/call",
        "params": {
            "name": "incredible_offers",
            "arguments": {
                "limit": 30,
                "page": page,
                "sort": "biggest_discount",
                "section": "incredible",
                "only_marketable": True,
            },
        },
    }).encode("utf-8")
    request = Request(
        "https://digikala-mcp.mmdju.workers.dev/mcp",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "OfferChin-Expiry-Monitor/1.0",
        },
    )
    with urlopen(request, timeout=25) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise RuntimeError("Digikala MCP response exceeded 2 MB")
    text = raw.decode("utf-8").strip()
    data_lines = [
        line[5:].strip()
        for line in text.splitlines()
        if line.startswith("data:") and line[5:].strip() and line[5:].strip() != "[DONE]"
    ]
    if data_lines:
        text = data_lines[-1]
    envelope = json.loads(text)
    if envelope.get("error"):
        raise RuntimeError(str(envelope["error"])[:180])
    result = envelope.get("result", envelope)
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict) or item.get("type") != "text":
                    continue
                raw_text = str(item.get("text") or "").strip()
                if not raw_text:
                    continue
                try:
                    parsed = json.loads(raw_text)
                    if isinstance(parsed, dict):
                        return parsed
                except ValueError:
                    continue
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
    if isinstance(result, dict):
        return result
    raise RuntimeError("Digikala MCP returned an unexpected response shape")


def fetch_mcp_offer_expiries():
    """Return exact offer deadlines exposed by Digikala's live deal-card feed."""
    results = {}
    for page in range(1, DEAL_LIST_PAGES + 1):
        try:
            payload = _mcp_call_incredible_offers_page(page)
        except Exception as exc:
            print(f"EXPIRY_MCP_FAILED page={page} error={type(exc).__name__} detail={str(exc)[:140]!r}")
            break
        page_count = 0
        for node in walk_dicts(payload):
            pid = _product_id(node)
            if not pid:
                continue
            expiry = extract_expiry(node)
            if expiry:
                results[pid] = expiry
                page_count += 1
        print(f"EXPIRY_MCP_PAGE page={page} products_with_deadlines={page_count}")
        if not payload:
            break
    print(f"EXPIRY_MCP_SUMMARY products_with_deadlines={len(results)}")
    return results


def fetch_direct_api_offer_expiries():
    """Fallback for direct API responses that carry the same optional deadline fields."""
    results = {}
    for page in range(1, DEAL_LIST_PAGES + 1):
        params = urlencode({"page": page, "q": ""})
        request = Request(
            f"{FEED_URL}?{params}",
            headers={
                "User-Agent": "OfferChin-Expiry-Monitor/1.0",
                "Accept": "application/json",
                "Referer": "https://www.digikala.com/",
            },
        )
        try:
            with urlopen(request, timeout=HTTP_TIMEOUT) as response:
                if response.status != 200:
                    raise RuntimeError(f"Digikala feed HTTP {response.status}")
                raw = response.read(8_000_001)
            if len(raw) > 8_000_000:
                raise RuntimeError("Digikala feed response exceeded 8 MB")
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            print(f"EXPIRY_FEED_FAILED page={page} error={type(exc).__name__} detail={str(exc)[:140]!r}")
            break
        page_found = 0
        for node in walk_dicts(payload):
            pid = _product_id(node)
            if not pid:
                continue
            expiry = extract_expiry(node)
            if expiry:
                results[pid] = expiry
                page_found += 1
        print(f"EXPIRY_FEED_PAGE page={page} products_with_deadlines={page_found}")
    return results


def fetch_offer_expiries():
    """Prefer live MCP countdown fields, and fall back to the direct public feed."""
    results = fetch_mcp_offer_expiries()
    # Do not overwrite a countdown-based deadline with a weaker duplicate from another feed.
    for pid, expiry in fetch_direct_api_offer_expiries().items():
        results.setdefault(pid, expiry)
    return results

def _money_to_toman(raw, is_toman):
    if raw in (None, "", 0, "0"):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    value = value if is_toman else value / 10.0
    return max(0, int(round(value)))


def fetch_live_product_status(product_id):
    """Fail-safe fallback: detect a reverted price or out-of-stock state for an expiry-unknown post."""
    match = re.search(r"(?:dkp-)?(\d+)$", str(product_id or ""))
    if not match:
        return {}
    numeric_id = match.group(1)
    for version in ("v2", "v1"):
        request = Request(
            f"https://api.digikala.com/{version}/product/{numeric_id}/",
            headers={
                "User-Agent": "OfferChin-Expiry-Monitor/1.0",
                "Accept": "application/json",
                "Referer": "https://www.digikala.com/",
            },
        )
        try:
            with urlopen(request, timeout=HTTP_TIMEOUT) as response:
                if response.status != 200:
                    continue
                raw = response.read(5_000_001)
            if len(raw) > 5_000_000:
                continue
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            print(f"EXPIRY_PRODUCT_CHECK_FAILED product_id={product_id} api={version} error={type(exc).__name__}")
            continue
        candidates = []
        for node in walk_dicts(payload):
            raw_id = node.get("product_id") or node.get("id")
            if str(raw_id or "") != numeric_id:
                continue
            if not any(key in node for key in ("default_variant", "variants", "price", "title_fa", "product_title")):
                continue
            score = 0
            score += 4 if isinstance(node.get("default_variant"), dict) else 0
            score += 2 if isinstance(node.get("variants"), (list, dict)) else 0
            score += 1 if isinstance(node.get("price"), dict) else 0
            score += 1 if node.get("title_fa") or node.get("product_title") else 0
            candidates.append((score, node))
        if not candidates:
            continue
        product = max(candidates, key=lambda pair: pair[0])[1]
        variant = product.get("default_variant") if isinstance(product.get("default_variant"), dict) else {}
        if not variant:
            variants = product.get("variants")
            if isinstance(variants, dict):
                variants = list(variants.values())
            if isinstance(variants, list):
                variant = next((v for v in variants if isinstance(v, dict) and v.get("marketable") is True), {})
        variant = variant if isinstance(variant, dict) else {}
        price_obj = variant.get("price") if isinstance(variant.get("price"), dict) else {}
        if not price_obj:
            price_obj = product.get("price") if isinstance(product.get("price"), dict) else {}
        sources = (price_obj, variant, product)

        def first_price(keys, is_toman):
            for source in sources:
                for key in keys:
                    if source.get(key) is not None:
                        value = _money_to_toman(source.get(key), is_toman)
                        if value:
                            return value
            return None

        current = first_price(("selling_price_toman", "selling_price_tooman", "price_toman", "current_price_toman"), True)
        if current is None:
            current = first_price(("selling_price_rial", "price_rial", "current_price_rial"), False)
        if current is None:
            current = first_price(("selling_price", "discounted_price", "final_price", "price"), False)
        original = first_price(("rrp_price_toman", "original_price_toman", "list_price_toman"), True)
        if original is None:
            original = first_price(("rrp_price_rial", "original_price_rial", "list_price_rial"), False)
        if original is None:
            original = first_price(("rrp_price", "original_price", "regular_price", "list_price"), False)

        in_stock = None
        for node in (variant, product):
            for key in ("marketable", "has_stock", "is_in_stock", "isAvailable", "available"):
                if isinstance(node.get(key), bool):
                    in_stock = node[key]
                    break
            if in_stock is not None:
                break
            for key in ("availability", "stock_status", "status", "availability_status"):
                raw_status = str(node.get(key) or "").lower().replace("_", "").replace("-", "")
                if any(token in raw_status for token in ("outofstock", "soldout", "notavailable", "ناموجود")):
                    in_stock = False
                    break
                if any(token in raw_status for token in ("instock", "marketable", "available")):
                    in_stock = True
                    break
            if in_stock is not None:
                break
        return {"current_price": current, "original_price": original, "in_stock": in_stock, "api_version": version}
    return {}


def _read_state():
    if not STATE_PATH.exists():
        return {"published": {}, "last_published_at": ""}
    with STATE_PATH.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    if not isinstance(state, dict):
        raise ValueError("state.json must contain an object")
    state.setdefault("published", {})
    return state


def _write_state(state):
    temporary = STATE_PATH.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(STATE_PATH)


def _should_probe(record, now):
    telegram_done = record.get("expiry_status") in {"deleted", "already_absent"}
    bale_message_id = record.get("bale_message_id")
    bale_done = record.get("bale_expiry_status") in {"deleted", "already_absent"}
    if telegram_done and (not str(bale_message_id or "").isdigit() or bale_done):
        return False
    if record.get("expires_at") and not record.get("expiry_estimated"):
        return False
    last_raw = record.get("expiry_last_probed_at")
    try:
        last = datetime.fromisoformat(str(last_raw).replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = (now - last).total_seconds()
    except (TypeError, ValueError):
        elapsed = float("inf")
    interval = PROBE_INTERVAL_SECONDS if record.get("expiry_estimated") else UNKNOWN_PROBE_INTERVAL_SECONDS
    return elapsed >= interval



def _telegram_delete(message_id):
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
    body = urlencode({"chat_id": CHAT_ID, "message_id": int(message_id)}).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("ok") is True:
        return "deleted"
    description = str(payload.get("description") or "")
    if "message to delete not found" in description.lower() or "message_id_invalid" in description.lower():
        return "already_absent"
    raise RuntimeError(description[:180] or "Telegram deleteMessage failed")


def _bale_delete(message_id):
    if not BALE_BOT_TOKEN:
        raise RuntimeError("BALE_BOT_TOKEN missing")
    if not BALE_CHANNEL_ID:
        raise RuntimeError("BALE_CHANNEL_ID missing")
    url = f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/deleteMessage"
    body = urlencode({"chat_id": BALE_CHANNEL_ID, "message_id": int(message_id)}).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("ok") is True:
        return "deleted"
    description = str(payload.get("description") or "")
    if "message to delete not found" in description.lower() or "message_id_invalid" in description.lower():
        return "already_absent"
    raise RuntimeError(description[:180] or "Bale deleteMessage failed")


def _delete_expired_posts(published, now, mark_unknown=False):
    """Delete posts whose explicit deadline has passed; return state change and actual deletions."""
    changed = False
    deleted = 0
    for pid, rec in published.items():
        if not isinstance(rec, dict):
            continue
        expiry = parse_expiry(rec.get("expires_at"))
        if not expiry:
            if mark_unknown:
                for id_field, status_field in (
                    ("telegram_message_id", "expiry_status"),
                    ("bale_message_id", "bale_expiry_status"),
                ):
                    if not str(rec.get(id_field) or "").isdigit():
                        continue
                    if rec.get(status_field) not in {"deleted", "already_absent", "unknown"}:
                        rec[status_field] = "unknown"
                        changed = True
            continue
        expires_at = datetime.fromisoformat(expiry)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now < expires_at:
            if str(rec.get("telegram_message_id") or "").isdigit() and not rec.get("expiry_status"):
                rec["expiry_status"] = "tracked_estimated" if rec.get("expiry_estimated") else "tracked"
                changed = True
            if str(rec.get("bale_message_id") or "").isdigit() and not rec.get("bale_expiry_status"):
                rec["bale_expiry_status"] = "tracked_estimated" if rec.get("expiry_estimated") else "tracked"
                changed = True
            continue
        for platform, id_field, status_field, timestamp_field, delete_fn in (
            ("telegram", "telegram_message_id", "expiry_status", "expired_deleted_at", _telegram_delete),
            ("bale", "bale_message_id", "bale_expiry_status", "bale_expired_deleted_at", _bale_delete),
        ):
            raw_id = rec.get(id_field)
            if not str(raw_id or "").isdigit() or rec.get(status_field) in {"deleted", "already_absent"}:
                continue
            try:
                outcome = delete_fn(int(raw_id))
                rec[status_field] = outcome
                rec[timestamp_field] = now.isoformat()
                changed = True
                if outcome == "deleted":
                    deleted += 1
                print(f"EXPIRY_DELETE_OK platform={platform} product_id={pid} message_id={raw_id} outcome={outcome} expiry={expiry}")
            except Exception as exc:
                rec[status_field] = "delete_failed"
                error_text = str(exc)[:180]
                rec[f"{platform}_expiry_last_delete_error"] = f"{type(exc).__name__}: {error_text}"
                changed = True
                print(f"EXPIRY_DELETE_FAILED platform={platform} product_id={pid} message_id={raw_id} error={type(exc).__name__} detail={error_text[:160]!r}")
    return changed, deleted


def run():
    state = _read_state()
    published = state.get("published", {})
    if not isinstance(published, dict):
        raise ValueError("state.json published must be an object")
    now = datetime.now(timezone.utc)
    changed = False
    deleted = 0

    pre_changed, pre_deleted = _delete_expired_posts(published, now, mark_unknown=True)
    changed = changed or pre_changed
    deleted += pre_deleted
    if pre_changed:
        _write_state(state)
        print("EXPIRY_STATE_SAVED phase=known_deadline_cleanup")

    probe_candidates = [
        (pid, rec) for pid, rec in published.items()
        if isinstance(rec, dict)
        and (
            (str(rec.get("telegram_message_id") or "").isdigit() and rec.get("expiry_status") not in {"deleted", "already_absent"})
            or (str(rec.get("bale_message_id") or "").isdigit() and rec.get("bale_expiry_status") not in {"deleted", "already_absent"})
        )
        and _should_probe(rec, now)
    ]
    probe_candidates.sort(key=lambda pair: str(pair[1].get("expiry_last_probed_at") or ""))
    feed_last = parse_expiry(state.get("expiry_feed_last_checked_at"))
    feed_due = not feed_last or (now - datetime.fromisoformat(feed_last)).total_seconds() >= UNKNOWN_PROBE_INTERVAL_SECONDS
    live_expiries = {}
    if probe_candidates and feed_due:
        try:
            live_expiries = fetch_offer_expiries()
        except Exception as exc:
            print(f"EXPIRY_FEED_LOOKUP_FAILED error={type(exc).__name__} detail={str(exc)[:140]!r}")
        state["expiry_feed_last_checked_at"] = now.isoformat()
        changed = True
        for pid, rec in published.items():
            if not isinstance(rec, dict) or (rec.get("expires_at") and not rec.get("expiry_estimated")):
                continue
            live = live_expiries.get(pid)
            if live:
                rec["expires_at"] = live
                rec["expiry_source"] = "digikala_live_deals_feed"
                rec["expiry_estimated"] = False
                if rec.get("expiry_status") not in {"deleted", "already_absent"}:
                    rec["expiry_status"] = "tracked"
                if str(rec.get("bale_message_id") or "").isdigit() and rec.get("bale_expiry_status") not in {"deleted", "already_absent"}:
                    rec["bale_expiry_status"] = "tracked"
                changed = True
                print(f"EXPIRY_TRACKED product_id={pid} expires_at={live}")

    product_probe_count = 0
    max_product_probes = 3
    max_probe_candidates = max_product_probes * 2
    for pid, rec in probe_candidates[:max_probe_candidates]:
        if not isinstance(rec, dict) or (rec.get("expires_at") and not rec.get("expiry_estimated")):
            continue
        rec["expiry_last_probed_at"] = now.isoformat()
        changed = True
        if product_probe_count >= max_product_probes:
            continue
        product_probe_count += 1
        snapshot = fetch_live_product_status(pid)
        rec["expiry_last_product_check_at"] = now.isoformat()
        if not snapshot:
            continue
        current = snapshot.get("current_price")
        posted = rec.get("posted_current_price")
        stock = snapshot.get("in_stock")
        reason = ""
        if stock is False:
            reason = "out_of_stock"
        else:
            try:
                posted_value = int(posted)
                current_value = int(current)
                if posted_value > 0 and current_value > posted_value * 1.05:
                    reason = "price_reverted"
            except (TypeError, ValueError, OverflowError):
                pass
        rec["last_seen_current_price"] = current
        rec["last_seen_in_stock"] = stock
        if reason:
            rec["expires_at"] = now.isoformat()
            rec["expiry_source"] = "live_product_stock_or_price"
            rec["expiry_estimated"] = False
            rec["expiry_reason"] = reason
            rec["expiry_status"] = "expired_confirmed"
            changed = True
            print(f"EXPIRY_CONFIRMED_BY_LIVE_PRODUCT product_id={pid} reason={reason} current_price={current}")

    post_changed, post_deleted = _delete_expired_posts(published, now, mark_unknown=True)
    changed = changed or post_changed
    deleted += post_deleted
    if changed:
        _write_state(state)
    backlog = max(0, len(probe_candidates) - min(len(probe_candidates), max_probe_candidates))
    print(
        f"EXPIRY_MONITOR_SUMMARY tracked={len(published)} probed={product_probe_count} "
        f"probe_backlog={backlog} deleted_now={deleted} state_changed={changed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
