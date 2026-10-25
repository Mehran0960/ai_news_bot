#!/usr/bin/env python3
"""Keep OfferChin deal posts live only when their absolute deadline is verified.

Only verified expired offers are deleted from Telegram and Bale. Missing or estimated
deadlines are not proof of expiry, so affected posts are preserved until a direct DigiKala
source-backed deadline can be re-established. Caption edits explicitly reattach the
approved Affilio purchase button and never display a remaining-time countdown.
"""
from __future__ import annotations

import html
import json
import os
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from affilio_radar import build_caption, TELEGRAM_CHANNEL_URL
from offer_expiry import extract_offer_expiry, parse_absolute_deadline
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
# Remove verified expired offers ten minutes before DigiKala's source deadline; never display a countdown.
POST_REMOVAL_BUFFER_MINUTES = max(
    0, min(30, int(os.getenv("AFFILIO_COUNTDOWN_SAFETY_BUFFER_MINUTES", "10")))
)
# Recheck the first-party deal feed every five minutes so cached deadlines remain current.
LIVE_DEADLINE_SYNC_INTERVAL_SECONDS = 5 * 60
# Bound detail lookups so missing timers cannot stall expiry cleanup.
DIRECT_PRODUCT_DETAIL_CHECK_LIMIT = max(1, min(2, int(os.getenv("AFFILIO_DIRECT_PRODUCT_DETAIL_CHECK_LIMIT", "1"))))
CAPTION_FORMAT_VERSION = 12


def walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def parse_expiry(value):
    """Parse an explicitly absolute deadline to UTC; naive timestamps use Tehran time."""
    return parse_absolute_deadline(value)



def _has_verified_deadline(record):
    """True only when an authoritative DigiKala API/source confirmed the timestamp."""
    if not isinstance(record, dict) or record.get("expiry_estimated") is True:
        return False
    if not parse_expiry(record.get("expires_at")):
        return False
    source = str(record.get("expiry_source") or "")
    if source == "live_product_stock_or_price":
        return True
    if source == "digikala_mcp_offer_card":
        return record.get("expiry_deadline_verified_from_site_card") is True
    return (
        source in {"digikala_live_deals_feed", "digikala_product_detail_api"}
        and record.get("expiry_deadline_verified_directly") is True
    )

def extract_expiry(obj, now=None):
    """Use the same site-countdown parser as initial publication and caption refresh."""
    return extract_offer_expiry(obj, now=now)


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
        page_observed_at = datetime.now(timezone.utc)
        page_candidates = 0
        for node in walk_dicts(payload):
            pid = _product_id(node)
            if not pid:
                continue
            title = node.get("title_fa") or node.get("product_title") or node.get("title")
            if not title:
                continue
            raw_url = node.get("url") or node.get("product_url") or node.get("web_url")
            if isinstance(raw_url, dict):
                raw_url = raw_url.get("uri") or raw_url.get("url") or ""
            url_match = re.search(r"/product/(dkp-\d+)", str(raw_url or ""), re.I)
            # A real offer card has its own canonical product URL. A nested variant
            # can repeat the ID/title but must never supersede the card countdown.
            if not url_match or url_match.group(1).lower() != pid.lower():
                continue
            expiry = extract_expiry(node, now=page_observed_at)
            old = candidate_nodes.get(pid)
            should_replace = (
                old is None
                or (
                    bool(expiry)
                    and (pid not in expiries or len(node) > len(old))
                )
            )
            if should_replace:
                candidate_nodes[pid] = dict(node)
                if expiry:
                    expiries[pid] = expiry
                    candidate_nodes[pid]["deal_expires_at"] = expiry
                page_candidates += 1
        page_count = sum(1 for pid in candidate_nodes if pid in expiries)
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
    """Read the first-party DigiKala live-deals REST endpoint using redirect-safe HTTP."""
    results = {}
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 OfferChin/1.0",
        "Accept": "application/json",
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.7",
        "Referer": "https://www.digikala.com/",
    }
    for page in range(1, DEAL_LIST_PAGES + 1):
        try:
            response = session.get(
                FEED_URL, params={"page": page, "q": ""}, headers=headers,
                timeout=HTTP_TIMEOUT, allow_redirects=True,
            )
            response.raise_for_status()
            if len(response.content) > 8_000_000:
                raise RuntimeError("Digikala feed response exceeded 8 MB")
            payload = response.json()
            page_observed_at = datetime.now(timezone.utc)
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
            url_match = re.search(r"/product/(dkp-\d+)", str(raw_url or ""), re.I)
            if not url_match or url_match.group(1).lower() != pid.lower():
                continue
            old = candidate_nodes.get(pid)
            if old is None or len(node) > len(old):
                candidate_nodes[pid] = dict(node)
        for pid, card in candidate_nodes.items():
            expiry = extract_expiry(card, now=page_observed_at)
            if expiry:
                results[pid] = expiry
                page_found += 1
        print(f"EXPIRY_FEED_PAGE page={page} products_with_deadlines={page_found}")
    return results


def fetch_offer_deadlines(required_product_ids=None):
    """Fetch current exact DigiKala card deadlines, preferring first-party REST data.

    The REST endpoint is authoritative when it exposes a timer. On products where
    the list endpoint omits timer fields, the same product-matched live offer card
    returned by the DigiKala MCP adapter can supplement the gap. Estimated/cache-only
    timestamps never enter this map.
    """
    required = {str(pid) for pid in (required_product_ids or []) if str(pid)}
    direct = {}
    try:
        payload = fetch_direct_api_offer_expiries()
        if isinstance(payload, dict):
            direct = {
                str(pid): expiry
                for pid, expiry in payload.items()
                if str(pid) and parse_expiry(expiry)
            }
    except Exception as exc:
        print(f"EXPIRY_DIRECT_FEED_LOOKUP_FAILED error={type(exc).__name__} detail={str(exc)[:140]!r}")

    combined = dict(direct)
    sources = {pid: "digikala_live_deals_feed" for pid in direct}
    missing_required = required.difference(direct)
    mcp_added = 0
    if missing_required:
        try:
            # Page 1 contains the freshest timed cards; unresolved records fall back
            # to a bounded, rotating batch of first-party product-detail checks.
            mcp, _cards = fetch_mcp_offer_candidates(page_numbers=[1])
            for raw_pid, raw_expiry in mcp.items():
                pid = str(raw_pid)
                if pid in direct or (required and pid not in missing_required):
                    continue
                expiry = parse_expiry(raw_expiry)
                if not expiry:
                    continue
                combined[pid] = expiry
                sources[pid] = "digikala_mcp_offer_card"
                mcp_added += 1
        except Exception as exc:
            print(f"EXPIRY_MCP_FALLBACK_FAILED error={type(exc).__name__} detail={str(exc)[:140]!r}")

    unresolved_count = len(required.difference(combined))
    print(
        f"EXPIRY_SOURCE_PRIORITY direct_site={len(direct)} mcp_page1_added={mcp_added} "
        f"required={len(required)} unresolved_required={unresolved_count} "
        "direct_site_wins=true cached_deadlines_preserved_without_live_evidence=true "
        "product_detail_probes_deferred_to_rotating_monitor=true"
    )
    return combined, sources


def fetch_offer_expiries(required_product_ids=None):
    """Compatibility wrapper returning only the combined current source-backed deadlines."""
    deadlines, _sources = fetch_offer_deadlines(required_product_ids=required_product_ids)
    return deadlines
def _money_to_toman(raw, is_toman):
    if raw in (None, "", 0, "0"):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    value = value if is_toman else value / 10.0
    return max(0, int(round(value)))



def sync_live_offer_deadlines(published, live_expiries, now, live_sources=None):
    """Reconcile tracked posts with current card timers while preserving each timer's source."""
    summary = {"matched": 0, "updated": 0, "unchanged": 0, "missing_from_feed": 0, "skipped": 0}
    terminal = {"deleted", "already_absent"}
    # DigiKala's current feed represents the current campaign only. Never copy its
    # deadline onto post_history records from earlier campaigns of the same product.
    for pid, rec in (published or {}).items():
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
            if telegram_id.isdigit() or bale_id.isdigit():
                summary["skipped"] += 1
            continue

        raw_live = live_expiries.get(str(pid))
        live = parse_expiry(raw_live)
        source = str((live_sources or {}).get(str(pid)) or "digikala_live_deals_feed")
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
            or rec.get("expiry_source") != source
            or (source in {"digikala_live_deals_feed", "digikala_product_detail_api"} and rec.get("expiry_deadline_verified_directly") is not True)
            or (source == "digikala_mcp_offer_card" and rec.get("expiry_deadline_verified_from_site_card") is not True)
            or (delta_seconds is not None and abs(delta_seconds) >= 60)
            or any(
                rec.get(status_field) in {
                    "expired_marked", "delete_failed", "deadline_unavailable_marked",
                    "deadline_unavailable_delete_failed", "unknown",
                }
                for status_field in ("expiry_status", "bale_expiry_status")
            )
        )
        if not must_update:
            # Same-value deadlines still count as fresh first-party confirmation.
            rec["expiry_last_live_sync_at"] = now.isoformat()
            if source in {"digikala_live_deals_feed", "digikala_product_detail_api"}:
                rec["expiry_last_direct_verification_at"] = now.isoformat()
            elif source == "digikala_mcp_offer_card":
                rec["expiry_last_site_card_sync_at"] = now.isoformat()
            summary["unchanged"] += 1
            continue

        rec["expires_at"] = live
        rec["expiry_source"] = source
        rec["expiry_estimated"] = False
        rec["expiry_deadline_verified_directly"] = source in {"digikala_live_deals_feed", "digikala_product_detail_api"}
        rec["expiry_deadline_verified_from_site_card"] = source == "digikala_mcp_offer_card"
        rec["expiry_last_live_sync_at"] = now.isoformat()
        if source in {"digikala_live_deals_feed", "digikala_product_detail_api"}:
            rec["expiry_last_direct_verification_at"] = now.isoformat()
        elif source == "digikala_mcp_offer_card":
            rec["expiry_last_site_card_sync_at"] = now.isoformat()
        # Force this exact post to the front of the static-caption migration queue.
        rec["deadline_caption_refresh_required"] = True
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
        variants = product.get("variants")
        if isinstance(variants, dict):
            variants = list(variants.values())
        marketable_variant = (
            next((v for v in variants if isinstance(v, dict) and v.get("marketable") is True), {})
            if isinstance(variants, list) else {}
        )
        # If DigiKala's default variant is explicitly unavailable, prefer an
        # actually marketable variant instead of mistaking one unavailable size
        # or colour for the entire product being out of stock.
        if not variant or variant.get("marketable") is False:
            variant = marketable_variant or variant
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
        deal_expiry = extract_expiry(product, now=datetime.now(timezone.utc))
        return {
            "current_price": current,
            "original_price": original,
            "in_stock": in_stock,
            "api_version": version,
            "deal_expires_at": deal_expiry or "",
            "expiry_verified_directly": bool(deal_expiry),
        }
    return {}



def _has_active_publication(record):
    """Whether at least one public message/video for this record still needs cleanup."""
    if not isinstance(record, dict):
        return False
    terminal = {"deleted", "already_absent"}
    targets = (
        ("telegram_message_id", "expiry_status", True),
        ("bale_message_id", "bale_expiry_status", True),
        ("youtube_video_id", "youtube_expiry_status", False),
        ("aparat_video_hash", "aparat_expiry_status", False),
    )
    for id_field, status_field, numeric_id in targets:
        raw_id = str(record.get(id_field) or "").strip()
        if not raw_id or (numeric_id and not raw_id.isdigit()):
            continue
        if str(record.get(status_field) or "") not in terminal:
            return True
    return False


