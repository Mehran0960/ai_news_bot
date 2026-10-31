#!/usr/bin/env python3
"""Incremental, resumable DigiKala catalog sweep for OfferChin.

The crawler only reads public DigiKala listing endpoints. It never publishes.
Every successful category page is checkpointed before the next request so a
transient failure cannot silently skip the page.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

try:
    from product_quality import is_publishable_product_title
except Exception:  # pragma: no cover - only used when run outside the package folder
    def is_publishable_product_title(value: object) -> bool:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return len(text) >= 5 and len(text.split()) >= 2


ROOT = Path(__file__).resolve().parent
SWEEP_STATE_PATH = ROOT / "catalog_sweep_state.json"
CANDIDATES_PATH = ROOT / "catalog_sweep_candidates.json"
PUBLISHER_STATE_PATH = ROOT / "state.json"

API_ROOT = "https://api.digikala.com"
DICTIONARY_URL = f"{API_ROOT}/v1/dictionaries/"
SEARCH_URL = f"{API_ROOT}/v1/search/"
REQUEST_TIMEOUT = (5, 18)
CATEGORY_REFRESH_HOURS = 24
CANDIDATE_TTL_HOURS = 72
MIN_CANDIDATE_DISCOUNT = 5
MAX_PAGES_PER_CATEGORY = 5000
MAX_RETAINED_CANDIDATES = 3000
MAX_PUBLISHER_SEEN_IDS = 12000
PUBLISHER_SEEN_TTL_DAYS = 45

PERSIAN_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬٫",
    "01234567890123456789,.",
)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.7",
    "Referer": "https://www.digikala.com/",
})


class CatalogSweepError(RuntimeError):
    """Raised when a page cannot be safely interpreted or checkpointed."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogSweepError(f"cannot_read_{path.name}:{type(exc).__name__}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _normal_int(value: Any, default: int = 0) -> int:
    try:
        normalized = str(value or "").translate(PERSIAN_DIGITS).replace(",", "").replace(" ", "")
        match = re.search(r"-?\d+", normalized)
        return int(match.group(0)) if match else default
    except (TypeError, ValueError, OverflowError):
        return default


