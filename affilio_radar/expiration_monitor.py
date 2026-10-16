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


def fetch_offer_expiries():
    """Fetch the current first deal pages; on network/API failure return no inferred deadlines."""
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
            print(f"EXPIRY_FEED_FAILED page={page} error={type(exc).__name__} detail={str(exc)[:160]!r}")
            # A partial feed is not evidence that an offer expired. Keep deadlines already stored.
            return {}
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
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        if isinstance(data, dict):
            product_rows = data.get("products") or data.get("items")
            if isinstance(product_rows, list) and not product_rows:
                break
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
    if record.get("expiry_status") == "deleted" or record.get("expiry_status") == "already_absent":
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


def run():
    state = _read_state()
    published = state.get("published", {})
    if not isinstance(published, dict):
        raise ValueError("state.json published must be an object")
    now = datetime.now(timezone.utc)
    needs_probe = [
        (pid, rec) for pid, rec in published.items()
        if isinstance(rec, dict)
        and str(rec.get("telegram_message_id") or "").isdigit()
        and _should_probe(rec, now)
    ]
    changed = False
    if needs_probe:
        live_expiries = fetch_offer_expiries()
        if live_expiries:
            for pid, rec in needs_probe:
                live = live_expiries.get(pid)
                if live and (not rec.get("expires_at") or rec.get("expiry_estimated")):
                    rec["expires_at"] = live
                    rec["expiry_source"] = "digikala_incredible_offers_api"
                    rec["expiry_estimated"] = False
                    rec["expiry_status"] = "tracked"
                    changed = True
                    print(f"EXPIRY_TRACKED product_id={pid} expires_at={live}")
        for pid, rec in needs_probe:
            rec["expiry_last_probed_at"] = now.isoformat()
            changed = True
            # If no exact deadline is available, verify live stock/price as a conservative fallback.
            if not rec.get("expires_at") or rec.get("expiry_estimated"):
                snapshot = fetch_live_product_status(pid)
                rec["expiry_last_product_check_at"] = now.isoformat()
                if snapshot:
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

    deleted = 0
    for pid, rec in published.items():
        if not isinstance(rec, dict) or rec.get("expiry_status") in {"deleted", "already_absent"}:
            continue
        raw_message_id = rec.get("telegram_message_id")
        if not str(raw_message_id or "").isdigit():
            continue
        raw_expiry = rec.get("expires_at")
        expiry = parse_expiry(raw_expiry)
        if not expiry:
            if rec.get("expiry_status") != "unknown":
                rec["expiry_status"] = "unknown"
                changed = True
            continue
        expires_at = datetime.fromisoformat(expiry)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now < expires_at:
            if not rec.get("expiry_status"):
                rec["expiry_status"] = "tracked_estimated" if rec.get("expiry_estimated") else "tracked"
                changed = True
            continue
        try:
            outcome = _telegram_delete(int(raw_message_id))
            rec["expiry_status"] = outcome
            rec["expired_deleted_at"] = now.isoformat()
            changed = True
            deleted += 1
            print(f"EXPIRY_DELETE_OK product_id={pid} message_id={raw_message_id} outcome={outcome} expiry={expiry}")
        except Exception as exc:
            rec["expiry_status"] = "delete_failed"
            rec["expiry_last_delete_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
            changed = True
            print(f"EXPIRY_DELETE_FAILED product_id={pid} message_id={raw_message_id} error={type(exc).__name__} detail={str(exc)[:160]!r}")

    if changed:
        _write_state(state)
    print(f"EXPIRY_MONITOR_SUMMARY tracked={len(published)} probed={len(needs_probe)} deleted_now={deleted} state_changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