def _positive_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def audit_live_post_prices(published, now=None, max_products=None):
    """Check active Telegram/Bale/video posts against DigiKala's live product API.

    A verified price/original-price mismatch or confirmed out-of-stock result marks
    the affected publication for removal on every platform. API failures are only
    logged as inconclusive and never authorize deletion.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    limit = PRICE_AUDIT_PRODUCT_CHECKS_PER_RUN if max_products is None else max(1, int(max_products))
    groups = {}

    for product_id, record in _iter_post_records(published):
        if not isinstance(record, dict) or not _has_active_publication(record):
            continue
        # Once direct evidence has already invalidated a publication, keep retrying
        # deletion; do not let a later price fluctuation cancel that decision.
        if record.get("expiry_source") == "live_product_stock_or_price" and record.get("expiry_reason"):
            continue
        groups.setdefault(str(product_id), []).append(record)

    due = []
    interval = PRICE_AUDIT_INTERVAL_SECONDS
    for product_id, records in groups.items():
        stamps = []
        is_due = False
        for record in records:
            raw = parse_expiry(record.get("price_audit_last_checked_at"))
            if not raw:
                stamps.append(0.0)
                is_due = True
                continue
            try:
                checked = datetime.fromisoformat(raw)
                if checked.tzinfo is None:
                    checked = checked.replace(tzinfo=timezone.utc)
                checked_epoch = checked.astimezone(timezone.utc).timestamp()
                stamps.append(checked_epoch)
                if (now - checked.astimezone(timezone.utc)).total_seconds() >= interval:
                    is_due = True
            except (TypeError, ValueError, OverflowError):
                stamps.append(0.0)
                is_due = True
        if is_due:
            due.append((min(stamps) if stamps else 0.0, product_id, records))

    due.sort(key=lambda item: (item[0], item[1]))
    selected = due[:limit]
    changed = False
    checked_count = mismatched_count = inconclusive_count = 0
    print(
        f"PRICE_AUDIT_START due_products={len(due)} limit={limit} "
        f"interval_seconds={interval} backlog={max(0, len(due) - len(selected))}"
    )

    for _last_checked, product_id, records in selected:
        checked_count += 1
        snapshot = fetch_live_product_status(product_id)
        if not snapshot:
            inconclusive_count += 1
            for record in records:
                record["price_audit_last_checked_at"] = now.isoformat()
                record["price_audit_status"] = "inconclusive"
                record["price_audit_last_error"] = "direct_product_api_unavailable"
                changed = True
            print(f"PRICE_AUDIT_INCONCLUSIVE product_id={product_id} reason=direct_product_api_unavailable")
            continue

        live_current = _positive_int(snapshot.get("current_price"))
        live_original = _positive_int(snapshot.get("original_price"))
        in_stock = snapshot.get("in_stock")
        live_deadline = (
            parse_expiry(snapshot.get("deal_expires_at"))
            if snapshot.get("expiry_verified_directly") is True else ""
        )
        product_had_mismatch = False

        for record in records:
            record["price_audit_last_checked_at"] = now.isoformat()
            record["price_audit_live_current_price"] = live_current
            record["price_audit_live_original_price"] = live_original
            record["price_audit_live_in_stock"] = in_stock
            record.pop("price_audit_last_error", None)
            record.pop("price_audit_mismatch_fields", None)
            changed = True

            posted_current = _positive_int(record.get("posted_current_price") or record.get("current_price"))
            posted_original = _positive_int(record.get("posted_original_price") or record.get("original_price"))
            mismatch_fields = []
            if in_stock is False:
                reason = "out_of_stock"
            else:
                reason = ""
                if posted_current is not None and live_current is not None and posted_current != live_current:
                    mismatch_fields.append("current_price")
                if posted_original is not None and live_original is not None and posted_original != live_original:
                    mismatch_fields.append("original_price")
                if mismatch_fields:
                    reason = "price_mismatch"

            if reason:
                product_had_mismatch = True
                mismatched_count += 1
                record["price_audit_status"] = "mismatch_confirmed"
                record["price_audit_mismatch_fields"] = mismatch_fields or ["stock"]
                record["price_audit_reason"] = reason
                record["expires_at"] = now.isoformat()
                record["expiry_source"] = "live_product_stock_or_price"
                record["expiry_deadline_verified_directly"] = True
                record["expiry_deadline_verified_from_site_card"] = False
                record["expiry_estimated"] = False
                record["expiry_last_direct_verification_at"] = now.isoformat()
                record["expiry_last_removal_check_at"] = now.isoformat()
                record["expiry_last_removal_check_result"] = "confirmed"
                record["expiry_reason"] = reason
                print(
                    f"PRICE_AUDIT_MISMATCH_CONFIRMED product_id={product_id} "
                    f"reason={reason} posted_current={posted_current} live_current={live_current} "
                    f"posted_original={posted_original} live_original={live_original} "
                    f"fields={','.join(mismatch_fields) or 'stock'}; deletion_queued=true"
                )
                continue

            # A direct product-detail timer supersedes any older cached card deadline.
            # This prevents a stale deadline from deleting an offer that DigiKala extended.
            if live_deadline:
                previous_deadline = parse_expiry(record.get("expires_at"))
                should_sync_deadline = (
                    not previous_deadline
                    or record.get("expiry_source") != "digikala_product_detail_api"
                    or record.get("expiry_deadline_verified_directly") is not True
                )
                if previous_deadline:
                    try:
                        previous_dt = datetime.fromisoformat(previous_deadline)
                        current_dt = datetime.fromisoformat(live_deadline)
                        if previous_dt.tzinfo is None:
                            previous_dt = previous_dt.replace(tzinfo=timezone.utc)
                        if current_dt.tzinfo is None:
                            current_dt = current_dt.replace(tzinfo=timezone.utc)
                        should_sync_deadline = should_sync_deadline or abs((current_dt - previous_dt).total_seconds()) >= 60
                    except (TypeError, ValueError, OverflowError):
                        should_sync_deadline = True
                if should_sync_deadline:
                    record["expires_at"] = live_deadline
                    record["expiry_source"] = "digikala_product_detail_api"
                    record["expiry_deadline_verified_directly"] = True
                    record["expiry_deadline_verified_from_site_card"] = False
                    record["expiry_estimated"] = False
                    record["expiry_last_direct_verification_at"] = now.isoformat()
                    record["expiry_last_removal_check_result"] = "confirmed"
                    changed = True

            compared = (
                (posted_current is not None and live_current is not None)
                or (posted_original is not None and live_original is not None)
            )
            record["price_audit_status"] = "matched" if compared else "inconclusive"
            if not compared:
                inconclusive_count += 1

            # A previously verified DigiKala card timer is already source-backed.
            # If it has passed and the direct API returns a live product but no active
            # countdown, allow the normal expiry cleanup to remove the stale promotion.
            expires = parse_expiry(record.get("expires_at"))
            source = str(record.get("expiry_source") or "")
            if (
                not live_deadline and expires
                and source == "digikala_mcp_offer_card"
                and record.get("expiry_deadline_verified_from_site_card") is True
                and datetime.fromisoformat(expires) <= now
                and (live_current is not None or in_stock is not None)
            ):
                record["expiry_last_removal_check_at"] = now.isoformat()
                record["expiry_last_removal_check_result"] = "confirmed"
                changed = True
                print(
                    f"PRICE_AUDIT_EXPIRED_CARD_CONFIRMED product_id={product_id} "
                    f"expires_at={expires}; deletion_queued=true"
                )

        if not product_had_mismatch:
            print(
                f"PRICE_AUDIT_PRODUCT_CHECKED product_id={product_id} current_price={live_current} "
                f"original_price={live_original} in_stock={in_stock}"
            )

    print(
        f"PRICE_AUDIT_SUMMARY checked_products={checked_count} "
        f"mismatch_records={mismatched_count} inconclusive_products={inconclusive_count} "
        f"backlog={max(0, len(due) - len(selected))} state_changed={changed}"
    )
    return changed, checked_count, mismatched_count, inconclusive_count, max(0, len(due) - len(selected))

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
    terminal = {"deleted", "already_absent"}
    telegram_done = record.get("expiry_status") in terminal
    bale_message_id = record.get("bale_message_id")
    bale_done = record.get("bale_expiry_status") in terminal
    if telegram_done and (not str(bale_message_id or "").isdigit() or bale_done):
        return False
    if _has_verified_deadline(record):
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
    """Legacy helper retained for compatibility; new captions use an absolute deadline."""
    effective_deadline = deadline - timedelta(minutes=POST_REMOVAL_BUFFER_MINUTES)
    seconds = (effective_deadline - now).total_seconds()
    if seconds <= 0:
        return "مهلت آفر به پایان رسیده"
    if seconds < 60:
        return "کمتر از ۱ دقیقه"
    minutes = int(seconds // 60)
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{_persian_number(hours)} ساعت و {_persian_number(mins)} دقیقه"
    if hours:
        return f"{_persian_number(hours)} ساعت"
    return f"{_persian_number(mins)} دقیقه"


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """Convert Gregorian calendar date to Solar Hijri (Jalali) date."""
    g_days_before_month = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    if not 1 <= gm <= 12 or not 1 <= gd <= 31:
        raise ValueError("Invalid Gregorian month or day")
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
        + g_days_before_month[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def _format_jalali_deadline(deadline):
    """Render a confirmed UTC deadline as a fixed Persian date and Tehran-local time."""
    if not isinstance(deadline, datetime):
        return ""
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    local = deadline.astimezone(ZoneInfo("Asia/Tehran"))
    if local.hour == 0 and local.minute == 0:
        local -= timedelta(minutes=1)
    jalali_year, jalali_month, jalali_day = gregorian_to_jalali(
        local.year, local.month, local.day
    )
    weekdays = {
        "Monday": "دوشنبه", "Tuesday": "سه‌شنبه", "Wednesday": "چهارشنبه",
        "Thursday": "پنجشنبه", "Friday": "جمعه", "Saturday": "شنبه", "Sunday": "یکشنبه",
    }
    months = {number: name for name, number in PERSIAN_MONTHS.items()}
    rendered = (
        f"{weekdays.get(local.strftime('%A'), '')} {jalali_day} "
        f"{months[jalali_month]} {jalali_year}، ساعت {local:%H:%M}"
    )
    return rendered.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


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


def _build_legacy_repaired_caption(fields, deadline=None, now=None, affiliate_url=""):
    """Compatibility wrapper: every caption edit uses the canonical publication formatter."""
    product = {
        "title": fields.get("title") or "پیشنهاد ویژه",
        "current_price": fields.get("current_price"),
        "original_price": fields.get("original_price"),
        "discount_percent": fields.get("discount_percent"),
    }
    # The deadline remains authoritative only in state; caption text intentionally has no timer.
    return build_caption(product, affiliate_url, TELEGRAM_CHANNEL_URL)

def _caption_needs_repair(caption_html, caption_text, fields, deadline=None, now=None):
    """Check captions against the canonical static layout, not the former underline style."""
    text = str(caption_text or "")
    if "عضویت در کانال OfferChin" not in text or "t.me/OfferChin" in text:
        return True

    # Captions never contain a timer or a textual deadline: only state drives deletion.
    timer_or_deadline_markers = (
        "⏳", "⌛", "مانده به پایان تخفیف", "مهلت آفر به پایان رسیده",
        "کمتر از ۱ دقیقه", "📅 پایان تخفیف:", "پایان تخفیف:",
    )
    if any(marker in text for marker in timer_or_deadline_markers):
        return True

    soup = BeautifulSoup(caption_html or "", "html.parser")
    # The reference/list price is no longer part of the public caption. Repair
    # legacy posts that still mention it or display a struck-through amount.
    if "قیمت اصلی" in text or soup.find(["s", "del", "strike"]) is not None:
        return True
    if soup.find("u") is not None:
        return True
    bold_texts = [
        " ".join(_normalize_digits(node.get_text(" ", strip=True)).split())
        for node in soup.find_all(["b", "strong"])
    ]
    normalized_text = " ".join(_normalize_digits(text).split())

    if "فروش ویژه دیجی‌کالا" not in normalized_text:
        return True
    if "🛍️" not in normalized_text:
        return True
    if "برای خرید از دیجی‌کالا" not in normalized_text or "دکمهٔ زیر" not in normalized_text:
        return True

    current = fields.get("current_price")
    original = fields.get("original_price")
    discount = fields.get("discount_percent")
    expected_dividers = 0

    try:
        current_value = int(current) if current is not None else 0
    except (TypeError, ValueError, OverflowError):
        current_value = 0
    try:
        original_value = int(original) if original is not None else 0
    except (TypeError, ValueError, OverflowError):
        original_value = 0
    try:
        discount_value = int(discount) if discount is not None else 0
    except (TypeError, ValueError, OverflowError):
        discount_value = 0

    if current_value > 0:
        expected_amount = _normalize_digits(_persian_number(current_value))
        if not any(
            "قیمت ویژه" in value and "تومان" in value and expected_amount in value
            for value in bold_texts
        ):
            return True
        expected_dividers += 1

    if discount_value > 0:
        expected_discount = _normalize_digits(_persian_number(discount_value)) + "٪"
        if not any(
            "تخفیف" in value and expected_discount in value
            for value in bold_texts
        ):
            return True
        expected_dividers += 1

    # The divider count/order is the visual signature of the agreed caption format.
    if text.count("────────────") != expected_dividers:
        return True

    # No original-price label or strike-through is allowed in the canonical caption,
    # regardless of the discount band; the legacy form was rejected above.
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
        product_ids = set()
        purchase_button_visible = False
        for anchor in wrap.select("a[href]"):
            product_id = _product_id_from_public_url(anchor.get("href", ""))
            if product_id:
                product_ids.add(product_id)
                purchase_button_visible = True
        results[message_id] = {
            "message_id": message_id,
            "caption_text": caption_text,
            "caption_html": caption_html,
            "product_ids": sorted(product_ids),
            "purchase_button_visible": purchase_button_visible,
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
        # Telegram's public preview repeats the pinned post (often message 1)
        # on every page. Do not let that pinned ID stop backward pagination.
        pageable_ids = [message_id for message_id in page_posts if message_id > 1]
        oldest = min(pageable_ids) if pageable_ids else min(page_posts)
        print(f"PUBLIC_HISTORY_PAGE_OK page={page} messages={len(page_posts)} oldest_id={oldest} newest_id={max(page_posts)}")
        if not pageable_ids or oldest == last_oldest:
            break
        last_oldest = oldest
        before = oldest
        time.sleep(0.15)
    print(f"PUBLIC_HISTORY_SUMMARY messages_scanned={len(all_posts)} pages_limit={max_pages}")
    return all_posts


def _product_id_from_public_url(value):
    """Extract a DigiKala ID from the confirmed Affilio purchase URL or product link."""
    try:
        parsed = urlsplit(html.unescape(str(value or "").strip()))
    except Exception:
        return ""
    host = (parsed.hostname or "").lower()
    if host == "aflo.ir":
        for destination in parse_qs(parsed.query, keep_blank_values=True).get("p", []):
            match = re.search(r"/product/((?:dkp|snp)-\d+)(?:/|$)", unquote(destination), re.I)
            if match:
                return match.group(1).lower()
    if host in {"digikala.com", "www.digikala.com", "snappshop.ir"}:
        match = re.search(r"/product/((?:dkp|snp)-\d+)(?:/|$)", parsed.path, re.I)
        if match:
            return match.group(1).lower()
    if host.endswith(".workers.dev"):
        match = re.search(r"/p/(dkp-\d+)(?:/|$)", parsed.path, re.I)
        if match:
            return match.group(1).lower()
    return ""


def _normalise_duplicate_title(value):
    value = str(value or "").lower().replace("ي", "ی").replace("ك", "ک").replace("\u200c", "")
    value = value.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    value = re.sub(r"[\u200b-\u200f\ufeff]", "", value)
    return "".join(re.findall(r"[^\W_]+", value, flags=re.UNICODE))


def _parse_explicit_message_ids(value):
    """Parse a comma/space separated list of known message IDs for a one-off cleanup."""
    return {
        int(item)
        for item in re.findall(r"\d+", str(value or ""))
        if int(item) > 0
    }


def _delete_one_specific_product(state, product_id, title, telegram_ids_raw="", bale_ids_raw=""):
    """Delete all known/public channel copies; keep only the normal repeat cooldown."""
    product_id = str(product_id or "").strip().lower()
    title = str(title or "").strip()
    if not re.fullmatch(r"(?:dkp|snp)-\d{1,12}", product_id) or not title:
        print("ONE_TIME_PRODUCT_DELETE_ABORTED reason=invalid_product_id_or_title")
        return 2
    if not BOT_TOKEN:
        print("ONE_TIME_PRODUCT_DELETE_ABORTED reason=telegram_bot_token_missing")
        return 2
    if not BALE_BOT_TOKEN or not BALE_CHANNEL_ID:
        print("ONE_TIME_PRODUCT_DELETE_ABORTED reason=bale_credentials_missing")
        return 2

    published = state.setdefault("published", {})
    if not isinstance(published, dict):
        print("ONE_TIME_PRODUCT_DELETE_ABORTED reason=published_state_invalid")
        return 2
    ledger = state.setdefault("publication_ledger", {})
    if not isinstance(ledger, dict):
        ledger = {}
        state["publication_ledger"] = ledger

    telegram_ids = _parse_explicit_message_ids(telegram_ids_raw)
    bale_ids = _parse_explicit_message_ids(bale_ids_raw)
    related_records = []
    target_title = _normalise_duplicate_title(title)
    for candidate_id, record in _iter_post_records(published):
        if not isinstance(record, dict):
            continue
        record_id = str(candidate_id or "").lower()
        url_id = _product_id_from_public_url(record.get("product_url", ""))
        record_title = _normalise_duplicate_title(record.get("title", ""))
        if record_id != product_id and url_id != product_id and record_title != target_title:
            continue
        related_records.append(record)
    durable_record = ledger.get(product_id)
    if isinstance(durable_record, dict):
        related_records.append(durable_record)

    for record in related_records:
        raw_id = record.get("telegram_message_id")
        if str(raw_id or "").isdigit():
            telegram_ids.add(int(raw_id))
        raw_bale_id = record.get("bale_message_id")
        if str(raw_bale_id or "").isdigit():
            bale_ids.add(int(raw_bale_id))
        history = record.get("post_history")
        if isinstance(history, list):
            for prior in history:
                if not isinstance(prior, dict):
                    continue
                raw_tg = prior.get("telegram_message_id")
                raw_bale = prior.get("bale_message_id")
                if str(raw_tg or "").isdigit():
                    telegram_ids.add(int(raw_tg))
                if str(raw_bale or "").isdigit():
                    bale_ids.add(int(raw_bale))

    # Telegram's public preview can reveal older posts whose IDs disappeared from state.
    history_scan_ok = False
    try:
        public_posts = fetch_public_channel_posts(max_pages=80)
        history_scan_ok = True
        for message_id, post in public_posts.items():
            caption = str(post.get("caption_text") or "")
            caption_key = _normalise_duplicate_title(caption)
            post_product_ids = {str(value).lower() for value in (post.get("product_ids") or [])}
            matched = (
                product_id in post_product_ids
                or product_id in caption.lower()
                or (bool(target_title) and target_title in caption_key)
            )
            if matched:
                telegram_ids.add(int(message_id))
                print(f"ONE_TIME_PRODUCT_DELETE_MATCH platform=telegram message_id={message_id} product_id={product_id}")
        print(
            f"ONE_TIME_PRODUCT_DELETE_SCAN product_id={product_id} "
            f"posts_scanned={len(public_posts)} "
            f"matches={sum(1 for mid, post in public_posts.items() if (
                product_id in {str(value).lower() for value in (post.get('product_ids') or [])}
                or product_id in str(post.get('caption_text') or '').lower()
                or target_title in _normalise_duplicate_title(post.get('caption_text') or '')
            ))} "
            f"complete_to_oldest={bool(public_posts) and min(public_posts) <= 1}"
        )
    except Exception as exc:
        print(
            f"ONE_TIME_PRODUCT_DELETE_SCAN_FAILED product_id={product_id} "
            f"error={type(exc).__name__} detail={str(exc)[:140]!r}; "
            "tracked and explicitly supplied IDs will still be attempted"
        )

    if not telegram_ids and not bale_ids:
        print(f"ONE_TIME_PRODUCT_DELETE_ABORTED product_id={product_id} reason=no_message_ids_found")
        return 2

    now = datetime.now(timezone.utc)
    # This is an exception for one cleanup, not a permanent exclusion. The ledger
    # timestamp below activates the standard repeat cooldown; normal discovery
    # will reconsider this product afterward under ordinary rules.
    suppressions = state.get("product_suppressions")
    if isinstance(suppressions, dict):
        suppressions.pop(product_id, None)
        if not suppressions:
            state.pop("product_suppressions", None)
    result_telegram = {}
    result_bale = {}
    failures = []

    for platform, message_ids, delete_fn, results in (
        ("telegram", sorted(telegram_ids), _telegram_delete, result_telegram),
        ("bale", sorted(bale_ids), _bale_delete, result_bale),
    ):
        for message_id in message_ids:
            last_error = ""
            for attempt in range(1, 4):
                try:
                    outcome = delete_fn(message_id)
                    if outcome not in {"deleted", "already_absent"}:
                        raise RuntimeError(f"unconfirmed deletion outcome: {outcome}")
                    results[message_id] = outcome
                    print(
                        f"ONE_TIME_PRODUCT_DELETE_RESULT platform={platform} "
                        f"product_id={product_id} message_id={message_id} outcome={outcome}"
                    )
                    break
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {str(exc)[:140]}"
                    if attempt < 3:
                        time.sleep(float(attempt))
            else:
                results[message_id] = "delete_failed"
                failures.append((platform, message_id, last_error))
                print(
                    f"ONE_TIME_PRODUCT_DELETE_FAILED platform={platform} "
                    f"product_id={product_id} message_id={message_id} error={last_error!r}"
                )

    # Store every attempted message ID, including old IDs recovered from public
    # history, so the usual duplicate guard cannot immediately repost the item.
    old_record = published.get(product_id)
    base = dict(old_record) if isinstance(old_record, dict) else {}
    base["title"] = title
    base["product_url"] = (
        base.get("product_url") or f"https://www.digikala.com/product/{product_id}/"
    )
    base["ts"] = now.timestamp()
    base["one_time_removed_at"] = now.isoformat()
    base["one_time_removal_reason"] = "user_requested_product_cleanup"
    if telegram_ids:
        latest_tg = max(telegram_ids)
        base["telegram_message_id"] = latest_tg
        base["expiry_status"] = result_telegram.get(latest_tg, "delete_failed")
    if bale_ids:
        latest_bale = max(bale_ids)
        base["bale_message_id"] = latest_bale
        base["bale_expiry_status"] = result_bale.get(latest_bale, "delete_failed")

    history_records = []
    for message_id in sorted(telegram_ids):
        if message_id == max(telegram_ids):
            continue
        history_records.append({
            "telegram_message_id": message_id,
            "expiry_status": result_telegram.get(message_id, "delete_failed"),
            "one_time_removed_at": now.isoformat(),
        })
    for message_id in sorted(bale_ids):
        if message_id == max(bale_ids):
            continue
        history_records.append({
            "bale_message_id": message_id,
            "bale_expiry_status": result_bale.get(message_id, "delete_failed"),
            "one_time_removed_at": now.isoformat(),
        })
    base["post_history"] = history_records[-80:]
    published[product_id] = base

    ledger_entry = {
        "ts": now.timestamp(),
        "title": title,
        "product_url": base["product_url"],
        "telegram_message_id": base.get("telegram_message_id"),
        "bale_message_id": base.get("bale_message_id"),
        "expiry_status": base.get("expiry_status", "deleted"),
        "bale_expiry_status": base.get("bale_expiry_status", "deleted"),
        "one_time_removed_at": now.isoformat(),
        "one_time_removal_reason": "user_requested_product_cleanup",
    }
    for price_field in ("posted_current_price", "posted_original_price", "posted_discount_percent"):
        if price_field in base:
            ledger_entry[price_field] = base[price_field]
    ledger[product_id] = ledger_entry

    for queue_name in ("pending_queue", "discovery_queue"):
        queue = state.get(queue_name)
        if isinstance(queue, dict):
            queue.pop(product_id, None)
        elif isinstance(queue, list):
            state[queue_name] = [
                item for item in queue
                if not (
                    isinstance(item, dict)
                    and str(item.get("product_id") or item.get("id") or "").lower() == product_id
                )
            ]

    _write_state(state)
    print(
        "ONE_TIME_PRODUCT_DELETE_SUMMARY "
        + json.dumps({
            "product_id": product_id,
            "telegram_ids_attempted": sorted(telegram_ids),
            "telegram_deleted": sum(v == "deleted" for v in result_telegram.values()),
            "telegram_already_absent": sum(v == "already_absent" for v in result_telegram.values()),
            "bale_ids_attempted": sorted(bale_ids),
            "bale_deleted": sum(v == "deleted" for v in result_bale.values()),
            "bale_already_absent": sum(v == "already_absent" for v in result_bale.values()),
            "delete_failures": len(failures),
            "history_scan_ok": history_scan_ok,
            "permanent_exclusion_added": False,
            "repeat_cooldown_hours": 24,
            "suppression_reason": "one_time_product_removal_only",
        }, ensure_ascii=False, sort_keys=True)
    )
    return 1 if failures else 0


def _run_duplicate_cleanup(state, apply=True):
    """Delete older duplicate product posts while keeping one copy of each live offer."""
    if not BOT_TOKEN:
        print("DUPLICATE_CLEANUP_ABORTED reason=telegram_bot_token_missing")
        return 2
    published = state.get("published", {})
    if not isinstance(published, dict):
        print("DUPLICATE_CLEANUP_ABORTED reason=published_state_invalid")
        return 2

    max_pages = max(1, min(80, int(os.getenv("AFFILIO_DUPLICATE_SCAN_PAGES", "30"))))
    try:
        posts = fetch_public_channel_posts(max_pages=max_pages)
    except Exception as exc:
        print(f"DUPLICATE_SCAN_ABORTED error={type(exc).__name__} detail={str(exc)[:160]!r}")
        print("No channel posts were deleted because the live history scan failed.")
        return 2
    if not posts:
        print("DUPLICATE_SCAN_ABORTED reason=no_public_posts_returned")
        return 2

    product_for_message = {}
    sent_button_for_message = {}
    for product_id, record in _iter_post_records(published):
        key = str(product_id or "").lower()
        if not re.fullmatch(r"(?:dkp|snp)-\d+", key):
            key = _product_id_from_public_url(record.get("product_url", ""))
        raw_id = record.get("telegram_message_id")
        if str(raw_id or "").isdigit():
            product_for_message[int(raw_id)] = key
            delivery = record.get("delivery_status")
            sent_button_for_message[int(raw_id)] = (
                isinstance(delivery, dict) and delivery.get("telegram") == "sent"
            )

    groups = {}
    for message_id, post in posts.items():
        caption_text = str(post.get("caption_text") or "")
        if not caption_text.strip():
            continue
        title = _extract_legacy_caption_fields(caption_text).get("title", "")
        product_ids = set(post.get("product_ids") or [])
        known = product_for_message.get(int(message_id))
        if known:
            product_ids.add(known)
        if not title and not product_ids:
            continue
        if len(product_ids) == 1:
            key = ("product", next(iter(product_ids)))
        elif len(product_ids) > 1:
            print(f"DUPLICATE_SCAN_SKIP_AMBIGUOUS message_id={message_id} product_ids={sorted(product_ids)}")
            continue
        else:
            normalised_title = _normalise_duplicate_title(title)
            if len(normalised_title) < 12:
                continue
            key = ("title", normalised_title)
        post["dedupe_key"] = key
        post["dedupe_title"] = title
        post["dedupe_has_button"] = bool(
            post.get("purchase_button_visible") or sent_button_for_message.get(int(message_id), False)
        )
        groups.setdefault(key, []).append(int(message_id))

    duplicate_groups = [
        (key, sorted(set(message_ids)))
        for key, message_ids in groups.items()
        if len(set(message_ids)) > 1
    ]
    duplicate_groups.sort(key=lambda item: item[1][0])
    deleted_telegram = absent_telegram = failed_telegram = 0
    state_changed = False

    for key, message_ids in duplicate_groups:
        winner = max(message_ids, key=lambda mid: (
            bool(posts.get(mid, {}).get("dedupe_has_button") or sent_button_for_message.get(mid, False)),
            int(mid),
        ))
        print(f"DUPLICATE_GROUP platform=telegram key={key[1]} ids={message_ids} keep={winner}")
        for message_id in message_ids:
            if message_id == winner:
                continue
            if not apply:
                print(f"DUPLICATE_WOULD_DELETE platform=telegram message_id={message_id} keep={winner}")
                continue
            try:
                outcome = _telegram_delete(int(message_id))
                if outcome == "deleted":
                    deleted_telegram += 1
                else:
                    absent_telegram += 1
                for _record_product_id, record in _iter_post_records(published):
                    if str(record.get("telegram_message_id") or "").isdigit() and int(record["telegram_message_id"]) == int(message_id):
                        record["expiry_status"] = outcome
                        record["expired_deleted_at" if outcome == "deleted" else "expiry_absent_at"] = datetime.now(timezone.utc).isoformat()
                        state_changed = True
                print(f"DUPLICATE_DELETE_RESULT platform=telegram message_id={message_id} keep={winner} outcome={outcome}")
            except Exception as exc:
                failed_telegram += 1
                print(f"DUPLICATE_DELETE_FAILED platform=telegram message_id={message_id} keep={winner} error={type(exc).__name__}: {str(exc)[:150]}")
            time.sleep(BOT_API_MIN_GAP_SECONDS)

    # Bale's Bot API cannot enumerate channel history: only delete duplicates whose IDs are tracked.
    bale_groups = {}
    for product_id, record in _iter_post_records(published):
        key = str(product_id or "").lower()
        if not re.fullmatch(r"(?:dkp|snp)-\d+", key):
            key = _product_id_from_public_url(record.get("product_url", ""))
        raw_id = record.get("bale_message_id")
        status = str(record.get("bale_expiry_status") or "")
        if not key or not str(raw_id or "").isdigit() or status in {"deleted", "already_absent"}:
            continue
        bale_groups.setdefault(key, []).append(int(raw_id))
    deleted_bale = absent_bale = failed_bale = 0
    for product_id, ids in sorted(bale_groups.items()):
        ids = sorted(set(ids))
        if len(ids) < 2:
            continue
        winner = ids[-1]
        print(f"DUPLICATE_GROUP platform=bale product_id={product_id} ids={ids} keep={winner}")
        for message_id in ids[:-1]:
            if not apply:
                print(f"DUPLICATE_WOULD_DELETE platform=bale message_id={message_id} keep={winner}")
                continue
            try:
                outcome = _bale_delete(message_id)
                if outcome == "deleted":
                    deleted_bale += 1
                else:
                    absent_bale += 1
                for _record_product_id, record in _iter_post_records(published):
                    if str(record.get("bale_message_id") or "").isdigit() and int(record["bale_message_id"]) == int(message_id):
                        record["bale_expiry_status"] = outcome
                        record["bale_expired_deleted_at" if outcome == "deleted" else "bale_expiry_absent_at"] = datetime.now(timezone.utc).isoformat()
                        state_changed = True
                print(f"DUPLICATE_DELETE_RESULT platform=bale message_id={message_id} keep={winner} outcome={outcome}")
            except Exception as exc:
                failed_bale += 1
                print(f"DUPLICATE_DELETE_FAILED platform=bale message_id={message_id} keep={winner} error={type(exc).__name__}: {str(exc)[:150]}")
            time.sleep(BOT_API_MIN_GAP_SECONDS)

    if apply and state_changed:
        _write_state(state)
        print("DUPLICATE_STATE_UPDATED=true")
    summary = {
        "mode": "apply" if apply else "dry_run",
        "telegram_groups": len(duplicate_groups),
        "telegram_deleted": deleted_telegram,
        "telegram_already_absent": absent_telegram,
        "telegram_failed": failed_telegram,
        "bale_deleted_from_tracked_ids": deleted_bale,
        "bale_already_absent": absent_bale,
        "bale_failed": failed_bale,
        "posts_scanned": len(posts),
        "max_pages": max_pages,
    }
    print("DUPLICATE_CLEANUP_FINAL " + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 1 if failed_telegram or failed_bale else 0


def _is_valid_affilio_tracking_url(value):
    try:
        parsed = urlsplit(str(value or "").strip())
        destinations = parse_qs(parsed.query, keep_blank_values=True).get("p", [])
        destination = urlsplit(destinations[0]) if len(destinations) == 1 else None
    except Exception:
        return False
    return bool(
        parsed.scheme == "https"
        and (parsed.hostname or "").lower() == "aflo.ir"
        and parsed.path == "/QekEYTRg"
        and destination is not None
        and destination.scheme == "https"
        and (
            ((destination.hostname or "").lower() == "www.digikala.com"
             and re.fullmatch(r"/product/dkp-\d+/", destination.path, re.IGNORECASE))
            or ((destination.hostname or "").lower() == "snappshop.ir"
                and re.fullmatch(r"/product/snp-\d+", destination.path, re.IGNORECASE))
        )
    )


def _build_affilio_tracking_url(product_url):
    """Build the confirmed OfferChin Affilio link for either supported retailer."""
    try:
        parsed = urlsplit(str(product_url or "").strip())
    except Exception:
        return ""
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"https", "http"}:
        return ""
    if host in {"digikala.com", "www.digikala.com"}:
        match = re.fullmatch(r"/product/(dkp-\d+)/?", parsed.path, re.IGNORECASE)
        canonical = f"https://www.digikala.com/product/{match.group(1).lower()}/" if match else ""
    elif host == "snappshop.ir":
        match = re.fullmatch(r"/product/(snp-\d+)/?", parsed.path, re.IGNORECASE)
        canonical = f"https://snappshop.ir/product/{match.group(1).lower()}" if match else ""
    else:
        canonical = ""
    if not canonical:
        return ""
    result = "https://aflo.ir/QekEYTRg?p=" + quote(canonical, safe="")
    return result if _is_valid_affilio_tracking_url(result) else ""


def _telegram_edit_caption(message_id, caption, remove_purchase_button=False, affiliate_url=""):
    """Edit a caption only when a verified purchase button can be attached."""
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    if remove_purchase_button:
        raise RuntimeError("Refusing to remove the purchase button; expired posts must be deleted instead")
    if not _is_valid_affilio_tracking_url(affiliate_url):
        raise RuntimeError("Refusing to edit a post without a verified Affilio purchase button")
    payload = {
        "chat_id": CHAT_ID,
        "message_id": int(message_id),
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": json.dumps({
            "inline_keyboard": [[{
                "text": "🛍️ مشاهده و خرید از دیجی‌کالا",
                "url": affiliate_url,
            }]]
        }, ensure_ascii=False),
    }
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
            if "message is not modified" in description.lower():
                return "edited"
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
        if "message is not modified" in description.lower():
            return "edited"
        if "retry after" in description.lower() and attempt < 3:
            wait_match = re.search(r"retry after\s+(\d+)", description.lower())
            pause = min(60, int(wait_match.group(1)) if wait_match else 5)
            print(f"TELEGRAM_HISTORY_EDIT_RATE_LIMIT message_id={message_id} retry_after={pause}s")
            time.sleep(pause + 1)
            continue
        raise RuntimeError(description[:180])
    raise RuntimeError("Telegram editMessageCaption retry limit reached")


def _telegram_mark_expired(message_id, title):
    raise RuntimeError("Expired posts must be deleted; purchase-button removal is prohibited")


def _telegram_mark_deadline_unavailable(message_id, title):
    raise RuntimeError("Unverified expiry is not proof of expiry; purchase-button removal is prohibited")


def _bale_mark_expired(message_id, title):
    raise RuntimeError("Expired posts must be deleted; purchase-button removal is prohibited")


def _bale_mark_deadline_unavailable(message_id, title):
    raise RuntimeError("Unverified expiry is not proof of expiry; purchase-button removal is prohibited")


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
    """Repair legacy captions without trusting caption text as expiry authority.

    Deletion is exclusively handled from persisted, verified DigiKala deadlines
    or a live product-status confirmation. A public caption is not a source of
    truth for deletion because old countdowns can drift.
    """
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
    non_editable_statuses = {"deleted", "already_absent"}
    for message_id, post in sorted(posts.items()):
        caption_text = str(post.get("caption_text") or "")
        caption_html = str(post.get("caption_html") or "")
        if not caption_text.strip():
            continue

        record = tracked_by_message_id.get(int(message_id))
        if record is None:
            if not _looks_like_offer_post(caption_text):
                continue

            product_ids = sorted({
                str(value).lower()
                for value in (post.get("product_ids") or [])
                if re.fullmatch(r"(?:dkp|snp)-\d+", str(value).lower())
            })
            purchase_button_visible = bool(post.get("purchase_button_visible")) and len(product_ids) == 1

            # Never leave an untracked buttonless advert in the public channel.
            # When the platform cannot confirm deletion, leave it unchanged and retry
            # next cycle rather than editing it into another buttonless caption.
            if not purchase_button_visible:
                try:
                    outcome = _telegram_delete(int(message_id))
                    if outcome in {"deleted", "already_absent"}:
                        if outcome == "deleted":
                            deleted += 1
                        print(
                            f"PUBLIC_HISTORY_UNTRACKED_NO_BUTTON_REMOVED message_id={message_id} "
                            f"outcome={outcome}"
                        )
                    else:
                        print(
                            f"PUBLIC_HISTORY_UNTRACKED_NO_BUTTON_DELETE_UNCONFIRMED "
                            f"message_id={message_id} outcome={outcome!r}"
                        )
                except Exception as exc:
                    print(
                        f"PUBLIC_HISTORY_UNTRACKED_NO_BUTTON_DELETE_FAILED message_id={message_id} "
                        f"error={type(exc).__name__} detail={str(exc)[:120]!r}"
                    )
                continue

            pid = product_ids[0]
            canonical_url = f"https://www.digikala.com/product/{pid}/"
            affiliate_url = _build_affilio_tracking_url(canonical_url)
            if not affiliate_url:
                print(
                    f"PUBLIC_HISTORY_UNTRACKED_REPAIR_DEFERRED message_id={message_id} "
                    "reason=affiliate_url_unavailable; existing keyboard left untouched"
                )
                continue

            # If this product already has a live Telegram post, keep it and remove
            # this untracked duplicate without changing the product's cooldown.
            existing_record = published.get(pid) if isinstance(published, dict) else None
            existing_tg_id = str((existing_record or {}).get("telegram_message_id") or "")
            existing_tg_status = str((existing_record or {}).get("expiry_status") or "")
            if (
                existing_tg_id.isdigit()
                and int(existing_tg_id) != int(message_id)
                and existing_tg_status not in non_editable_statuses
            ):
                try:
                    outcome = _telegram_delete(int(message_id))
                    if outcome in {"deleted", "already_absent"}:
                        if outcome == "deleted":
                            deleted += 1
                        print(
                            f"PUBLIC_HISTORY_UNTRACKED_DUPLICATE_REMOVED product_id={pid} "
                            f"message_id={message_id} kept={existing_tg_id} outcome={outcome}"
                        )
                    else:
                        print(
                            f"PUBLIC_HISTORY_UNTRACKED_DUPLICATE_DELETE_UNCONFIRMED "
                            f"product_id={pid} message_id={message_id} outcome={outcome!r}"
                        )
                except Exception as exc:
                    print(
                        f"PUBLIC_HISTORY_UNTRACKED_DUPLICATE_DELETE_FAILED product_id={pid} "
                        f"message_id={message_id} error={type(exc).__name__}"
                    )
                continue

            fields = _extract_legacy_caption_fields(caption_text)
            caption = _build_legacy_repaired_caption(fields, None, now, affiliate_url=affiliate_url)
            try:
                result = _telegram_edit_caption(
                    int(message_id), caption, affiliate_url=affiliate_url
                )
                if result != "edited":
                    print(
                        f"PUBLIC_HISTORY_UNTRACKED_REPAIR_UNAVAILABLE product_id={pid} "
                        f"message_id={message_id} result={result}"
                    )
                    continue

                # Adopt the post so direct DigiKala lookup and expiry retries manage it.
                # Preserve any older campaign as its own history record; do not copy an
                # old deadline onto a newly discovered channel post.
                if isinstance(existing_record, dict):
                    prior = dict(existing_record)
                    prior.pop("post_history", None)
                    history = list(existing_record.get("post_history") or [])
                    if any(
                        str(prior.get(key) or "").isdigit()
                        for key in ("telegram_message_id", "bale_message_id")
                    ):
                        history.append(prior)
                    record = {
                        key: value for key, value in existing_record.items()
                        if key not in {
                            "telegram_message_id", "bale_message_id", "expiry_status",
                            "bale_expiry_status", "expires_at", "expiry_source",
                            "expiry_estimated", "expiry_deadline_verified_directly",
                            "expiry_deadline_verified_from_site_card",
                        }
                    }
                    record["post_history"] = history[-100:]
                else:
                    record = {}

                record.update({
                    "title": fields.get("title") or "پیشنهاد شگفت‌انگیز دیجی‌کالا",
                    "product_url": canonical_url,
                    "telegram_message_id": int(message_id),
                    "ts": now.timestamp(),
                    "expires_at": "",
                    "expiry_source": "unavailable",
                    "expiry_estimated": False,
                    "expiry_status": "unknown",
                    "caption_deadline_format_version": CAPTION_FORMAT_VERSION,
                    "caption_static_migrated_at": now.isoformat(),
                })
                record.pop("expiry_deadline_verified_directly", None)
                record.pop("expiry_deadline_verified_from_site_card", None)
                published[pid] = record
                changed = True
                reformatted += 1
                print(
                    f"PUBLIC_HISTORY_UNTRACKED_ADOPTED product_id={pid} "
                    f"message_id={message_id} button=restored countdown=removed"
                )
            except Exception as exc:
                print(
                    f"PUBLIC_HISTORY_UNTRACKED_REPAIR_FAILED product_id={pid} "
                    f"message_id={message_id} error={type(exc).__name__} detail={str(exc)[:140]!r}"
                )
            continue
        # Public history confirms this message still exists. If persisted state says
        # it was deleted, treat that status as stale and re-evaluate the real message.
        if str(record.get("expiry_status") or "") in non_editable_statuses:
            record["expiry_status"] = "tracked" if _has_verified_deadline(record) else "unknown"
            record.pop("expired_deleted_at", None)
            changed = True
            print(
                f"PUBLIC_HISTORY_TERMINAL_STATE_REOPENED message_id={message_id} "
                f"status={record['expiry_status']} reason=public_preview_confirms_presence"
            )

        fields = _extract_legacy_caption_fields(caption_text)
        fields["title"] = fields.get("title") or record.get("title") or "پیشنهاد ویژه"
        fields["current_price"] = (
            fields.get("current_price") or record.get("posted_current_price") or record.get("current_price")
        )
        fields["original_price"] = (
            fields.get("original_price") or record.get("posted_original_price") or record.get("original_price")
        )
        fields["discount_percent"] = fields.get("discount_percent") or record.get("discount_percent")
        deadline_text = parse_expiry(record.get("expires_at"))
        deadline = None
        if _has_verified_deadline(record) and deadline_text:
            try:
                deadline = datetime.fromisoformat(deadline_text)
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                deadline = deadline.astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError):
                deadline = None
        try:
            caption_version = int(record.get("caption_deadline_format_version") or 0)
        except (TypeError, ValueError, OverflowError):
            caption_version = 0
        button_state_known = "purchase_button_visible" in post
        button_missing = button_state_known and not bool(post.get("purchase_button_visible"))
        needs_static_migration = (
            button_missing
            or caption_version < CAPTION_FORMAT_VERSION
            or bool(record.get("deadline_caption_refresh_required"))
            or str(record.get("expiry_status") or "") in {
                "delete_failed", "expired_marked", "deadline_unavailable_marked",
                "deadline_unavailable_delete_failed",
            }
            or _caption_needs_repair(caption_html, caption_text, fields, deadline, now)
        )
        if not needs_static_migration:
            continue
        record_product_url = str(record.get("product_url") or "").strip()
        if not record_product_url:
            ids = [
                str(value).lower() for value in (post.get("product_ids") or [])
                if re.fullmatch(r"(?:dkp|snp)-\d+", str(value).lower())
            ]
            if len(ids) == 1:
                record_product_url = (
                    f"https://snappshop.ir/product/{ids[0]}"
                    if ids[0].startswith("snp-")
                    else f"https://www.digikala.com/product/{ids[0]}/"
                )
        affiliate_url = _build_affilio_tracking_url(record_product_url)
        if not affiliate_url:
            if button_missing:
                # Never leave a known buttonless tracked post live if its approved
                # purchase destination cannot be rebuilt.
                try:
                    outcome = _telegram_delete(int(message_id))
                    if outcome in {"deleted", "already_absent"}:
                        if outcome == "deleted":
                            deleted += 1
                        record["expiry_status"] = outcome
                        record["expired_deleted_at" if outcome == "deleted" else "expiry_last_absent_at"] = now.isoformat()
                        changed = True
                        print(
                            f"PUBLIC_HISTORY_NO_BUTTON_REMOVED message_id={message_id} "
                            f"outcome={outcome} reason=affiliate_url_unavailable"
                        )
                    else:
                        print(
                            f"PUBLIC_HISTORY_NO_BUTTON_DELETE_UNCONFIRMED message_id={message_id} "
                            f"outcome={outcome!r}"
                        )
                except Exception as exc:
                    print(
                        f"PUBLIC_HISTORY_NO_BUTTON_DELETE_FAILED message_id={message_id} "
                        f"error={type(exc).__name__} detail={str(exc)[:140]!r}"
                    )
            else:
                print(
                    f"PUBLIC_HISTORY_CAPTION_REPAIR_SKIPPED message_id={message_id} "
                    "reason=affiliate_url_unavailable; existing keyboard left untouched"
                )
            continue
        caption = _build_legacy_repaired_caption(fields, deadline, now, affiliate_url=affiliate_url)
        try:
            result = _telegram_edit_caption(int(message_id), caption, affiliate_url=affiliate_url)
            if result == "edited":
                reformatted += 1
                record["caption_deadline_format_version"] = CAPTION_FORMAT_VERSION
                record["caption_static_migrated_at"] = now.isoformat()
                record["caption_countdown_refreshed_at"] = now.isoformat()
                record["caption_without_expiry_migrated_at"] = now.isoformat()
                if record.get("expiry_status") in {
                    "deadline_unavailable_marked", "deadline_unavailable_delete_failed", "unknown", "expired_marked",
                }:
                    record["expiry_status"] = "tracked" if deadline is not None else "unknown"
                changed = True
                print(f"PUBLIC_HISTORY_CAPTION_REPAIRED message_id={message_id} button=restored")
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
    """Preserve posts when their deadline cannot be verified.

    Missing or estimated deadlines must never be treated as proof that an offer
    expired. Explicit, verified deadlines are handled by _delete_expired_posts.
    The state flag limits logging noise while leaving the record eligible for a
    later live-feed sync or product-status probe.
    """
    changed = False
    deleted = 0
    marked = 0
    platforms = (
        ("telegram", "telegram_message_id", "expiry_status"),
        ("bale", "bale_message_id", "bale_expiry_status"),
    )
    for pid, rec in _iter_post_records(published):
        if not isinstance(rec, dict):
            continue
        raw_expiry = parse_expiry(rec.get("expires_at"))
        deadline = None
        if raw_expiry:
            deadline = datetime.fromisoformat(raw_expiry)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            if deadline <= now:
                # The normal explicit-deadline path handles expiry and retries.
                continue
            if _has_verified_deadline(rec):
                continue

        reason = "missing_deadline" if deadline is None else "deadline_not_verified"
        for platform, id_field, status_field in platforms:
            raw_id = rec.get(id_field)
            if not str(raw_id or "").isdigit():
                continue
            if rec.get(status_field) in {"deleted", "already_absent"}:
                continue
            marker = f"{platform}_unverified_deadline_preserved_at"
            if rec.get(marker):
                continue
            rec[marker] = now.isoformat()
            changed = True
            print(
                f"DEADLINE_UNVERIFIED_PRESERVED platform={platform} product_id={pid} "
                f"message_id={int(raw_id)} reason={reason}; awaiting_reverification"
            )
    return changed, deleted, marked

def _confirm_expiry_for_deletion(product_id, record, now, budget=None):
    """Reconfirm a near-expiry offer through DigiKala's own product API before deletion.

    A first-party feed confirmation can be used while fresh. A cached/MCP offer-card
    deadline must be rechecked against the current product API at the removal cutoff.
    If DigiKala returns no usable timer or direct evidence that the offer ended, retain
    the post and its purchase button until the next scheduled check.
    """
    interval = LIVE_DEADLINE_SYNC_INTERVAL_SECONDS

    def is_fresh(value):
        parsed = parse_expiry(value)
        if not parsed:
            return False
        try:
            checked = datetime.fromisoformat(parsed)
        except ValueError:
            return False
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        age = (now - checked.astimezone(timezone.utc)).total_seconds()
        return -60 <= age <= interval

    source = str(record.get("expiry_source") or "")
    direct_source = source in {"digikala_live_deals_feed", "digikala_product_detail_api"}
    if (
        direct_source
        and _has_verified_deadline(record)
        and is_fresh(record.get("expiry_last_direct_verification_at"))
    ):
        return "confirmed", False
    if (
        source == "live_product_stock_or_price"
        and is_fresh(record.get("expiry_last_direct_verification_at"))
    ):
        return "confirmed", False

    previous_check = parse_expiry(record.get("expiry_last_removal_check_at"))
    if previous_check and is_fresh(previous_check):
        previous_result = str(record.get("expiry_last_removal_check_result") or "")
        return ("confirmed" if previous_result == "confirmed" else "inconclusive"), False

    if isinstance(budget, dict):
        remaining = int(budget.get("remaining", 0) or 0)
        if remaining <= 0:
            print(
                f"EXPIRY_DIRECT_RECHECK_DEFERRED product_id={product_id} "
                "reason=per-run-direct-check-budget; post_and_purchase_button_preserved=true"
            )
            return "inconclusive", False
        budget["remaining"] = remaining - 1

    before = dict(record)
    snapshot = fetch_live_product_status(product_id)
    record["expiry_last_removal_check_at"] = now.isoformat()
    if not snapshot:
        record["expiry_last_removal_check_result"] = "inconclusive"
        changed = record != before
        print(
            f"EXPIRY_DIRECT_RECHECK_UNCONFIRMED product_id={product_id} "
            "reason=direct_product_api_returned_no_usable_status; "
            "post_and_purchase_button_preserved=true"
        )
        return "inconclusive", changed

    direct_deadline = (
        parse_expiry(snapshot.get("deal_expires_at"))
        if snapshot.get("expiry_verified_directly") is True else ""
    )
    record["last_seen_current_price"] = snapshot.get("current_price")
    record["last_seen_in_stock"] = snapshot.get("in_stock")
    if direct_deadline:
        previous_deadline = parse_expiry(record.get("expires_at"))
        record["expires_at"] = direct_deadline
        record["expiry_source"] = "digikala_product_detail_api"
        record["expiry_deadline_verified_directly"] = True
        record["expiry_deadline_verified_from_site_card"] = False
        record["expiry_estimated"] = False
        record["expiry_last_direct_verification_at"] = now.isoformat()
        record["expiry_last_removal_check_result"] = "confirmed"
        record.pop("expiry_reason", None)
        print(
            f"EXPIRY_DIRECT_PRODUCT_RECHECK product_id={product_id} "
            f"previous={previous_deadline or 'missing'} live={direct_deadline}"
        )
        return "confirmed", True

    # When DigiKala directly reports no stock or a material price reversion, the
    # offer is no longer purchasable even if its card no longer carries a timer.
    reason = ""
    if snapshot.get("in_stock") is False:
        reason = "out_of_stock"
    else:
        try:
            posted_price = int(record.get("posted_current_price") or 0)
            live_price = int(snapshot.get("current_price") or 0)
            if posted_price > 0 and live_price > posted_price * 1.05:
                reason = "price_reverted"
        except (TypeError, ValueError, OverflowError):
            pass

    if reason:
        record["expires_at"] = now.isoformat()
        record["expiry_source"] = "live_product_stock_or_price"
        record["expiry_deadline_verified_directly"] = True
        record["expiry_deadline_verified_from_site_card"] = False
        record["expiry_estimated"] = False
        record["expiry_last_direct_verification_at"] = now.isoformat()
        record["expiry_last_removal_check_result"] = "confirmed"
        record["expiry_reason"] = reason
        print(
            f"EXPIRY_DIRECT_PRODUCT_INVALIDATION product_id={product_id} "
            f"reason={reason} current_price={snapshot.get('current_price')}"
        )
        return "confirmed", True

    # The verified site-card deadline already reached its configured removal cutoff
    # before this confirmation is called. If DigiKala returns a usable live product
    # but no active campaign timer, honor that source-backed cutoff instead of
    # leaving the promotion public indefinitely because the detail API omits a timer.
    if (
        source == "digikala_mcp_offer_card"
        and _has_verified_deadline(record)
        and snapshot.get("expiry_verified_directly") is False
        and (snapshot.get("current_price") is not None or snapshot.get("in_stock") is not None)
    ):
        record["expiry_last_removal_check_result"] = "confirmed"
        print(
            f"EXPIRY_CARD_DEADLINE_CONFIRMED product_id={product_id} "
            f"reason=verified_site_card_deadline_passed_without_active_timer"
        )
        return "confirmed", True

    record["expiry_last_removal_check_result"] = "inconclusive"
    print(
        f"EXPIRY_DIRECT_RECHECK_UNCONFIRMED product_id={product_id} "
        "reason=no_current_timer_or_proof_offer_ended; "
        "post_and_purchase_button_preserved=true"
    )
    return "inconclusive", record != before



def _record_has_active_publication(record):
    """Return whether at least one tracked publication is still potentially public."""
    if not isinstance(record, dict):
        return False
    terminal = {"deleted", "already_absent"}
    for id_field, status_field in (
        ("telegram_message_id", "expiry_status"),
        ("bale_message_id", "bale_expiry_status"),
    ):
        raw_id = str(record.get(id_field) or "")
        if raw_id.isdigit() and record.get(status_field) not in terminal:
            return True
    video_id = str(record.get("youtube_video_id") or "").strip()
    if video_id and record.get("youtube_expiry_status") not in terminal:
        return True
    video_hash = str(record.get("aparat_video_hash") or "").strip()
    if video_hash and record.get("aparat_expiry_status") not in terminal:
        return True
    return False


def _mark_price_invalid(record, product_id, reason, posted_price, live_price, now):
    """Turn a directly verified stale-price post into a normal permanent-deletion job."""
    record["price_audit_status"] = "invalidated"
    record["price_audit_reason"] = reason
    record["price_audit_posted_price"] = posted_price
    record["price_audit_live_price"] = live_price
    record["price_audit_invalidated_at"] = now.isoformat()
    record["expires_at"] = now.isoformat()
    record["expiry_source"] = "live_product_stock_or_price"
    record["expiry_deadline_verified_directly"] = True
    record["expiry_deadline_verified_from_site_card"] = False
    record["expiry_estimated"] = False
    record["expiry_last_direct_verification_at"] = now.isoformat()
    record["expiry_last_removal_check_at"] = now.isoformat()
    record["expiry_last_removal_check_result"] = "confirmed"
    record["expiry_reason"] = reason
    if str(record.get("telegram_message_id") or "").isdigit() and record.get("expiry_status") not in {"deleted", "already_absent"}:
        record["expiry_status"] = "expired_confirmed"
    if str(record.get("bale_message_id") or "").isdigit() and record.get("bale_expiry_status") not in {"deleted", "already_absent"}:
        record["bale_expiry_status"] = "expired_confirmed"


def _audit_live_prices(published, now=None, batch_size=None, interval_seconds=None, retry_seconds=None):
    """Continuously verify every active tracked offer price in bounded rotating batches.

    Only a usable first-party DigiKala product API response can invalidate a post.
    Missing/ambiguous responses are recorded and retried, never treated as proof
    that a price changed. Stale-price posts flow through the existing permanent
    deletion paths for Telegram, Bale, YouTube and Aparat.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    batch_size = batch_size if batch_size is not None else max(1, min(12, int(os.getenv("AFFILIO_PRICE_AUDIT_BATCH_SIZE", "10"))))
    interval_seconds = interval_seconds or max(
        300, min(21600, int(os.getenv("AFFILIO_PRICE_AUDIT_INTERVAL_SECONDS", "3600")))
    )
    retry_seconds = retry_seconds or max(
        300, min(3600, int(os.getenv("AFFILIO_PRICE_AUDIT_RETRY_SECONDS", "900")))
    )
    terminal = {"deleted", "already_absent"}
    groups = {}

    # Include current and historical posts separately: the same product may have
    # multiple public messages with different prices, and each message must be
    # judged against the price it actually advertised.
    for product_id, record in (published or {}).items():
        if not isinstance(record, dict):
            continue
        entries = [(record, False)]
        history = record.get("post_history")
        if isinstance(history, list):
            entries.extend((old, True) for old in history if isinstance(old, dict))
        for entry, is_history in entries:
            if not _record_has_active_publication(entry):
                continue
            try:
                posted_price = int(entry.get("posted_current_price") or 0)
            except (TypeError, ValueError, OverflowError):
                posted_price = 0
            if posted_price <= 0:
                continue
            # The current product-detail API is DigiKala-specific; do not
            # misinterpret SnappShop IDs as DigiKala product numbers.
            pid = str(product_id or "").strip().lower()
            if not pid.startswith("dkp-") or not pid[4:].isdigit():
                continue
            if entry.get("price_audit_status") == "invalidated":
                continue
            groups.setdefault(pid, []).append((entry, is_history, posted_price))

    due = []
    for product_id, entries in groups.items():
        next_checks = []
        for record, _is_history, _posted in entries:
            raw_next = parse_expiry(record.get("price_audit_next_check_at"))
            if not raw_next:
                next_checks.append(None)
                continue
            try:
                next_at = datetime.fromisoformat(raw_next)
                if next_at.tzinfo is None:
                    next_at = next_at.replace(tzinfo=timezone.utc)
                next_checks.append(next_at.astimezone(timezone.utc))
            except (TypeError, ValueError, OverflowError):
                next_checks.append(None)
        # A product is due if at least one active post for it needs its first
        # audit or its retry interval has elapsed.
        if any(value is None or value <= now for value in next_checks):
            oldest = min((value for value in next_checks if value is not None), default=datetime.min.replace(tzinfo=timezone.utc))
            due.append((oldest, product_id, entries))
    due.sort(key=lambda item: (item[0], item[1]))

    changed = False
    checked = mismatched = out_of_stock = unconfirmed = 0
    selected = due[:batch_size]

    # DigiKala product-detail requests can be slow during network degradation.
    # Fetch a small bounded batch concurrently, then apply state mutations in order.
    snapshots = {}
    if selected:
        with ThreadPoolExecutor(max_workers=min(4, len(selected))) as executor:
            futures = {
                product_id: executor.submit(fetch_live_product_status, product_id)
                for _oldest, product_id, _entries in selected
            }
            for product_id, future in futures.items():
                try:
                    snapshots[product_id] = future.result()
                except Exception as exc:
                    snapshots[product_id] = {}
                    print(
                        f"PRICE_AUDIT_PRODUCT_LOOKUP_FAILED product_id={product_id} "
                        f"error={type(exc).__name__}"
                    )

    for _oldest, product_id, entries in selected:
        checked += 1
        snapshot = snapshots.get(product_id) or {}
        live_price = snapshot.get("current_price") if isinstance(snapshot, dict) else None
        stock = snapshot.get("in_stock") if isinstance(snapshot, dict) else None
        usable_price = False
        try:
            live_price = int(live_price) if live_price is not None else None
            usable_price = live_price is not None and live_price > 0
        except (TypeError, ValueError, OverflowError):
            live_price = None
        live_original_price = snapshot.get("original_price") if isinstance(snapshot, dict) else None
        try:
            live_original_price = int(live_original_price) if live_original_price is not None else None
            if live_original_price is not None and live_original_price <= 0:
                live_original_price = None
        except (TypeError, ValueError, OverflowError):
            live_original_price = None

        direct_deadline = (
            parse_expiry(snapshot.get("deal_expires_at"))
            if isinstance(snapshot, dict) and snapshot.get("expiry_verified_directly") is True
            else ""
        )
        lookup_ok = bool(snapshot) and (usable_price or stock is False)
        checked_at = now.isoformat()

        if not lookup_ok:
            unconfirmed += 1
            for record, _is_history, _posted in entries:
                record["price_audit_last_checked_at"] = checked_at
                record["price_audit_next_check_at"] = (now + timedelta(seconds=retry_seconds)).isoformat()
                record["price_audit_status"] = "unconfirmed"
                record["price_audit_error"] = "no_usable_live_price_or_stock_status"
                changed = True
            print(f"PRICE_AUDIT_UNCONFIRMED product_id={product_id} retry_seconds={retry_seconds}")
            continue

        product_changed = False
        product_mismatches = 0
        product_out = stock is False
        for record, is_history, posted_price in entries:
            if not _record_has_active_publication(record):
                continue
            record["price_audit_last_checked_at"] = checked_at
            record["price_audit_next_check_at"] = (now + timedelta(seconds=interval_seconds)).isoformat()
            record["last_seen_current_price"] = live_price
            record["last_seen_original_price"] = live_original_price
            record["last_seen_in_stock"] = stock

            if product_out:
                _mark_price_invalid(record, product_id, "out_of_stock", posted_price, live_price, now)
                out_of_stock += 1
                product_changed = True
                changed = True
                continue
            if not usable_price:
                record["price_audit_status"] = "unconfirmed"
                record["price_audit_error"] = "live_price_unavailable"
                record["price_audit_next_check_at"] = (now + timedelta(seconds=retry_seconds)).isoformat()
                unconfirmed += 1
                changed = True
                continue
            record.pop("price_audit_error", None)
            posted_original_price = None
            try:
                raw_posted_original = record.get("posted_original_price") or record.get("original_price")
                posted_original_price = int(raw_posted_original) if raw_posted_original is not None else None
                if posted_original_price is not None and posted_original_price <= 0:
                    posted_original_price = None
            except (TypeError, ValueError, OverflowError):
                posted_original_price = None

            mismatch_fields = []
            if live_price != posted_price:
                mismatch_fields.append("current_price")
            # Only compare original/list prices when DigiKala returns a usable value;
            # a missing list price is inconclusive, not permission to delete.
            if (
                posted_original_price is not None
                and live_original_price is not None
                and posted_original_price != live_original_price
            ):
                mismatch_fields.append("original_price")

            if mismatch_fields:
                _mark_price_invalid(record, product_id, "price_mismatch", posted_price, live_price, now)
                record["price_audit_mismatch_fields"] = mismatch_fields
                record["price_audit_posted_original_price"] = posted_original_price
                record["price_audit_live_original_price"] = live_original_price
                mismatched += 1
                product_mismatches += 1
                product_changed = True
                changed = True
                print(
                    f"PRICE_AUDIT_INVALIDATED product_id={product_id} "
                    f"posted_price={posted_price} live_price={live_price} "
                    f"posted_original={posted_original_price} live_original={live_original_price} "
                    f"fields={','.join(mismatch_fields)} reason=price_mismatch historical={is_history}"
                )
                continue

            record["price_audit_status"] = "match"
            record["price_audit_posted_price"] = posted_price
            record["price_audit_live_price"] = live_price
            record["price_audit_posted_original_price"] = posted_original_price
            record["price_audit_live_original_price"] = live_original_price
            changed = True
            # Only refresh the current record's timer. A current campaign timer
            # must never be copied onto an older historical post for this product.
            if direct_deadline and not is_history:
                old_deadline = parse_expiry(record.get("expires_at"))
                if old_deadline != direct_deadline or record.get("expiry_source") != "digikala_product_detail_api":
                    record["expires_at"] = direct_deadline
                    record["expiry_source"] = "digikala_product_detail_api"
                    record["expiry_deadline_verified_directly"] = True
                    record["expiry_deadline_verified_from_site_card"] = False
                    record["expiry_estimated"] = False
                    changed = True
                record["expiry_last_direct_verification_at"] = checked_at
                record.pop("expiry_reason", None)
        if product_out and not product_mismatches:
            print(f"PRICE_AUDIT_INVALIDATED_PRODUCT product_id={product_id} reason=out_of_stock")
        elif not product_changed:
            print(
                f"PRICE_AUDIT_MATCH product_id={product_id} live_price={live_price} "
                f"active_posts={len(entries)}"
            )

    summary = {
        "products_due": len(due),
        "products_checked": checked,
        "price_mismatches": mismatched,
        "out_of_stock_posts": out_of_stock,
        "unconfirmed": unconfirmed,
        "remaining_due": max(0, len(due) - min(len(due), batch_size)),
    }
    if checked:
        print(
            "PRICE_AUDIT_SUMMARY "
            f"products_due={summary['products_due']} checked={checked} "
            f"price_mismatches={mismatched} out_of_stock_posts={out_of_stock} "
            f"unconfirmed={unconfirmed} remaining_due={summary['remaining_due']}"
        )
    return changed, summary


