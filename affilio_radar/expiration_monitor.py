#!/usr/bin/env python3
"""Keep OfferChin deal posts live only when their absolute deadline is verified.

Expired offers and posts whose deadlines are missing, estimated, or otherwise
unverifiable are deleted from Telegram and Bale. If deletion temporarily fails,
the purchase button is disabled where possible and deletion is retried on later
cleanup runs. Public-history auditing also removes legacy offer captions without
a recoverable absolute deadline while preserving ordinary channel announcements.
"""
from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from urllib.error import HTTPError
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
BOT_API_MIN_GAP_SECONDS = 1.1
PROBE_INTERVAL_SECONDS = 900
UNKNOWN_PROBE_INTERVAL_SECONDS = 900
# Keep deletion safety independent from the caption's displayed countdown.
# A post is removed up to ten minutes before the verified deadline.
POST_REMOVAL_BUFFER_MINUTES = 10
LIVE_DEADLINE_SYNC_INTERVAL_SECONDS = 15 * 60


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


def fetch_mcp_offer_candidates(page_numbers=None):
    """Return verified countdowns and offer cards, optionally scanning a rotating subset of pages."""
    expiries = {}
    candidate_nodes = {}
    if page_numbers is None:
        pages = list(range(1, DEAL_LIST_PAGES + 1))
    else:
        pages = []
        for raw_page in page_numbers:
            try:
                page_number = int(raw_page)
            except (TypeError, ValueError, OverflowError):
                continue
            if 1 <= page_number <= DEAL_LIST_PAGES and page_number not in pages:
                pages.append(page_number)
        if not pages:
            pages = list(range(1, DEAL_LIST_PAGES + 1))
    print(f"EXPIRY_MCP_SCAN_PAGES pages={pages}")
    for page in pages:
        try:
            payload = _mcp_call_incredible_offers_page(page)
        except Exception as exc:
            print(f"EXPIRY_MCP_FAILED page={page} error={type(exc).__name__} detail={str(exc)[:140]!r}")
            break
        page_candidates = 0
        for node in walk_dicts(payload):
            pid = _product_id(node)
            if not pid:
                continue
            # Only use a real product/offer card as the deadline source. Nested
            # variant/price dictionaries may repeat the product ID and carry unrelated
            # expiry-like fields; letting them overwrite a card's deadline was unsafe.
            title = node.get("title_fa") or node.get("product_title") or node.get("title")
            if not title:
                continue
            raw_url = node.get("url") or node.get("product_url") or node.get("web_url")
            if isinstance(raw_url, dict):
                raw_url = raw_url.get("uri") or raw_url.get("url") or ""
            product_shaped = any(
                key in node
                for key in ("default_variant", "variants", "price", "status", "product_type", "is_incredible")
            )
            if not raw_url and not product_shaped:
                continue
            old = candidate_nodes.get(pid)
            if old is None or len(node) > len(old):
                candidate_nodes[pid] = dict(node)
                page_candidates += 1
        page_count = 0
        for pid, card in candidate_nodes.items():
            expiry = extract_expiry(card)
            if expiry:
                expiries[pid] = expiry
                card["deal_expires_at"] = expiry
                page_count += 1
        print(
            f"EXPIRY_MCP_PAGE page={page} products_with_deadlines={page_count} "
            f"offer_cards={page_candidates}"
        )
        if not payload:
            break
    print(
        f"EXPIRY_MCP_SUMMARY products_with_deadlines={len(expiries)} "
        f"offer_cards={len(candidate_nodes)}"
    )
    return expiries, list(candidate_nodes.values())


def fetch_mcp_offer_expiries():
    """Return exact offer deadlines exposed by Digikala's live deal-card feed."""
    expiries, _ = fetch_mcp_offer_candidates()
    return expiries


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
        candidate_nodes = {}
        for node in walk_dicts(payload):
            pid = _product_id(node)
            title = node.get("title_fa") or node.get("product_title") or node.get("title")
            if not pid or not title:
                continue
            raw_url = node.get("url") or node.get("product_url") or node.get("web_url")
            if isinstance(raw_url, dict):
                raw_url = raw_url.get("uri") or raw_url.get("url") or ""
            if not raw_url and not any(key in node for key in ("default_variant", "variants", "price", "status", "product_type", "is_incredible")):
                continue
            old = candidate_nodes.get(pid)
            if old is None or len(node) > len(old):
                candidate_nodes[pid] = dict(node)
        for pid, card in candidate_nodes.items():
            expiry = extract_expiry(card)
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