def _normal_float(value: Any, default: float = 0.0) -> float:
    try:
        normalized = str(value or "").translate(PERSIAN_DIGITS).replace(",", "").replace(" ", "")
        match = re.search(r"-?\d+(?:\.\d+)?", normalized)
        return float(match.group(0)) if match else default
    except (TypeError, ValueError, OverflowError):
        return default


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _first_nonempty(record: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _category_id(record: dict) -> str:
    raw = _first_nonempty(record, ("category_id", "id", "value", "categoryId"))
    value = str(raw or "").strip()
    return value if value.isdigit() else ""


def _category_name(record: dict) -> str:
    raw = _first_nonempty(
        record, ("title_fa", "title", "name_fa", "name", "label", "category_title")
    )
    if isinstance(raw, dict):
        raw = _first_nonempty(raw, ("title_fa", "title", "name", "label"))
    return re.sub(r"\s+", " ", str(raw or "")).strip()[:120]


def extract_categories(payload: Any) -> list[dict]:
    """Extract category nodes from category_tree/mega_menu or search filters."""
    found: dict[str, dict] = {}
    child_keys = {
        "children", "childs", "categories", "sub_categories", "subcategories",
        "items", "nodes", "category_tree", "mega_menu",
    }

    def visit(value: Any, parent_id: str = "", depth: int = 0, category_context: bool = False):
        if isinstance(value, list):
            for child in value:
                visit(child, parent_id, depth, category_context)
            return
        if not isinstance(value, dict):
            return

        candidate_id = _category_id(value)
        candidate_name = _category_name(value)
        has_child_container = any(
            isinstance(value.get(key), (list, dict)) for key in child_keys
        )
        looks_like_category = bool(
            candidate_id and candidate_name and (
                category_context or has_child_container
                or any(key in value for key in ("slug", "category_slug", "url", "uri"))
            )
        )

        next_parent = parent_id
        next_depth = depth
        if looks_like_category:
            record = {
                "id": candidate_id,
                "name": candidate_name,
                "parent_id": parent_id,
                "depth": depth,
                "slug": str(value.get("slug") or value.get("category_slug") or "")[:160],
            }
            previous = found.get(candidate_id)
            if previous is None or (
                previous.get("parent_id") in ("", None) and parent_id
            ):
                found[candidate_id] = record
            next_parent = candidate_id
            next_depth = depth + 1

        for key, child in value.items():
            key_lower = str(key).lower()
            next_context = category_context or (
                "categor" in key_lower or "mega_menu" in key_lower or key_lower == "children"
            )
            if isinstance(child, (dict, list)):
                visit(child, next_parent, next_depth, next_context)

    visit(payload)

    # Some search API versions expose category facets instead of a tree.
    if not found:
        for node in _walk_dicts(payload):
            key = str(node.get("key") or node.get("name") or node.get("slug") or "").lower()
            if "categor" not in key and "دسته" not in key:
                continue
            for list_key in ("values", "options", "items", "children"):
                values = node.get(list_key)
                if not isinstance(values, list):
                    continue
                for item in values:
                    if not isinstance(item, dict):
                        continue
                    cid = _category_id(item)
                    name = _category_name(item)
                    if cid and name:
                        found.setdefault(cid, {
                            "id": cid, "name": name, "parent_id": "",
                            "depth": 0,
                            "slug": str(item.get("slug") or "")[:160],
                        })

    return sorted(found.values(), key=lambda row: (int(row["id"]), row["name"]))


def _request_json(session: requests.Session, url: str, params=None) -> dict:
    response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    if len(response.content) > 8_000_000:
        raise CatalogSweepError("api_response_exceeded_8mb")
    try:
        payload = response.json()
    except ValueError as exc:
        raise CatalogSweepError("api_returned_non_json") from exc
    if not isinstance(payload, dict):
        raise CatalogSweepError("api_payload_not_object")
    return payload


def discover_categories(session: requests.Session | None = None) -> list[dict]:
    """Refresh category IDs from DigiKala's public dictionaries, then search facets."""
    http = session or SESSION
    dictionary_types = (
        "states", "cities", "user_jobs", "mega_menu", "universal",
        "category_tree", "districts", "seo_content", "superapp_services",
    )
    params = []
    for index, kind in enumerate(dictionary_types):
        params.append((f"types[{index}]", kind))
        params.append((f"hashes[{index}]", ""))

    errors = []
    try:
        payload = _request_json(http, DICTIONARY_URL, params=params)
        categories = extract_categories(payload)
        if categories:
            return categories
        errors.append("dictionaries_no_category_nodes")
    except Exception as exc:
        errors.append(f"dictionaries_{type(exc).__name__}")

    try:
        payload = _request_json(http, SEARCH_URL, params={"page": 1})
        categories = extract_categories(payload)
        if categories:
            return categories
        errors.append("search_filters_no_category_nodes")
    except Exception as exc:
        errors.append(f"search_{type(exc).__name__}")

    raise CatalogSweepError("category_discovery_failed:" + ",".join(errors))


def _money_to_toman(raw: Any, currency: str = "") -> int:
    if raw is None:
        return 0
    amount = _normal_float(raw)
    if amount <= 0:
        return 0
    if str(currency or "").upper() == "IRR":
        amount /= 10
    result = int(round(amount))
    return result if result >= 1000 else 0


def _price_source_rows(product: dict) -> list[dict]:
    sources = []
    for key in ("price", "default_variant", "variant"):
        value = product.get(key)
        if isinstance(value, dict):
            if isinstance(value.get("price"), dict):
                sources.append(value["price"])
            sources.append(value)
    sources.append(product)
    return sources


def _listing_prices(product: dict) -> tuple[int, int, int, int]:
    current = 0
    original = 0
    discount = 0
    for source in _price_source_rows(product):
        if not discount:
            discount = max(0, min(100, _normal_int(source.get("discount_percent"))))
        if not current:
            for key in ("selling_price_toman", "selling_price_tooman", "price_toman"):
                current = _money_to_toman(source.get(key), "IRT")
                if current:
                    break
        if not current:
            for key in ("selling_price", "selling_price_rial", "price"):
                current = _money_to_toman(source.get(key), "IRR")
                if current:
                    break
        if not original:
            for key in ("rrp_price_toman", "original_price_toman", "list_price_toman"):
                original = _money_to_toman(source.get(key), "IRT")
                if original:
                    break
        if not original:
            for key in ("rrp_price", "rrp_price_rial", "original_price", "regular_price"):
                original = _money_to_toman(source.get(key), "IRR")
                if original:
                    break
    if not discount and current and original and original > current:
        discount = max(1, min(100, round(100 * (original - current) / original)))
    savings = max(0, original - current) if current and original > current else 0
    return current, original, discount, savings


def _listing_rating(product: dict) -> tuple[float, int]:
    rating = product.get("rating") if isinstance(product.get("rating"), dict) else {}
    stats = product.get("statistics") if isinstance(product.get("statistics"), dict) else {}
    sources = [rating, stats, product]
    score = 0.0
    reviews = 0
    for source in sources:
        if not score:
            for key in ("rate", "rating", "rating_value", "ratingValue", "average_rating"):
                score = _normal_float(source.get(key))
                if score > 0:
                    if score > 5 and score <= 100:
                        score /= 20
                    if score > 5:
                        score = 0.0
                    break
        if not reviews:
            for key in ("rate_count", "review_count", "rating_count", "count", "reviewCount"):
                reviews = max(0, _normal_int(source.get(key)))
                if reviews:
                    break
    return round(score, 2), reviews


def extract_product_rows(payload: Any) -> list[dict]:
    """Return compact listing cards, not deep product-detail records."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or "products" not in data:
        raise CatalogSweepError("search_payload_missing_data_products")
    products = data.get("products")
    if not isinstance(products, list):
        raise CatalogSweepError("search_payload_products_not_list")

    rows = []
    seen = set()
    for product in products:
        if not isinstance(product, dict):
            continue
        raw_url = product.get("url") or product.get("product_url") or product.get("web_url")
        if isinstance(raw_url, dict):
            raw_url = raw_url.get("uri") or raw_url.get("url")
        raw_id = product.get("id") or product.get("product_id")
        product_id = ""
        if isinstance(raw_url, str):
            match = re.search(r"/product/(dkp-\d+)", raw_url, re.I)
            if match:
                product_id = match.group(1).lower()
        if not product_id and str(raw_id or "").isdigit():
            product_id = f"dkp-{int(raw_id)}"
        if not product_id or product_id in seen:
            continue
        seen.add(product_id)

        title = str(
            product.get("title_fa") or product.get("product_title")
            or product.get("title") or ""
        ).strip()[:180]
        if not is_publishable_product_title(title):
            continue
        current, original, discount, savings = _listing_prices(product)
        rating, review_count = _listing_rating(product)
        rows.append({
            "product_id": product_id,
            "product_url": f"https://www.digikala.com/product/{product_id}/",
            "title": title,
            "current_price": current,
            "original_price": original,
            "discount_percent": discount,
            "savings_toman": savings,
            "rating": rating,
            "review_count": review_count,
            "source": "digikala_catalog_sweep",
            "last_seen_at": iso_now(),
        })
    return rows


def extract_total_pages(payload: Any, current_page: int, product_count: int) -> int | None:
    """Read pagination across known DigiKala response variants."""
    page_keys = (
        "total_pages", "totalPages", "page_count", "pageCount",
        "last_page", "lastPage", "pages_count",
    )
    for node in _walk_dicts(payload):
        for key in page_keys:
            value = _normal_int(node.get(key))
            if value > 0:
                return min(MAX_PAGES_PER_CATEGORY, value)
        total_items = _normal_int(
            node.get("total_items") or node.get("totalItems")
            or node.get("total_count") or node.get("totalCount")
        )
        page_size = _normal_int(
            node.get("page_size") or node.get("pageSize")
            or node.get("per_page") or node.get("perPage")
        )
        if total_items > 0 and page_size > 0:
            return min(MAX_PAGES_PER_CATEGORY, max(1, math.ceil(total_items / page_size)))
    if product_count == 0:
        return max(1, current_page)
    return None


def _candidate_demand(row: dict) -> int:
    explicit = max(0, _normal_int(row.get("demand_score")))
    if explicit:
        return min(200, explicit)
    reviews = max(0, _normal_int(row.get("review_count")))
    rating = _normal_float(row.get("rating"))
    review_proxy = min(30, round(3.5 * math.log1p(reviews))) if reviews else 0
    rating_proxy = max(0, min(10, round((rating - 3.0) * 5))) if rating else 0
    return review_proxy + rating_proxy


def catalog_candidate_sort_key(row: dict) -> tuple:
    """Keep market-demand signals primary and deal percentage immediately after."""
    return (
        _candidate_demand(row),
        max(0, _normal_int(row.get("review_count"))),
        round(_normal_float(row.get("rating")) * 10),
        max(0, _normal_int(row.get("discount_percent"))),
        max(0, _normal_int(row.get("savings_toman"))),
    )


def _category_page_url(category_id: str, page: int) -> tuple[str, dict]:
    return SEARCH_URL, {"categories[]": str(category_id), "page": int(page)}


def _publisher_seen_ids(publisher_state_path: Path) -> set[str]:
    state = _read_json(publisher_state_path, {})
    handoff = state.get("catalog_sweep_handoff", {}) if isinstance(state, dict) else {}
    seen = handoff.get("seen_ids", {}) if isinstance(handoff, dict) else {}
    return {str(pid) for pid in seen} if isinstance(seen, dict) else set()


def _clean_old_candidates(candidates: dict[str, dict], seen_ids: set[str], now: datetime) -> dict[str, dict]:
    cleaned = {}
    cutoff = now - timedelta(hours=CANDIDATE_TTL_HOURS)
    for pid, row in candidates.items():
        if pid in seen_ids or not isinstance(row, dict):
            continue
        last_seen = row.get("last_seen_at") or row.get("first_seen_at") or ""
        try:
            stamp = datetime.fromisoformat(str(last_seen).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if stamp < cutoff:
            continue
        if not re.fullmatch(r"dkp-\d{1,12}", str(pid)):
            continue
        cleaned[str(pid)] = row
    return cleaned


def load_catalog_candidates(path: Path = CANDIDATES_PATH) -> list[dict]:
    """Read current unacknowledged candidate cards for the publisher."""
    try:
        payload = _read_json(path, {})
    except CatalogSweepError:
        print("CATALOG_SWEEP_CANDIDATE_FILE_INVALID")
        return []
    rows = payload.get("candidates", []) if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def load_catalog_candidates_for_handoff(
    candidates_path: Path,
    publisher_state: dict,
    max_count: int = 40,
    now: datetime | None = None,
) -> list[dict]:
    """Return unseen cards and record acknowledgements in publisher state."""
    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    rows = load_catalog_candidates(candidates_path)
    handoff = publisher_state.setdefault("catalog_sweep_handoff", {})
    if not isinstance(handoff, dict):
        handoff = {}
        publisher_state["catalog_sweep_handoff"] = handoff
    seen = handoff.setdefault("seen_ids", {})
    if not isinstance(seen, dict):
        seen = {}
        handoff["seen_ids"] = seen

    cutoff = current - timedelta(days=PUBLISHER_SEEN_TTL_DAYS)
    for pid, stamp in list(seen.items()):
        try:
            parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            seen.pop(pid, None)
            continue
        if parsed < cutoff:
            seen.pop(pid, None)

    already_queued = publisher_state.get("discovery_queue", {})
    already_queued = set(already_queued) if isinstance(already_queued, dict) else set()
    fresh = []
    for row in rows:
        pid = str(row.get("product_id") or "")
        url = str(row.get("product_url") or "")
        if not re.fullmatch(r"dkp-\d{1,12}", pid):
            continue
        if pid in seen or pid in already_queued:
            continue
        if not url.endswith(f"/{pid}/") or not is_publishable_product_title(row.get("title", "")):
            continue
        fresh.append(row)
    fresh.sort(key=catalog_candidate_sort_key, reverse=True)
    selected = fresh[:max(0, int(max_count))]
    stamp = current.isoformat()
    for row in selected:
        seen[str(row["product_id"])] = stamp
    if len(seen) > MAX_PUBLISHER_SEEN_IDS:
        ordered = sorted(seen.items(), key=lambda pair: str(pair[1]), reverse=True)
        handoff["seen_ids"] = dict(ordered[:MAX_PUBLISHER_SEEN_IDS])
    handoff["last_handoff_at"] = stamp if selected else handoff.get("last_handoff_at", "")
    handoff["last_handoff_count"] = len(selected)
    return selected


def _load_candidates_by_id(path: Path) -> dict[str, dict]:
    payload = _read_json(path, {})
    rows = payload.get("candidates", []) if isinstance(payload, dict) else []
    result = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            pid = str(row.get("product_id") or "")
            if re.fullmatch(r"dkp-\d{1,12}", pid):
                result[pid] = row
    return result


def _advance_cursor(state: dict, category_count: int, total_pages: int | None, products_count: int) -> None:
    category_index = max(0, _normal_int(state.get("category_index")))
    page = max(1, _normal_int(state.get("page"), 1))
    effective_total = total_pages if total_pages is not None else (
        page if products_count == 0 else None
    )
    if effective_total is not None and page >= effective_total:
        category_index += 1
        page = 1
    else:
        page += 1

    if category_index >= category_count:
        state["category_index"] = 0
        state["page"] = 1
        state["completed_cycles"] = max(0, _normal_int(state.get("completed_cycles"))) + 1
        state["last_cycle_completed_at"] = iso_now()
        state["current_cycle_pages"] = 0
        state["current_cycle_product_rows"] = 0
        state["current_cycle_categories_completed"] = 0
        print("CATALOG_SWEEP_CYCLE_COMPLETED")
    else:
        state["category_index"] = category_index
        state["page"] = page


def refresh_categories(state: dict, session: requests.Session, force: bool = False) -> None:
    now = utc_now()
    current = state.get("categories")
    refreshed = state.get("categories_refreshed_at")
    stale = True
    if refreshed:
        try:
            stamp = datetime.fromisoformat(str(refreshed).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            stale = now - stamp >= timedelta(hours=CATEGORY_REFRESH_HOURS)
        except (TypeError, ValueError):
            stale = True
    if current and not force and not stale:
        return

    categories = discover_categories(session)
    if not categories:
        raise CatalogSweepError("category_tree_empty")
    previous_id = None
    old_categories = current if isinstance(current, list) else []
    old_index = max(0, _normal_int(state.get("category_index")))
    if old_index < len(old_categories) and isinstance(old_categories[old_index], dict):
        previous_id = str(old_categories[old_index].get("id") or "")

    state["categories"] = categories
    state["categories_refreshed_at"] = now.isoformat()
    ids = [str(row["id"]) for row in categories]
    state["category_count"] = len(categories)
    state["category_ids_hash"] = str(hash(tuple(ids)))
    if previous_id and previous_id in ids:
        state["category_index"] = ids.index(previous_id)
    else:
        state["category_index"] = 0
        state["page"] = 1
    state.setdefault("page", 1)
    print(f"CATALOG_CATEGORIES_REFRESHED count={len(categories)}")


def run_sweep(
    pages_per_run: int = 2,
    session: requests.Session | None = None,
    state_path: Path = SWEEP_STATE_PATH,
    candidates_path: Path = CANDIDATES_PATH,
    publisher_state_path: Path = PUBLISHER_STATE_PATH,
    force_refresh: bool = False,
) -> int:
    """Scan a small page batch, checkpoint every page, and retain deal candidates."""
    http = session or SESSION
    state = _read_json(state_path, {})
    if not isinstance(state, dict):
        state = {}
    if not isinstance(state.get("stats"), dict):
        state["stats"] = {}
    stats = state["stats"]
    for key in (
        "pages_scanned_total", "product_rows_scanned_total",
        "discounted_candidates_found_total", "api_failures_total",
        "completed_cycles",
    ):
        stats[key] = max(0, _normal_int(stats.get(key)))

    try:
        refresh_categories(state, http, force=force_refresh)
    except Exception as exc:
        state["last_error"] = f"category_refresh:{type(exc).__name__}:{str(exc)[:160]}"
        state["last_error_at"] = iso_now()
        _write_json(state_path, state)
        print(f"CATALOG_SWEEP_CATEGORY_REFRESH_FAILED error={type(exc).__name__} detail={str(exc)[:160]!r}")
        return 1

    categories = state.get("categories", [])
    if not isinstance(categories, list) or not categories:
        print("CATALOG_SWEEP_ABORTED reason=no_categories")
        return 1

    candidates = _load_candidates_by_id(candidates_path)
    now = utc_now()
    seen_ids = _publisher_seen_ids(publisher_state_path)
    candidates = _clean_old_candidates(candidates, seen_ids, now)

    pages_limit = max(1, min(20, int(pages_per_run)))
    completed_pages = 0
    while completed_pages < pages_limit:
        category_index = max(0, _normal_int(state.get("category_index")))
        if category_index >= len(categories):
            state["category_index"] = 0
            state["page"] = 1
            state["completed_cycles"] = max(0, _normal_int(state.get("completed_cycles"))) + 1
            stats["completed_cycles"] = state["completed_cycles"]
            state["last_cycle_completed_at"] = iso_now()
            continue

        category = categories[category_index]
        if not isinstance(category, dict):
            state["category_index"] = category_index + 1
            state["page"] = 1
            continue
        category_id = str(category.get("id") or "")
        category_name = str(category.get("name") or category_id)
        page = max(1, _normal_int(state.get("page"), 1))
        if not category_id.isdigit() or page > MAX_PAGES_PER_CATEGORY:
            state["category_index"] = category_index + 1
            state["page"] = 1
            _write_json(state_path, state)
            continue

        url, params = _category_page_url(category_id, page)
        try:
            payload = _request_json(http, url, params=params)
            product_rows = extract_product_rows(payload)
            total_pages = extract_total_pages(payload, page, len(product_rows))
        except Exception as exc:
            stats["api_failures_total"] += 1
            state["last_error"] = f"category={category_id}:page={page}:{type(exc).__name__}:{str(exc)[:120]}"
            state["last_error_at"] = iso_now()
            state["stats"] = stats
            _write_json(state_path, state)
            print(
                f"CATALOG_SWEEP_PAGE_FAILED category={category_id} page={page} "
                f"error={type(exc).__name__} detail={str(exc)[:160]!r}; cursor_retained=true"
            )
            return 1

        for row in product_rows:
            pid = row["product_id"]
            if row["discount_percent"] < MIN_CANDIDATE_DISCOUNT:
                continue
            old = candidates.get(pid, {})
            first_seen = old.get("first_seen_at") or iso_now()
            candidate = {**old, **row, "first_seen_at": first_seen}
            candidates[pid] = candidate
            stats["discounted_candidates_found_total"] += 1

        stats["pages_scanned_total"] += 1
        stats["product_rows_scanned_total"] += len(product_rows)
        state["current_cycle_pages"] = max(0, _normal_int(state.get("current_cycle_pages"))) + 1
        state["current_cycle_product_rows"] = (
            max(0, _normal_int(state.get("current_cycle_product_rows"))) + len(product_rows)
        )
        state["last_successful_page_at"] = iso_now()
        state["last_successful_category_id"] = category_id
        state["last_successful_category_name"] = category_name
        state["last_successful_page"] = page
        state["last_error"] = ""
        _advance_cursor(state, len(categories), total_pages, len(product_rows))
        stats["completed_cycles"] = max(0, _normal_int(state.get("completed_cycles")))
        state["stats"] = stats

        candidates = _clean_old_candidates(candidates, seen_ids, utc_now())
        ordered_candidates = sorted(
            candidates.values(), key=catalog_candidate_sort_key, reverse=True
        )[:MAX_RETAINED_CANDIDATES]
        _write_json(candidates_path, {
            "updated_at": iso_now(),
            "candidate_count": len(ordered_candidates),
            "candidates": ordered_candidates,
        })
        state["unacknowledged_candidate_count"] = len(ordered_candidates)
        _write_json(state_path, state)
        completed_pages += 1
        print(
            f"CATALOG_SWEEP_PAGE_OK category={category_id} name={category_name!r} "
            f"page={page} total_pages={total_pages if total_pages is not None else 'unknown'} "
            f"product_rows={len(product_rows)} discounted_candidates={sum(1 for r in product_rows if r['discount_percent'] >= MIN_CANDIDATE_DISCOUNT)} "
            f"candidate_backlog={len(ordered_candidates)}"
        )
        if completed_pages < pages_limit:
            time.sleep(0.75)

    print(
        "CATALOG_SWEEP_RUN_SUMMARY "
        f"pages_this_run={completed_pages} "
        f"pages_total={stats['pages_scanned_total']} "
        f"product_rows_total={stats['product_rows_scanned_total']} "
        f"categories={len(categories)} "
        f"cursor={state.get('category_index', 0)}:{state.get('page', 1)} "
        f"candidate_backlog={state.get('unacknowledged_candidate_count', 0)}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental DigiKala catalog page sweep")
    parser.add_argument("--pages-per-run", type=int, default=2)
    parser.add_argument("--refresh-categories", action="store_true")
    args = parser.parse_args()
    return run_sweep(
        pages_per_run=args.pages_per_run,
        force_refresh=args.refresh_categories,
    )


if __name__ == "__main__":
    sys.exit(main())