def _delete_expired_posts(published, now, mark_unknown=False, direct_confirm=None):
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
        if not _has_verified_deadline(rec):
            print(
                f"EXPIRY_DEADLINE_NOT_AUTHORITATIVE_PRESERVED product_id={pid} "
                f"source={rec.get('expiry_source') or 'missing'} "
                f"estimated={bool(rec.get('expiry_estimated'))}"
            )
            continue
        removal_deadline = expires_at - timedelta(minutes=POST_REMOVAL_BUFFER_MINUTES)
        if now < removal_deadline:
            if str(rec.get("telegram_message_id") or "").isdigit() and not rec.get("expiry_status"):
                rec["expiry_status"] = "tracked_estimated" if rec.get("expiry_estimated") else "tracked"
                changed = True
            if str(rec.get("bale_message_id") or "").isdigit() and not rec.get("bale_expiry_status"):
                rec["bale_expiry_status"] = "tracked_estimated" if rec.get("expiry_estimated") else "tracked"
                changed = True
            continue
        if rec.get("expiry_estimated") is True:
            # An estimated timestamp may guide caption wording, but must never
            # authorize destructive cleanup. Wait for a verified deadline or a
            # live product check that confirms the offer is no longer valid.
            if not rec.get("expiry_estimate_cutoff_preserved_at"):
                rec["expiry_estimate_cutoff_preserved_at"] = now.isoformat()
                changed = True
                print(
                    f"EXPIRY_ESTIMATED_DEADLINE_PRESERVED product_id={pid} "
                    f"reason=estimated_timestamp_not_authoritative"
                )
            continue
        if direct_confirm is not None:
            decision, verification_changed = direct_confirm(pid, rec, now)
            changed = changed or verification_changed
            if decision != "confirmed":
                continue
            # Direct confirmation may extend the offer past the former cached cutoff.
            expiry = parse_expiry(rec.get("expires_at"))
            if not expiry or not _has_verified_deadline(rec):
                continue
            expires_at = datetime.fromisoformat(expiry)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            removal_deadline = expires_at - timedelta(minutes=POST_REMOVAL_BUFFER_MINUTES)
            if now < removal_deadline:
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
                error_text = str(exc)[:180]
                rec[f"{platform}_expiry_last_delete_error"] = f"{type(exc).__name__}: {error_text}"
                # Never edit a live caption or remove its keyboard on delete failure.
                # Keep the purchase button intact and retry permanent deletion next cycle.
                rec[status_field] = "delete_failed"
                changed = True
                print(
                    f"EXPIRY_DELETE_FAILED platform={platform} product_id={pid} "
                    f"message_id={raw_id} error={type(exc).__name__} "
                    f"detail={error_text[:160]!r}; purchase_button_untouched=true"
                )
    return changed, deleted