def sync_live_offer_deadlines(published, live_expiries, now):
    """Reconcile every still-visible tracked post with the latest verified deal-card deadline."""
    summary = {"matched": 0, "updated": 0, "unchanged": 0, "missing_from_feed": 0, "skipped": 0}
    terminal = {"deleted", "already_absent"}
    for pid, rec in _iter_post_records(published):
        if not isinstance(rec, dict):
            summary["skipped"] += 1
            continue
        platforms = []
        telegram_id = str(rec.get("telegram_message_id") or "")
        bale_id = str(rec.get("bale_message_id") or "")
        if telegram_id.isdigit() and rec.get("expiry_status") not in terminal:
            platforms.append("telegram")
        if bale_id.isdigit() and rec.get("bale_expiry_status") not in terminal:
            platforms.append("bale")
        if not platforms:
            continue

        raw_live = live_expiries.get(str(pid))
        live = parse_expiry(raw_live)
        if not live:
            summary["missing_from_feed"] += 1
            continue
        summary["matched"] += 1
        previous = parse_expiry(rec.get("expires_at"))
        try:
            previous_dt = datetime.fromisoformat(previous) if previous else None
            live_dt = datetime.fromisoformat(live)
        except ValueError:
            previous_dt = None
            live_dt = None
        delta_seconds = (live_dt - previous_dt).total_seconds() if previous_dt and live_dt else None
        must_update = (
            not previous_dt
            or bool(rec.get("expiry_estimated"))
            or rec.get("expiry_source") != "digikala_live_deals_feed"
            or (delta_seconds is not None and abs(delta_seconds) >= 60)
        )
        if not must_update:
            summary["unchanged"] += 1
            continue

        rec["expires_at"] = live
        rec["expiry_source"] = "digikala_live_deals_feed"
        rec["expiry_estimated"] = False
        rec["expiry_last_live_sync_at"] = now.isoformat()
        for platform in platforms:
            status_field = "expiry_status" if platform == "telegram" else "bale_expiry_status"
            if rec.get(status_field) not in terminal:
                rec[status_field] = "tracked"
        rec.pop("expiry_reason", None)
        summary["updated"] += 1
        delta_label = "unknown" if delta_seconds is None else f"{int(delta_seconds):+d}"
        print(
            f"EXPIRY_DEADLINE_SYNC product_id={pid} previous={previous or 'missing'} "
            f"live={live} delta_seconds={delta_label}"
        )
    return summary



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
    terminal = {"deleted", "already_absent", "expired_marked", "deadline_unavailable_marked", "deadline_unavailable_delete_failed"}
    telegram_done = record.get("expiry_status") in terminal
    bale_message_id = record.get("bale_message_id")
    bale_done = record.get("bale_expiry_status") in terminal
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



def _decode_delete_response(response):
    raw = response.read(65536)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {}


def _delete_error_description(exc):
    """Read a safe provider error description from an HTTP error body if present."""
    try:
        raw = exc.read(65536)
    except Exception:
        raw = b""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        payload = {}
    description = str(payload.get("description") or payload.get("message") or "").strip()
    if description:
        return description[:180]
    return f"HTTP {getattr(exc, 'code', '')}: {getattr(exc, 'reason', '')}"[:180]


def _is_message_absent(description):
    text = str(description or "").lower()
    return any(marker in text for marker in (
        "message to delete not found",
        "message to edit not found",
        "message not found",
        "message_id_invalid",
    ))


def _pace_bot_api():
    """Conservatively space channel mutations to reduce the risk of provider rate limits."""
    time.sleep(BOT_API_MIN_GAP_SECONDS)


def _telegram_delete(message_id):
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
    body = urlencode({"chat_id": CHAT_ID, "message_id": int(message_id)}).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    _pace_bot_api()
    try:
        with urlopen(request, timeout=20) as response:
            payload = _decode_delete_response(response)
    except HTTPError as exc:
        description = _delete_error_description(exc)
        if _is_message_absent(description):
            return "already_absent"
        raise RuntimeError(description) from None
    if payload.get("ok") is True:
        return "deleted"
    description = str(payload.get("description") or "Telegram deleteMessage failed")
    if _is_message_absent(description):
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
    _pace_bot_api()
    try:
        with urlopen(request, timeout=20) as response:
            payload = _decode_delete_response(response)
    except HTTPError as exc:
        description = _delete_error_description(exc)
        if _is_message_absent(description):
            return "already_absent"
        raise RuntimeError(description) from None
    if payload.get("ok") is True:
        return "deleted"
    description = str(payload.get("description") or "Bale deleteMessage failed")
    if _is_message_absent(description):
        return "already_absent"
    raise RuntimeError(description[:180] or "Bale deleteMessage failed")



PERSIAN_MONTHS = {
    "فروردین": 1, "اردیبهشت": 2, "خرداد": 3, "تیر": 4,
    "مرداد": 5, "شهریور": 6, "مهر": 7, "آبان": 8,
    "آذر": 9, "دی": 10, "بهمن": 11, "اسفند": 12,
}
PERSIAN_TO_ASCII = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)
PUBLIC_HISTORY_MAX_PAGES = max(1, min(10, int(os.getenv("AFFILIO_PUBLIC_HISTORY_PAGES", "6"))))
TELEGRAM_CHANNEL_USERNAME = CHAT_ID.lstrip("@") if CHAT_ID.startswith("@") else "OfferChin"


def _normalize_digits(value):
    return str(value or "").translate(PERSIAN_TO_ASCII)


def jalali_to_gregorian(jy, jm, jd):
    """Convert a Solar Hijri date to Gregorian."""
    jy += 1595
    days = -355668 + (365 * jy) + (jy // 33) * 8 + ((jy % 33 + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += (jm - 7) * 30 + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        gy += 100 * ((days - 1) // 36524)
        days = (days - 1) % 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0)
    month_lengths = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and gd > month_lengths[gm - 1]:
        gd -= month_lengths[gm - 1]
        gm += 1
    if gm > 12:
        raise ValueError("Invalid Jalali date")
    return gy, gm, gd