def _delete_expired_aparat_videos(published, now, direct_confirm=None):
    """Permanently delete expired Aparat videos, hiding them only as a failure fallback."""
    changed = False
    try:
        from aparat_uploader import (
            delete_aparat_video,
            set_aparat_video_private,
            aparat_credentials_available,
        )
        credentials_ready = aparat_credentials_available()
    except Exception as exc:
        delete_aparat_video = None
        set_aparat_video_private = None
        credentials_ready = False
        print(f"APARAT_EXPIRY_SETUP_UNAVAILABLE error={type(exc).__name__}")

    terminal = {"deleted", "already_absent"}
    for pid, rec in _iter_post_records(published):
        if not isinstance(rec, dict):
            continue
        if not _has_verified_deadline(rec):
            continue
        video_hash = str(rec.get("aparat_video_hash") or "").strip()
        expiry_status = str(rec.get("aparat_expiry_status") or "")
        if not video_hash or expiry_status in terminal:
            continue
        # Estimated deadlines are not sufficient evidence for deleting a video.
        if rec.get("expiry_estimated") is True:
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
        if direct_confirm is not None:
            decision, confirmation_changed = direct_confirm(pid, rec, now)
            changed = changed or confirmation_changed
            if decision != "confirmed":
                continue
            expires = parse_expiry(rec.get("expires_at"))
            if not expires:
                continue
            deadline = datetime.fromisoformat(expires)
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
                if now < retry_at and not (
                    expiry_status == "pending_credentials" and credentials_ready
                ):
                    continue
            except ValueError:
                pass

        if not credentials_ready or delete_aparat_video is None:
            rec["aparat_expiry_status"] = "pending_credentials"
            rec["aparat_expiry_next_attempt_at"] = (now + timedelta(minutes=60)).isoformat()
            rec["aparat_expiry_last_error"] = "aparat_cookie_secret_missing"
            changed = True
            continue

        try:
            outcome = delete_aparat_video(video_hash)
            if outcome not in terminal:
                raise RuntimeError("Aparat deletion was not confirmed")
            rec["aparat_expiry_status"] = outcome
            rec["aparat_visibility"] = outcome
            rec["aparat_deleted_at" if outcome == "deleted" else "aparat_already_absent_at"] = now.isoformat()
            rec.pop("aparat_expiry_next_attempt_at", None)
            rec.pop("aparat_expiry_last_error", None)
            changed = True
            print(f"APARAT_EXPIRY_DELETE_OK product_id={pid} video_hash={video_hash} outcome={outcome}")
        except Exception as exc:
            # Primary action is permanent deletion. If Aparat's unsupported web
            # delete endpoint fails, make a best-effort privacy change while retrying deletion.
            fallback = "not_attempted"
            if set_aparat_video_private is not None:
                try:
                    set_aparat_video_private(video_hash)
                    rec["aparat_visibility"] = "private_waiting_for_delete"
                    fallback = "private"
                except Exception as private_exc:
                    fallback = f"failed:{type(private_exc).__name__}"
            attempts = int(rec.get("aparat_expiry_attempts", 0) or 0) + 1
            rec["aparat_expiry_attempts"] = attempts
            rec["aparat_expiry_status"] = "delete_retry"
            rec["aparat_expiry_next_attempt_at"] = (now + timedelta(minutes=30)).isoformat()
            rec["aparat_expiry_last_error"] = type(exc).__name__
            changed = True
            print(
                f"APARAT_EXPIRY_DELETE_FAILED product_id={pid} error={type(exc).__name__} "
                f"fallback={fallback} retry_attempt={attempts}"
            )

    return changed