def extract_jalali_deadline(caption_text):
    """Extract an explicit absolute deadline from older Persian-language captions."""
    text = _normalize_digits(caption_text).replace("\u00a0", " ")
    month_pattern = "|".join(PERSIAN_MONTHS.keys())
    pattern = re.compile(
        rf"(?:پایان\s*(?:تخفیف|آفر)|اتمام\s*(?:تخفیف|آفر)|مهلت\s*(?:تخفیف|آفر))"
        rf"\s*[:：]?\s*"
        rf"(?:(?:شنبه|یکشنبه|دوشنبه|سه‌شنبه|چهارشنبه|پنجشنبه|جمعه)\s+)?"
        rf"(\d{{1,2}})\s+({month_pattern})\s+(\d{{4}})"
        rf"\s*[,،]?\s*ساعت\s*(\d{{1,2}})[:٫](\d{{2}})"
    )
    match = pattern.search(text)
    if not match:
        return None
    day, month_name, year, hour, minute = match.groups()
    day, month, year, hour, minute = int(day), PERSIAN_MONTHS[month_name], int(year), int(hour), int(minute)
    if not 1 <= day <= (31 if month <= 6 else 30) or not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    try:
        gy, gm, gd = jalali_to_gregorian(year, month, day)
        tehran = datetime(gy, gm, gd, hour, minute, tzinfo=ZoneInfo("Asia/Tehran"))
        return tehran.astimezone(timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def _persian_number(value):
    return f"{int(value):,}".translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬"))


def _remaining_label(deadline, now):
    # Keep repaired legacy captions consistent with the five-minute countdown buffer.
    seconds = (deadline - timedelta(minutes=COUNTDOWN_DISPLAY_BUFFER_MINUTES) - now).total_seconds()
    if seconds <= 0:
        return f"حداکثر {_persian_number(COUNTDOWN_DISPLAY_BUFFER_MINUTES)} دقیقه"
    minutes = max(1, int((seconds + 59) // 60))
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{_persian_number(hours)} ساعت و {_persian_number(mins)} دقیقه"
    if hours:
        return f"{_persian_number(hours)} ساعت"
    return f"{_persian_number(mins)} دقیقه"


def _extract_legacy_caption_fields(caption_text):
    """Read the core fields needed to safely rebuild a legacy caption."""
    text = " ".join(str(caption_text or "").split())
    title_match = re.search(r"🛍️\s*(.+?)\s*(?=💚\s*قیمت\s*ویژه)", text)
    title = title_match.group(1).strip(" :：") if title_match else ""
    text = _normalize_digits(text)
    current_match = re.search(r"قیمت\s*ویژه\s*[:：]\s*(?:💰\s*)?([\d٬,٫\s]+?)\s*تومان", text)
    original_match = re.search(r"قیمت\s*اصلی\s*[:：]\s*([\d٬,٫\s]+?)\s*تومان", text)
    discount_match = re.search(r"(\d{1,3})\s*٪\s*تخفیف", text)

    def as_int(match):
        if not match:
            return None
        raw = re.sub(r"\D", "", match.group(1))
        try:
            return int(raw) if raw else None
        except (TypeError, ValueError):
            return None

    return {
        "title": title,
        "current_price": as_int(current_match),
        "original_price": as_int(original_match),
        "discount_percent": as_int(discount_match),
    }


def _build_legacy_repaired_caption(fields, deadline, now):
    """Rebuild a pre-tracker caption with the current link, underline, and countdown format."""
    title = html.escape(str(fields.get("title") or "پیشنهاد ویژه").strip())
    parts = [
        "<b>🔥 پیشنهاد شگفت‌انگیز دیجی‌کالا</b>",
        "",
        f"<b>🛍️ {title}</b>",
        "",
    ]
    current = fields.get("current_price")
    original = fields.get("original_price")
    discount = fields.get("discount_percent")
    if current:
        parts.append(f"<b><u>💚 قیمت ویژه: 💰 {_persian_number(current)} تومان</u></b>")
    if discount:
        parts.append(f"<b><u>⚡️ {_persian_number(discount)}٪ تخفیف</u></b>")
    if original and current and original > current:
        parts += ["", f"<b>🏷️ قیمت اصلی: <s>{_persian_number(original)} تومان</s></b>"]
    if deadline:
        parts += ["", f"<b>⏳ {_remaining_label(deadline, now)} مانده به پایان تخفیف</b>"]
    parts += [
        "",
        '<a href="https://telegram.me/OfferChin">عضویت در کانال OfferChin</a>',
        "",
        "<b>👇 برای دیدن جزئیات، دکمهٔ زیر رو بزن.</b>",
    ]
    caption = "\n".join(parts)
    if len(caption) > 1024:
        parts[2] = f"<b>🛍️ {html.escape(str(fields.get('title') or 'پیشنهاد ویژه')[:90])}…</b>"
        caption = "\n".join(parts)
    return caption


def _caption_needs_repair(caption_html, caption_text, fields, deadline):
    """Avoid re-editing a legacy message once the desired formatting is already present."""
    if "عضویت در کانال OfferChin" not in caption_text or "t.me/OfferChin" in caption_text:
        return True
    soup = BeautifulSoup(caption_html or "", "html.parser")
    underline_texts = [" ".join(node.get_text(" ", strip=True).split()) for node in soup.find_all("u")]
    current = fields.get("current_price")
    discount = fields.get("discount_percent")
    if current:
        expected_amount = _persian_number(current)
        if not any("قیمت ویژه" in value and "تومان" in value and expected_amount in value for value in underline_texts):
            return True
    if discount:
        expected_discount = _persian_number(discount) + "٪"
        if not any("⚡️" in value and "تخفیف" in value and expected_discount in value for value in underline_texts):
            return True
    if deadline and "زمان باقی‌مانده" not in caption_text:
        return True
    if "پایان تخفیف" in caption_text:
        return True
    return False


def _fetch_public_channel_page(before=None):
    username = re.sub(r"[^A-Za-z0-9_]", "", TELEGRAM_CHANNEL_USERNAME) or "OfferChin"
    url = f"https://t.me/s/{username}"
    if before:
        url += f"?before={int(before)}"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; OfferChinExpiryBot/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
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
        caption_html = caption_node.decode_contents() if caption_node else ""
        results[message_id] = {
            "message_id": message_id,
            "caption_text": caption_text,
            "caption_html": caption_html,
        }
    return results


def fetch_public_channel_posts(max_pages=None):
    """Fetch public-channel history by paging backward from Telegram's public preview."""
    max_pages = max_pages or PUBLIC_HISTORY_MAX_PAGES
    all_posts = {}
    before = None
    last_oldest = None
    for page in range(1, max_pages + 1):
        try:
            page_posts = _fetch_public_channel_page(before)
        except Exception as exc:
            print(f"PUBLIC_HISTORY_PAGE_FAILED page={page} error={type(exc).__name__} detail={str(exc)[:120]!r}")
            if page == 1:
                raise
            break
        if not page_posts:
            print(f"PUBLIC_HISTORY_PAGE_EMPTY page={page} before={before or 'latest'}")
            break
        all_posts.update(page_posts)
        oldest = min(page_posts)
        print(f"PUBLIC_HISTORY_PAGE_OK page={page} messages={len(page_posts)} oldest_id={oldest} newest_id={max(page_posts)}")
        if oldest <= 1 or oldest == last_oldest:
            break
        last_oldest = oldest
        before = oldest
        time.sleep(0.15)
    print(f"PUBLIC_HISTORY_SUMMARY messages_scanned={len(all_posts)} pages_limit={max_pages}")
    return all_posts


def _telegram_edit_caption(message_id, caption, remove_purchase_button=False):
    """Edit a public channel caption while retaining or removing its purchase button."""
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    payload = {
        "chat_id": CHAT_ID,
        "message_id": int(message_id),
        "caption": caption,
        "parse_mode": "HTML",
    }
    if remove_purchase_button:
        payload["reply_markup"] = json.dumps({"inline_keyboard": []})
    endpoint = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageCaption"
    for attempt in range(4):
        request = Request(
            endpoint,
            data=urlencode(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        _pace_bot_api()
        try:
            with urlopen(request, timeout=HTTP_TIMEOUT) as response:
                result = _decode_delete_response(response)
        except HTTPError as exc:
            description = _delete_error_description(exc)
            if _is_message_absent(description):
                return "already_absent"
            if "retry after" in description.lower() and attempt < 3:
                wait_match = re.search(r"retry after\s+(\d+)", description.lower())
                pause = min(60, int(wait_match.group(1)) if wait_match else 5)
                print(f"TELEGRAM_HISTORY_EDIT_RATE_LIMIT message_id={message_id} retry_after={pause}s")
                time.sleep(pause + 1)
                continue
            raise RuntimeError(description) from None
        if result.get("ok"):
            return "edited"
        description = str(result.get("description") or "Telegram editMessageCaption failed")
        if _is_message_absent(description):
            return "already_absent"
        if "retry after" in description.lower() and attempt < 3:
            wait_match = re.search(r"retry after\s+(\d+)", description.lower())
            pause = min(60, int(wait_match.group(1)) if wait_match else 5)
            time.sleep(pause + 1)
            continue
        raise RuntimeError(description[:180])
    raise RuntimeError("Telegram editMessageCaption retry limit reached")


def _telegram_mark_expired(message_id, title):
    title = html.escape(str(title or "پیشنهاد ویژه").strip()[:140])
    caption = (
        "<b>⛔ مهلت این آفر به پایان رسیده و دکمهٔ خرید غیرفعال شده است.</b>\n\n"
        f"<b>🛍️ {title}</b>\n\n"
        '<a href="https://telegram.me/OfferChin">عضویت در کانال OfferChin</a>'
    )
    return _telegram_edit_caption(message_id, caption, remove_purchase_button=True)


def _telegram_mark_deadline_unavailable(message_id, title):
    title = html.escape(str(title or "پیشنهاد ویژه").strip()[:140])
    caption = (
        "<b>⚠️ زمان پایان این تخفیف قابل تأیید نیست؛ دکمهٔ خرید غیرفعال شده است.</b>\n\n"
        f"<b>🛍️ {title}</b>\n\n"
        '<a href="https://telegram.me/OfferChin">عضویت در کانال OfferChin</a>'
    )
    return _telegram_edit_caption(message_id, caption, remove_purchase_button=True)


def _bale_mark_deadline_unavailable(message_id, title):
    if not BALE_BOT_TOKEN:
        raise RuntimeError("BALE_BOT_TOKEN missing")
    if not BALE_CHANNEL_ID:
        raise RuntimeError("BALE_CHANNEL_ID missing")
    safe_title = str(title or "پیشنهاد ویژه").strip()[:140]
    caption = (
        "⚠️ زمان پایان این تخفیف قابل تأیید نیست؛ دکمهٔ خرید غیرفعال شده است.\n\n"
        f"🛍️ {safe_title}\n\n"
        "[عضویت در کانال OfferChin](https://ble.ir/OfferChin)"
    )
    payload = {
        "chat_id": BALE_CHANNEL_ID,
        "message_id": int(message_id),
        "caption": caption,
        "reply_markup": json.dumps({"inline_keyboard": []}),
    }
    request = Request(
        f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/editMessageCaption",
        data=urlencode(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    _pace_bot_api()
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT) as response:
            result = _decode_delete_response(response)
    except HTTPError as exc:
        description = _delete_error_description(exc)
        if _is_message_absent(description):
            return "already_absent"
        raise RuntimeError(description) from None
    if result.get("ok") is True:
        return "edited"
    description = str(result.get("description") or "Bale editMessageCaption failed")
    if _is_message_absent(description):
        return "already_absent"
    raise RuntimeError(description[:180] or "Bale editMessageCaption failed")


def _looks_like_offer_post(caption_text):
    """Recognize OfferChin promo captions even when some fields cannot be parsed."""
    text = str(caption_text or "").lower().replace("ي", "ی").replace("ك", "ک")
    compact = re.sub(r"[\s\u200c\u200f]+", "", text)
    return (
        "پیشنهادشگفتانگیزدیجیکالا" in compact
        or ("قیمتویژه" in compact and "تخفیف" in compact)
    )


def _iter_post_records(published):
    """Yield current and historical message records so previous campaigns remain cleanable."""
    for product_id, record in (published or {}).items():
        if not isinstance(record, dict):
            continue
        yield product_id, record
        history = record.get("post_history")
        if isinstance(history, list):
            for previous in history:
                if isinstance(previous, dict):
                    yield product_id, previous


def audit_public_channel_history(published, now=None, posts=None):
    """Delete expired untracked public posts and repair active legacy captions in place."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    try:
        posts = posts if posts is not None else fetch_public_channel_posts()
    except Exception as exc:
        print(f"PUBLIC_HISTORY_SCAN_FAILED error={type(exc).__name__} detail={str(exc)[:140]!r}")
        return False, 0, 0, 0, 0

    tracked_by_message_id = {}
    for _product_id, record in _iter_post_records(published):
        if str(record.get("telegram_message_id") or "").isdigit():
            tracked_by_message_id[int(record["telegram_message_id"])] = record

    changed = False
    deleted = marked_expired = reformatted = found_expired = 0
    for message_id, post in sorted(posts.items()):
        caption_text = str(post.get("caption_text") or "")
        caption_html = str(post.get("caption_html") or "")
        if not caption_text.strip():
            continue
        deadline = extract_jalali_deadline(caption_text)
        record = tracked_by_message_id.get(int(message_id))
        removal_deadline = deadline - timedelta(minutes=POST_REMOVAL_BUFFER_MINUTES) if deadline else None
        if deadline and removal_deadline <= now:
            found_expired += 1
            outcome = ""
            delete_error = ""
            try:
                outcome = _telegram_delete(int(message_id))
            except Exception as exc:
                delete_error = f"{type(exc).__name__}: {str(exc)[:180]}"
                print(f"PUBLIC_HISTORY_DELETE_FAILED message_id={message_id} error={delete_error!r}")
            if outcome == "deleted":
                deleted += 1
                print(
                    f"PUBLIC_HISTORY_EXPIRY_BUFFER_DELETED message_id={message_id} "
                    f"expiry={deadline.isoformat()} remove_at={removal_deadline.isoformat()}"
                )
                if record is not None:
                    record["expiry_status"] = "deleted"
                    record["expired_deleted_at"] = now.isoformat()
                    changed = True
                continue

            # The public page confirms the post is present; if deletion is rejected, disable its buy button.
            try:
                marked = _telegram_mark_expired(
                    int(message_id),
                    record.get("title") if record else _extract_legacy_caption_fields(caption_text).get("title"),
                )
                if marked == "edited":
                    marked_expired += 1
                    print(f"PUBLIC_HISTORY_EXPIRED_MARKED message_id={message_id} reason=delete_rejected_or_api_disagreement")
                    if record is not None:
                        record["expiry_status"] = "expired_marked"
                        record["expired_marked_at"] = now.isoformat()
                        record["expiry_last_delete_error"] = delete_error or "Delete API reported absent while public history still showed the post"
                        changed = True
                elif marked == "already_absent":
                    print(f"PUBLIC_HISTORY_API_ABSENT message_id={message_id} public_preview_may_be_stale")
                    if record is not None:
                        record["expiry_status"] = "already_absent"
                        changed = True
            except Exception as exc:
                print(f"PUBLIC_HISTORY_MARK_EXPIRED_FAILED message_id={message_id} error={type(exc).__name__} detail={str(exc)[:140]!r}")
                if record is not None:
                    record["expiry_status"] = "delete_failed"
                    record["expiry_last_delete_error"] = delete_error or f"{type(exc).__name__}: {str(exc)[:140]}"
                    changed = True
            continue

        # Tracked messages are evaluated from state, where their verified deadline lives.
        if record is not None:
            continue
        fields = _extract_legacy_caption_fields(caption_text)
        if deadline is None:
            # Even partially malformed legacy promo captions must not remain live
            # when their absolute deadline cannot be verified.
            if not _looks_like_offer_post(caption_text):
                continue
            try:
                outcome = _telegram_delete(int(message_id))
                if outcome == "deleted":
                    deleted += 1
                    print(f"PUBLIC_HISTORY_DEADLINE_UNAVAILABLE_DELETED message_id={message_id}")
                elif outcome == "already_absent":
                    print(f"PUBLIC_HISTORY_DEADLINE_UNAVAILABLE_ABSENT message_id={message_id}")
            except Exception as exc:
                print(
                    f"PUBLIC_HISTORY_DEADLINE_UNAVAILABLE_DELETE_FAILED message_id={message_id} "
                    f"error={type(exc).__name__} detail={str(exc)[:120]!r}"
                )
                try:
                    result = _telegram_mark_deadline_unavailable(
                        int(message_id), fields.get("title") or "پیشنهاد ویژه"
                    )
                    if result == "edited":
                        print(f"PUBLIC_HISTORY_DEADLINE_UNAVAILABLE_MARKED message_id={message_id}")
                except Exception as mark_exc:
                    print(
                        f"PUBLIC_HISTORY_DEADLINE_UNAVAILABLE_FALLBACK_FAILED message_id={message_id} "
                        f"error={type(mark_exc).__name__} detail={str(mark_exc)[:120]!r}"
                    )
            continue
        if not fields.get("title") or not fields.get("current_price") or not fields.get("discount_percent"):
            continue
        if not _caption_needs_repair(caption_html, caption_text, fields, deadline):
            continue
        caption = _build_legacy_repaired_caption(fields, deadline, now)
        try:
            result = _telegram_edit_caption(int(message_id), caption)
            if result == "edited":
                reformatted += 1
                print(f"PUBLIC_HISTORY_CAPTION_REPAIRED message_id={message_id}")
            elif result == "already_absent":
                print(f"PUBLIC_HISTORY_CAPTION_UNAVAILABLE message_id={message_id} reason=message_not_found")
        except Exception as exc:
            print(f"PUBLIC_HISTORY_CAPTION_REPAIR_FAILED message_id={message_id} error={type(exc).__name__} detail={str(exc)[:140]!r}")

    print(
        "PUBLIC_HISTORY_AUDIT_SUMMARY "
        f"messages_scanned={len(posts)} expired_found={found_expired} deleted={deleted} "
        f"marked_expired={marked_expired} active_captions_repaired={reformatted}"
    )
    return changed, deleted, marked_expired, reformatted, found_expired



def _delete_posts_without_verified_deadline(published, now):
    """Remove posts whose countdown deadline is missing, estimated, or otherwise unverifiable.

    A post is kept only when it has a future deadline from DigiKala's live offer feed.
    If deletion temporarily fails, disable the purchase button and retry deletion on
    later cleanup runs instead of leaving an unverified offer purchasable.
    """
    changed = False
    deleted = 0
    marked = 0
    terminal = {"deleted", "already_absent"}
    platforms = (
        ("telegram", "telegram_message_id", "expiry_status", "deadline_unavailable_deleted_at",
         _telegram_delete, _telegram_mark_deadline_unavailable),
        ("bale", "bale_message_id", "bale_expiry_status", "bale_deadline_unavailable_deleted_at",
         _bale_delete, _bale_mark_deadline_unavailable),
    )
    for pid, rec in _iter_post_records(published):
        if not isinstance(rec, dict):
            continue
        raw_expiry = parse_expiry(rec.get("expires_at"))
        if raw_expiry:
            deadline = datetime.fromisoformat(raw_expiry)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            if deadline <= now:
                # The normal expired-post path handles these and retries its own deletion.
                continue
            if (
                rec.get("expiry_source") == "digikala_live_deals_feed"
                and rec.get("expiry_estimated") is not True
            ):
                continue

        for platform, id_field, status_field, stamp_field, delete_fn, mark_fn in platforms:
            raw_id = rec.get(id_field)
            if not str(raw_id or "").isdigit() or rec.get(status_field) in terminal:
                continue
            message_id = int(raw_id)
            try:
                outcome = delete_fn(message_id)
                rec[status_field] = outcome
                rec[stamp_field] = now.isoformat()
                rec.pop(f"{platform}_deadline_unavailable_error", None)
                changed = True
                if outcome == "deleted":
                    deleted += 1
                print(
                    f"DEADLINE_UNAVAILABLE_DELETE platform={platform} product_id={pid} "
                    f"message_id={message_id} outcome={outcome}"
                )
                continue
            except Exception as exc:
                delete_error = f"{type(exc).__name__}: {str(exc)[:160]}"
                rec[f"{platform}_deadline_unavailable_error"] = delete_error
                changed = True
                print(
                    f"DEADLINE_UNAVAILABLE_DELETE_FAILED platform={platform} product_id={pid} "
                    f"message_id={message_id} error={delete_error!r}"
                )

            # If already marked, keep retrying deletion without repeatedly editing the caption.
            if rec.get(status_field) == "deadline_unavailable_marked":
                continue
            try:
                outcome = mark_fn(message_id, rec.get("title"))
                if outcome == "edited":
                    rec[status_field] = "deadline_unavailable_marked"
                    rec[f"{platform}_deadline_unavailable_marked_at"] = now.isoformat()
                    marked += 1
                    changed = True
                    print(
                        f"DEADLINE_UNAVAILABLE_MARKED platform={platform} product_id={pid} "
                        f"message_id={message_id} reason=delete_failed"
                    )
                elif outcome == "already_absent":
                    rec[status_field] = "already_absent"
                    rec[stamp_field] = now.isoformat()
                    changed = True
            except Exception as mark_exc:
                rec[status_field] = "deadline_unavailable_delete_failed"
                rec[f"{platform}_deadline_unavailable_error"] = (
                    f"{delete_error}; fallback={type(mark_exc).__name__}: {str(mark_exc)[:120]}"
                )
                changed = True
                print(
                    f"DEADLINE_UNAVAILABLE_FALLBACK_FAILED platform={platform} product_id={pid} "
                    f"message_id={message_id} error={type(mark_exc).__name__}"
                )
    return changed, deleted, marked


def _delete_expired_posts(published, now, mark_unknown=False):
    """Delete posts whose explicit deadline has passed; return state change and actual deletions."""
    changed = False
    deleted = 0
    for pid, rec in _iter_post_records(published):
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
                    if rec.get(status_field) not in {"deleted", "already_absent", "expired_marked", "unknown", "deadline_unavailable_marked", "deadline_unavailable_delete_failed"}:
                        rec[status_field] = "unknown"
                        changed = True
            continue
        expires_at = datetime.fromisoformat(expiry)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        removal_deadline = expires_at - timedelta(minutes=POST_REMOVAL_BUFFER_MINUTES)
        if now < removal_deadline:
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
                print(
                    f"EXPIRY_DELETE_OK platform={platform} product_id={pid} message_id={raw_id} "
                    f"outcome={outcome} expiry={expiry} remove_at={removal_deadline.isoformat()}"
                )
            except Exception as exc:
                rec[status_field] = "delete_failed"
                error_text = str(exc)[:180]
                rec[f"{platform}_expiry_last_delete_error"] = f"{type(exc).__name__}: {error_text}"
                changed = True
                print(f"EXPIRY_DELETE_FAILED platform={platform} product_id={pid} message_id={raw_id} error={type(exc).__name__} detail={error_text[:160]!r}")
    return changed, deleted




def _hide_expired_aparat_videos(published, now):
    """Stop sharing tracked Aparat videos before the offer deadline where possible."""
    changed = False
    try:
        from aparat_uploader import set_aparat_video_private, aparat_credentials_available
        credentials_ready = aparat_credentials_available()
    except Exception as exc:
        set_aparat_video_private = None
        credentials_ready = False
        print(f"APARAT_EXPIRY_SETUP_UNAVAILABLE error={type(exc).__name__}")

    for pid, rec in _iter_post_records(published):
        if not isinstance(rec, dict):
            continue
        # Legacy generic-feed videos that failed the one-time privacy migration are
        # intentionally left alone per the current publishing configuration. Do not
        # keep retrying an endpoint that has already rejected those old records.
        if str(rec.get("aparat_shorts_migration_status") or "") == "retry":
            continue
        video_hash = str(rec.get("aparat_video_hash") or "").strip()
        expiry_status = str(rec.get("aparat_expiry_status") or "")
        if not video_hash or expiry_status in {"private", "already_private"}:
            continue
        expires = parse_expiry(rec.get("expires_at"))
        if not expires:
            continue
        try:
            deadline = datetime.fromisoformat(expires)
        except ValueError:
            continue
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        removal_deadline = deadline - timedelta(minutes=POST_REMOVAL_BUFFER_MINUTES)
        if removal_deadline > now:
            continue
        retry_raw = parse_expiry(rec.get("aparat_expiry_next_attempt_at"))
        if retry_raw:
            try:
                retry_at = datetime.fromisoformat(retry_raw)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                if now < retry_at and not (expiry_status == "pending_credentials" and credentials_ready):
                    continue
            except ValueError:
                pass

        # A deliberately non-public first test upload is already not shared.
        if str(rec.get("aparat_visibility") or "") == "non_public_test":
            rec["aparat_expiry_status"] = "already_private"
            rec["aparat_private_at"] = now.isoformat()
            rec.pop("aparat_expiry_next_attempt_at", None)
            changed = True
            print(f"APARAT_EXPIRY_ALREADY_PRIVATE product_id={pid} video_hash={video_hash}")
            continue

        if not credentials_ready or set_aparat_video_private is None:
            rec["aparat_expiry_status"] = "pending_credentials"
            rec["aparat_expiry_next_attempt_at"] = (now + timedelta(minutes=60)).isoformat()
            rec["aparat_expiry_last_error"] = "aparat_cookie_secret_missing"
            changed = True
            continue

        try:
            set_aparat_video_private(video_hash)
            rec["aparat_expiry_status"] = "private"
            rec["aparat_private_at"] = now.isoformat()
            rec.pop("aparat_expiry_next_attempt_at", None)
            rec.pop("aparat_expiry_last_error", None)
            changed = True
            print(f"APARAT_EXPIRY_PRIVATE_OK product_id={pid} video_hash={video_hash}")
        except Exception as exc:
            rec["aparat_expiry_status"] = "retry"
            rec["aparat_expiry_next_attempt_at"] = (now + timedelta(minutes=30)).isoformat()
            rec["aparat_expiry_last_error"] = type(exc).__name__
            changed = True
            print(f"APARAT_EXPIRY_PRIVATE_FAILED product_id={pid} error={type(exc).__name__}")

    return changed


def _hide_expired_youtube_videos(published, now):
    """Set tracked YouTube Shorts to private once their underlying time-limited offer expires."""
    changed = False
    try:
        from short_video import set_youtube_video_private, youtube_credentials_available
        credentials_ready = youtube_credentials_available()
    except Exception as exc:
        set_youtube_video_private = None
        credentials_ready = False
        print(f"YOUTUBE_EXPIRY_SETUP_UNAVAILABLE error={type(exc).__name__}")

    for pid, rec in _iter_post_records(published):
        if not isinstance(rec, dict):
            continue
        video_id = str(rec.get("youtube_video_id") or "").strip()
        if not video_id or rec.get("youtube_expiry_status") in {"private", "already_private"}:
            continue
        expires = parse_expiry(rec.get("expires_at"))
        if not expires:
            continue
        try:
            deadline = datetime.fromisoformat(expires)
        except ValueError:
            continue
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        removal_deadline = deadline - timedelta(minutes=POST_REMOVAL_BUFFER_MINUTES)
        if removal_deadline > now:
            continue
        retry_raw = parse_expiry(rec.get("youtube_expiry_next_attempt_at"))
        if retry_raw:
            try:
                retry_at = datetime.fromisoformat(retry_raw)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                if now < retry_at:
                    continue
            except ValueError:
                pass

        if not credentials_ready or set_youtube_video_private is None:
            rec["youtube_expiry_status"] = "pending_credentials"
            rec["youtube_expiry_next_attempt_at"] = (now + timedelta(minutes=60)).isoformat()
            rec["youtube_expiry_last_error"] = "youtube_oauth_secrets_missing"
            changed = True
            continue

        try:
            set_youtube_video_private(video_id)
            rec["youtube_expiry_status"] = "private"
            rec["youtube_private_at"] = now.isoformat()
            rec.pop("youtube_expiry_next_attempt_at", None)
            rec.pop("youtube_expiry_last_error", None)
            changed = True
            print(f"YOUTUBE_EXPIRY_PRIVATE_OK product_id={pid} video_id={video_id}")
        except Exception as exc:
            rec["youtube_expiry_status"] = "retry"
            rec["youtube_expiry_next_attempt_at"] = (now + timedelta(minutes=30)).isoformat()
            rec["youtube_expiry_last_error"] = type(exc).__name__
            changed = True
            print(f"YOUTUBE_EXPIRY_PRIVATE_FAILED product_id={pid} error={type(exc).__name__}")

    return changed


def run():
    state = _read_state()
    published = state.get("published", {})
    if not isinstance(published, dict):
        raise ValueError("state.json published must be an object")
    now = datetime.now(timezone.utc)
    changed = False
    deleted = 0

    # Refresh known deadlines before expiry/deletion decisions; a fresh live deadline
    # must supersede a stale cached deadline.
    feed_last = parse_expiry(state.get("expiry_feed_last_checked_at"))
    force_feed_sync = os.getenv("AFFILIO_FORCE_DEADLINE_SYNC", "false").strip().lower() in {"1", "true", "yes", "on"}
    feed_due = force_feed_sync or not feed_last or (now - datetime.fromisoformat(feed_last)).total_seconds() >= LIVE_DEADLINE_SYNC_INTERVAL_SECONDS
    if feed_due and published:
        live_expiries = {}
        try:
            live_expiries = fetch_offer_expiries()
        except Exception as exc:
            print(f"EXPIRY_FEED_LOOKUP_FAILED error={type(exc).__name__} detail={str(exc)[:140]!r}")
        if live_expiries:
            sync_summary = sync_live_offer_deadlines(published, live_expiries, now)
            state["expiry_feed_last_checked_at"] = now.isoformat()
            state["expiry_feed_last_sync_summary"] = sync_summary
            changed = True
            print(
                "EXPIRY_LIVE_SYNC_SUMMARY "
                f"matched={sync_summary['matched']} updated={sync_summary['updated']} "
                f"unchanged={sync_summary['unchanged']} missing_from_feed={sync_summary['missing_from_feed']} "
                f"skipped={sync_summary['skipped']} forced={force_feed_sync}"
            )
        else:
            print("EXPIRY_LIVE_SYNC_SKIPPED reason=no_live_deadlines_received; cached deadlines retained")
    else:
        print(f"EXPIRY_LIVE_SYNC_SKIPPED reason=not_due forced={force_feed_sync}")

    pre_changed, pre_deleted = _delete_expired_posts(published, now, mark_unknown=True)
    changed = changed or pre_changed
    deleted += pre_deleted
    if pre_changed:
        _write_state(state)
        print("EXPIRY_STATE_SAVED phase=known_deadline_cleanup")

    unavailable_changed, unavailable_deleted, unavailable_marked = (
        _delete_posts_without_verified_deadline(published, now)
    )
    changed = changed or unavailable_changed
    deleted += unavailable_deleted
    if unavailable_changed:
        _write_state(state)
        print("EXPIRY_STATE_SAVED phase=deadline_unavailable_cleanup")

    history_changed, history_deleted, history_marked, history_repaired, history_expired_found = (
        audit_public_channel_history(published, now)
    )
    changed = changed or history_changed
    deleted += history_deleted
    if history_changed:
        _write_state(state)
        print("EXPIRY_STATE_SAVED phase=public_history_audit")

    probe_candidates = [
        (pid, rec) for pid, rec in published.items()
        if isinstance(rec, dict)
        and (
            (str(rec.get("telegram_message_id") or "").isdigit() and rec.get("expiry_status") not in {"deleted", "already_absent", "expired_marked"})
            or (str(rec.get("bale_message_id") or "").isdigit() and rec.get("bale_expiry_status") not in {"deleted", "already_absent", "expired_marked"})
        )
        and _should_probe(rec, now)
    ]
    probe_candidates.sort(key=lambda pair: str(pair[1].get("expiry_last_probed_at") or ""))
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

    youtube_privacy_changed = _hide_expired_youtube_videos(published, now)
    changed = changed or youtube_privacy_changed
    aparat_privacy_changed = _hide_expired_aparat_videos(published, now)
    changed = changed or aparat_privacy_changed
    if changed:
        _write_state(state)
    backlog = max(0, len(probe_candidates) - min(len(probe_candidates), max_probe_candidates))
    print(
        f"EXPIRY_MONITOR_SUMMARY tracked={len(published)} probed={product_probe_count} "
        f"probe_backlog={backlog} deleted_now={deleted} deadline_unavailable_marked={unavailable_marked} state_changed={changed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