def _delete_expired_youtube_videos(published, now, direct_confirm=None):
    """Permanently delete expired YouTube Shorts, using privacy only as a failure fallback."""
    changed = False
    try:
        from short_video import (
            delete_youtube_video,
            set_youtube_video_private,
            youtube_credentials_available,
        )
        credentials_ready = youtube_credentials_available()
    except Exception as exc:
        delete_youtube_video = None
        set_youtube_video_private = None
        credentials_ready = False
        print(f"YOUTUBE_EXPIRY_SETUP_UNAVAILABLE error={type(exc).__name__}")

    terminal = {"deleted", "already_absent"}
    for pid, rec in _iter_post_records(published):
        if not isinstance(rec, dict):
            continue
        if not _has_verified_deadline(rec):
            continue
        video_id = str(rec.get("youtube_video_id") or "").strip()
        expiry_status = str(rec.get("youtube_expiry_status") or "")
        if not video_id or expiry_status in terminal:
            continue
        # Estimated deadlines do not prove expiry; only verified deadlines
        # may trigger permanent removal of published videos.
        if rec.get("expiry_estimated") is True:
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
        if direct_confirm is not None:
            decision, confirmation_changed = direct_confirm(pid, rec, now)
            changed = changed or confirmation_changed
            if decision != "confirmed":
                continue
            expires = parse_expiry(rec.get("expires_at"))
            if not expires:
                continue
            deadline = datetime.fromisoformat(expires)
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
                if now < retry_at and not (
                    expiry_status == "pending_credentials" and credentials_ready
                ):
                    continue
            except ValueError:
                pass

        if not credentials_ready or delete_youtube_video is None:
            rec["youtube_expiry_status"] = "pending_credentials"
            rec["youtube_expiry_next_attempt_at"] = (now + timedelta(minutes=60)).isoformat()
            rec["youtube_expiry_last_error"] = "youtube_oauth_secrets_missing"
            changed = True
            continue

        try:
            outcome = delete_youtube_video(video_id)
            if outcome not in terminal:
                raise RuntimeError("YouTube deletion was not confirmed")
            rec["youtube_expiry_status"] = outcome
            rec["youtube_deleted_at" if outcome == "deleted" else "youtube_already_absent_at"] = now.isoformat()
            rec.pop("youtube_expiry_next_attempt_at", None)
            rec.pop("youtube_expiry_last_error", None)
            changed = True
            print(f"YOUTUBE_EXPIRY_DELETE_OK product_id={pid} video_id={video_id} outcome={outcome}")
        except Exception as exc:
            # Deletion remains the goal; best-effort privacy is only a guardrail if
            # a delete request fails, and the permanent delete will be retried.
            fallback = "not_attempted"
            if set_youtube_video_private is not None:
                try:
                    set_youtube_video_private(video_id)
                    rec["youtube_visibility"] = "private_waiting_for_delete"
                    fallback = "private"
                except Exception as private_exc:
                    fallback = f"failed:{type(private_exc).__name__}"
            attempts = int(rec.get("youtube_expiry_attempts", 0) or 0) + 1
            rec["youtube_expiry_attempts"] = attempts
            rec["youtube_expiry_status"] = "delete_retry"
            rec["youtube_expiry_next_attempt_at"] = (now + timedelta(minutes=30)).isoformat()
            rec["youtube_expiry_last_error"] = type(exc).__name__
            changed = True
            print(
                f"YOUTUBE_EXPIRY_DELETE_FAILED product_id={pid} error={type(exc).__name__} "
                f"fallback={fallback} retry_attempt={attempts}"
            )

    return changed


def run():
    state = _read_state()
    one_time_product_id = os.getenv("AFFILIO_DELETE_SPECIFIC_PRODUCT_ID", "").strip()
    if one_time_product_id:
        return _delete_one_specific_product(
            state,
            one_time_product_id,
            os.getenv("AFFILIO_DELETE_SPECIFIC_PRODUCT_TITLE", ""),
            os.getenv("AFFILIO_DELETE_SPECIFIC_PRODUCT_TELEGRAM_IDS", ""),
            os.getenv("AFFILIO_DELETE_SPECIFIC_PRODUCT_BALE_IDS", ""),
        )
    if os.getenv("AFFILIO_DEDUPLICATE_ONLY", "false").strip().lower() in {"1", "true", "yes", "on"}:
        return _run_duplicate_cleanup(state, apply=True)
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
    if feed_due and any(
        isinstance(rec, dict) and (
            (str(rec.get("telegram_message_id") or "").isdigit() and rec.get("expiry_status") not in {"deleted", "already_absent"})
            or (str(rec.get("bale_message_id") or "").isdigit() and rec.get("bale_expiry_status") not in {"deleted", "already_absent"})
        )
        for rec in published.values()
    ):
        live_expiries = {}
        try:
            # Only DigiKala's own endpoint can authorize a deadline-driven deletion.
            # The MCP wrapper may assist discovery, but is never expiry-deletion authority.
            active_required_ids = [
                str(pid) for pid, rec in published.items()
                if isinstance(rec, dict) and (
                    (str(rec.get("telegram_message_id") or "").isdigit() and rec.get("expiry_status") not in {"deleted", "already_absent"})
                    or (str(rec.get("bale_message_id") or "").isdigit() and rec.get("bale_expiry_status") not in {"deleted", "already_absent"})
                )
            ]
            live_expiries, live_sources = fetch_offer_deadlines(required_product_ids=active_required_ids)
        except Exception as exc:
            print(f"EXPIRY_DIRECT_FEED_LOOKUP_FAILED error={type(exc).__name__} detail={str(exc)[:140]!r}")
        if live_expiries:
            sync_summary = sync_live_offer_deadlines(published, live_expiries, now, live_sources=live_sources)
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

    direct_recheck_budget = {"remaining": DIRECT_PRODUCT_DETAIL_CHECK_LIMIT}
    def confirm_near_expiry(product_id, record, current_time):
        return _confirm_expiry_for_deletion(
            product_id, record, current_time, budget=direct_recheck_budget
        )

    pre_changed, pre_deleted = _delete_expired_posts(
        published, now, mark_unknown=True, direct_confirm=confirm_near_expiry
    )
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

    price_changed, price_summary = _audit_live_prices(published, now)
    changed = changed or price_changed
    if price_changed:
        # Persist audit decisions before deletion side effects so a transient bot
        # API failure cannot erase the verified reason for the next retry.
        _write_state(state)
        print("PRICE_AUDIT_STATE_SAVED")

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
    product_probe_count = 0
    max_product_probes = 3
    max_probe_candidates = max_product_probes * 2
    for pid, rec in probe_candidates[:max_probe_candidates]:
        if not isinstance(rec, dict) or _has_verified_deadline(rec):
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
        direct_product_deadline = (
            parse_expiry(snapshot.get("deal_expires_at"))
            if snapshot.get("expiry_verified_directly") is True else None
        )
        if direct_product_deadline:
            previous_deadline = parse_expiry(rec.get("expires_at"))
            rec["expires_at"] = direct_product_deadline
            rec["expiry_source"] = "digikala_product_detail_api"
            rec["expiry_deadline_verified_directly"] = True
            rec["expiry_deadline_verified_from_site_card"] = False
            rec["expiry_estimated"] = False
            rec["expiry_last_direct_verification_at"] = now.isoformat()
            rec.pop("expiry_reason", None)
            changed = True
            print(
                f"EXPIRY_DEADLINE_FROM_DIRECT_PRODUCT_API product_id={pid} "
                f"previous={previous_deadline or 'missing'} live={direct_product_deadline}"
            )
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
            rec["expiry_deadline_verified_directly"] = True
            rec["expiry_deadline_verified_from_site_card"] = False
            rec["expiry_estimated"] = False
            rec["expiry_last_direct_verification_at"] = now.isoformat()
            rec["expiry_last_removal_check_at"] = now.isoformat()
            rec["expiry_last_removal_check_result"] = "confirmed"
            rec["expiry_reason"] = reason
            rec["expiry_status"] = "expired_confirmed"
            changed = True
            print(f"EXPIRY_CONFIRMED_BY_LIVE_PRODUCT product_id={pid} reason={reason} current_price={current}")

    post_changed, post_deleted = _delete_expired_posts(
        published, now, mark_unknown=True, direct_confirm=confirm_near_expiry
    )
    changed = changed or post_changed
    deleted += post_deleted

    youtube_delete_changed = _delete_expired_youtube_videos(
        published, now, direct_confirm=confirm_near_expiry
    )
    changed = changed or youtube_delete_changed
    aparat_delete_changed = _delete_expired_aparat_videos(
        published, now, direct_confirm=confirm_near_expiry
    )
    changed = changed or aparat_delete_changed
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
