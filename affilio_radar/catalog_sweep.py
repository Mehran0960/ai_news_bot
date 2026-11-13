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
    from .offerchin_four_factor import (
        apply_four_factor_scores as _apply_four_factor_scores,
        four_factor_sort_key as _four_factor_sort_key,
        infer_use_case_group as _infer_use_case_group,
    )
except ImportError:
    from offerchin_four_factor import (
        apply_four_factor_scores as _apply_four_factor_scores,
        four_factor_sort_key as _four_factor_sort_key,
        infer_use_case_group as _infer_use_case_group,
    )

try:
    from .product_quality import is_prohibited_product_title, is_publishable_product_title
except ImportError:
    try:
        from product_quality import is_prohibited_product_title, is_publishable_product_title
    except ImportError:  # pragma: no cover - fail closed if safety policy is unavailable
        def is_publishable_product_title(value: object) -> bool:
            text = re.sub(r"\s+", " ", str(value or "")).strip()
            return len(text) >= 5 and len(text.split()) >= 2

        def is_prohibited_product_title(value: object) -> bool:
            # Never make the catalog permissive when its safety policy is unavailable.
            return True


ROOT = Path(__file__).resolve().parent
SWEEP_STATE_PATH = ROOT / "catalog_sweep_state.json"
CANDIDATES_PATH = ROOT / "catalog_sweep_candidates.json"
PUBLISHER_STATE_PATH = ROOT / "state.json"

API_ROOT = "https://api.digikala.com"
DICTIONARY_URL = f"{API_ROOT}/v1/dictionaries/"
SEARCH_URL = f"{API_ROOT}/v1/search/"  # category discovery fallback only
CATEGORY_SEARCH_URL_TEMPLATE = f"{API_ROOT}/v2/category/{{category_id}}/"
REQUEST_TIMEOUT = (5, 18)
CATEGORY_REFRESH_HOURS = 24
# A previously verified taxonomy may bridge a temporary API outage, but only for four days.
CATEGORY_CACHE_MAX_FALLBACK_AGE_HOURS = 96
CATEGORY_DISCOVERY_RETRY_MINUTES = 60
CANDIDATE_TTL_HOURS = 72
MIN_CANDIDATE_DISCOUNT = 1
# Search API v2 category pages use sort=5 for Best Selling (verified against the
# live DigiKala API integration used by the current Digikala MCP client).
# This is only the upstream sort order; it does not cap page depth.
BEST_SELLING_SORT_VALUE = 5
BEST_SELLING_PAGE_SIZE = 20
BEST_SELLING_MAX_PAGES_PER_CATEGORY = 3
BEST_SELLING_MAX_AGE_HOURS = 24
MAX_RETAINED_CANDIDATES = 3000
MAX_PUBLISHER_SEEN_IDS = 12000
PUBLISHER_SEEN_TTL_DAYS = 2

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


def sort_categories_for_sweep(categories: Any) -> list[dict]:
    """Prioritize leaf categories, which contain product listings, before parent nodes."""
    rows = [row for row in (categories or []) if isinstance(row, dict)]
    parent_ids = {
        str(row.get("parent_id") or "").strip()
        for row in rows
        if str(row.get("parent_id") or "").strip().isdigit()
    }

    def priority(row: dict) -> tuple:
        category_id = str(row.get("id") or "")
        depth = max(0, _normal_int(row.get("depth")))
        is_parent = category_id in parent_ids
        return (
            1 if is_parent else 0,
            -depth,
            int(category_id) if category_id.isdigit() else 0,
            str(row.get("name") or ""),
        )

    return sorted(rows, key=priority)


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

    return sort_categories_for_sweep(found.values())


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


def _category_discovery_error_label(source: str, exc: Exception) -> str:
    """Preserve HTTP status in bounded diagnostics without logging response bodies."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError, OverflowError):
        status = None
    if status:
        return f"{source}_http_{status}"
    if isinstance(exc, requests.exceptions.Timeout):
        return f"{source}_timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return f"{source}_connection_error"
    return f"{source}_{type(exc).__name__}"


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
        errors.append(_category_discovery_error_label("dictionaries", exc))

    try:
        payload = _request_json(http, SEARCH_URL, params={"page": 1})
        categories = extract_categories(payload)
        if categories:
            return categories
        errors.append("search_filters_no_category_nodes")
    except Exception as exc:
        errors.append(_category_discovery_error_label("search", exc))

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


def _listing_availability(product: dict) -> str:
    """Return a stock state only when DigiKala exposes an explicit availability field."""
    in_stock_words = {
        "in_stock", "instock", "available", "available_now", "in stock",
        "موجود", "موجود است", "موجود در انبار",
    }
    out_of_stock_words = {
        "out_of_stock", "out of stock", "outofstock", "unavailable", "sold_out",
        "ناموجود", "اتمام موجودی", "ناموجود است",
    }
    for source in _price_source_rows(product):
        for key in ("is_in_stock", "in_stock", "is_available", "available", "can_buy"):
            value = source.get(key)
            if isinstance(value, bool):
                return "in_stock" if value else "out_of_stock"
            if isinstance(value, (int, float)) and value in (0, 1):
                return "in_stock" if bool(value) else "out_of_stock"
        for key in ("availability", "stock_status", "availability_status"):
            value = source.get(key)
            if isinstance(value, dict):
                value = value.get("title") or value.get("status") or value.get("label")
            if isinstance(value, str):
                normalized = re.sub(r"\s+", "_", value.strip().lower().replace("-", "_"))
                if normalized in in_stock_words:
                    return "in_stock"
                if normalized in out_of_stock_words:
                    return "out_of_stock"
        for key in ("stock_quantity", "available_quantity", "stock_count", "stock"):
            value = source.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return "in_stock" if value > 0 else "out_of_stock"
    return "unknown"


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


def _extract_product_nodes(payload: Any) -> list[dict]:
    """Support both legacy V1 products and current V2 category-page widgets."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise CatalogSweepError("search_payload_missing_data_object")

    if "products" in data:
        products = data.get("products")
        if not isinstance(products, list):
            raise CatalogSweepError("search_payload_products_not_list")
        return [row for row in products if isinstance(row, dict)]

    widgets = data.get("widgets")
    if not isinstance(widgets, list):
        raise CatalogSweepError("search_payload_missing_products_or_widgets")

    products: list[dict] = []
    listing_seen = False
    for widget in widgets:
        if not isinstance(widget, dict) or widget.get("type") != "vertical_product_listing":
            continue
        listing_seen = True
        nested = widget.get("data")
        nested_widgets = nested.get("widgets") if isinstance(nested, dict) else None
        if not isinstance(nested_widgets, list):
            raise CatalogSweepError("v2_vertical_product_listing_missing_widgets")
        for product_widget in nested_widgets:
            if not isinstance(product_widget, dict) or product_widget.get("type") != "product":
                continue
            product_data = product_widget.get("data")
            if isinstance(product_data, dict):
                # A V2 product card is marketable only when Digikala explicitly
                # marks it as such; live product detail remains the final gate.
                if product_data.get("status") == "marketable":
                    products.append(product_data)
    if not listing_seen:
        raise CatalogSweepError("v2_category_payload_missing_vertical_product_listing")
    return products


def extract_product_rows(payload: Any) -> list[dict]:
    """Return compact listing cards from both legacy V1 and current V2 responses."""
    products = _extract_product_nodes(payload)
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
        # Retain every identified product. The publisher fetches the canonical
        # detail page and applies strict title/price/stock/discount checks later.
        if not is_publishable_product_title(title):
            title = f"محصول دیجی‌کالا {product_id}"
        current, original, discount, savings = _listing_prices(product)
        availability = _listing_availability(product)
        if availability == "unknown" and product.get("status") == "marketable":
            availability = "marketable_unverified_stock"
        rating, review_count = _listing_rating(product)
        rows.append({
            "product_id": product_id,
            "product_url": f"https://www.digikala.com/product/{product_id}/",
            "title": title,
            "current_price": current,
            "original_price": original,
            "discount_percent": discount,
            "savings_toman": savings,
            "availability": availability,
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
                return value
        total_items = _normal_int(
            node.get("total_items") or node.get("totalItems")
            or node.get("total_count") or node.get("totalCount")
        )
        page_size = _normal_int(
            node.get("page_size") or node.get("pageSize")
            or node.get("per_page") or node.get("perPage")
        )
        if total_items > 0 and page_size > 0:
            return max(1, math.ceil(total_items / page_size))
    if product_count == 0:
        return max(1, current_page)
    return None


def _fresh_best_selling_rank(row: dict, now: datetime | None = None) -> int | None:
    if not isinstance(row, dict) or row.get("catalog_sort_mode") != "best_selling":
        return None
    rank = _normal_int(row.get("catalog_best_selling_rank"))
    if not 1 <= rank <= BEST_SELLING_PAGE_SIZE * BEST_SELLING_MAX_PAGES_PER_CATEGORY:
        return None
    raw = str(row.get("catalog_rank_observed_at") or "").strip()
    try:
        observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        observed = observed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None
    current = now or utc_now()
    age = (current.astimezone(timezone.utc) - observed).total_seconds() / 3600
    return rank if 0 <= age <= BEST_SELLING_MAX_AGE_HOURS else None


def _candidate_demand(row: dict) -> int:
    """Build a conservative DigiKala-first demand key; never accept a synthetic demand_score."""
    rank = _fresh_best_selling_rank(row)
    if rank is not None:
        tier = 3 if rank <= 10 else 2 if rank <= 30 else 1
        category_rows = row.get("catalog_best_selling_ranks_by_category")
        category_count = 0
        momentum = 0
        if isinstance(category_rows, dict):
            for category_id, entry in category_rows.items():
                if not str(category_id).isdigit() or not isinstance(entry, dict):
                    continue
                observed = str(entry.get("observed_at") or "")
                try:
                    parsed = datetime.fromisoformat(observed.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    age_hours = (utc_now() - parsed.astimezone(timezone.utc)).total_seconds() / 3600
                    saved_rank = _normal_int(entry.get("rank"))
                except (TypeError, ValueError, OverflowError):
                    continue
                if 0 <= age_hours <= BEST_SELLING_MAX_AGE_HOURS and 1 <= saved_rank <= BEST_SELLING_PAGE_SIZE * BEST_SELLING_MAX_PAGES_PER_CATEGORY:
                    category_count += 1
                    history = entry.get("rank_history")
                    if isinstance(history, list):
                        prior = []
                        for sample in history:
                            if not isinstance(sample, dict):
                                continue
                            try:
                                prior_rank = _normal_int(sample.get("rank"))
                                prior_at = datetime.fromisoformat(
                                    str(sample.get("observed_at") or "").replace("Z", "+00:00")
                                )
                                if prior_at.tzinfo is None:
                                    prior_at = prior_at.replace(tzinfo=timezone.utc)
                                elapsed = (parsed.astimezone(timezone.utc) - prior_at.astimezone(timezone.utc)).total_seconds() / 3600
                                if 6 <= elapsed <= 24 * 7 and 1 <= prior_rank <= BEST_SELLING_PAGE_SIZE * BEST_SELLING_MAX_PAGES_PER_CATEGORY:
                                    prior.append((prior_at, prior_rank))
                            except (TypeError, ValueError, OverflowError):
                                continue
                        if prior:
                            _prior_at, prior_rank = max(prior, key=lambda item: item[0])
                            momentum = max(momentum, prior_rank - saved_rank)
        # Native bestseller rank is stronger than lifetime review volume or a markdown.
        return 10_000 + tier * 1_000 + (BEST_SELLING_PAGE_SIZE * BEST_SELLING_MAX_PAGES_PER_CATEGORY + 1 - rank) * 10 + min(10, category_count) * 5 + max(-60, min(60, momentum))

    # Fallback only: review volume and rating are historical quality context, not sales.
    reviews = max(0, _normal_int(row.get("review_count")))
    rating = _normal_float(row.get("rating"))
    review_proxy = min(30, round(3.5 * math.log1p(reviews))) if reviews else 0
    rating_proxy = max(0, min(10, round((rating - 3.0) * 5))) if rating else 0
    return review_proxy + rating_proxy


def _catalog_live_demand_score(row: dict) -> float:
    """Only fresh native bestseller rank counts as live demand in the raw listing stage."""
    rank = _fresh_best_selling_rank(row)
    if rank is None:
        return 0.0
    observed_raw = str(row.get("catalog_rank_observed_at") or "")
    try:
        observed = datetime.fromisoformat(observed_raw.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (utc_now() - observed.astimezone(timezone.utc)).total_seconds() / 3600)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    base_score = 100.0 if rank <= 10 else 85.0 if rank <= 30 else 70.0
    category_rows = row.get("catalog_best_selling_ranks_by_category")
    fresh_categories = 0
    if isinstance(category_rows, dict):
        for entry in category_rows.values():
            if not isinstance(entry, dict):
                continue
            try:
                stamp = datetime.fromisoformat(str(entry.get("observed_at") or "").replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                rank_value = _normal_int(entry.get("rank"))
                age = (utc_now() - stamp.astimezone(timezone.utc)).total_seconds() / 3600
                if 1 <= rank_value <= BEST_SELLING_PAGE_SIZE * BEST_SELLING_MAX_PAGES_PER_CATEGORY and 0 <= age <= BEST_SELLING_MAX_AGE_HOURS:
                    fresh_categories += 1
            except (TypeError, ValueError, OverflowError):
                continue
    coverage_bonus = min(8.0, 2.0 * max(0, fresh_categories - 1))
    freshness = max(0.78, 1.0 - 0.22 * age_hours / BEST_SELLING_MAX_AGE_HOURS)
    return round(min(100.0, (base_score + coverage_bonus) * freshness), 2)


def _score_catalog_candidate_cohort(rows: list[dict]) -> None:
    _apply_four_factor_scores(
        rows,
        live_demand_score_fn=_catalog_live_demand_score,
        use_case_group_fn=lambda row: _infer_use_case_group(
            row.get("title"), row.get("catalog_category_name") or row.get("catalog_category_path")
        ),
        # Compare prices within the same taxonomy node, not across unrelated use cases.
        price_group_fn=lambda row: str(
            row.get("catalog_category_id") or row.get("catalog_best_selling_category_id")
            or _infer_use_case_group(row.get("title"), row.get("catalog_category_name"))
        ),
        # The listing stage has not independently verified price history or market median.
        discount_verified_fn=lambda _row: False,
        now=utc_now(),
    )


def catalog_candidate_sort_key(row: dict) -> tuple:
    """Use balanced four-factor priority; retain demand/value order for incomplete cards."""
    if not isinstance(row.get("offerchin_four_factor"), dict):
        _score_catalog_candidate_cohort([row])
    rank = _fresh_best_selling_rank(row)
    rank_strength = (
        BEST_SELLING_PAGE_SIZE * BEST_SELLING_MAX_PAGES_PER_CATEGORY + 1 - rank
        if rank is not None else 0
    )
    return (
        *_four_factor_sort_key(row),
        _candidate_demand(row),
        rank_strength,
        max(0, _normal_int(row.get("discount_percent"))),
        max(0, _normal_int(row.get("savings_toman"))),
    )


def retain_diverse_candidates(
    rows: list[dict],
    limit: int = MAX_RETAINED_CANDIDATES,
    rotation: int = 0,
) -> list[dict]:
    """Retain the global demand-first shortlist; do not impose category quotas or promote markdowns."""
    cap = max(0, int(limit))
    # The rolling candidate shortlist exists to find publishable offers, not to keep
    # undiscounted bestsellers that can never pass the last-mile publication gate.
    eligible = [
        row for row in rows or []
        if isinstance(row, dict)
        and row.get("product_id")
        and _normal_int(row.get("discount_percent")) >= MIN_CANDIDATE_DISCOUNT
        and _normal_int(row.get("savings_toman")) > 0
        and not is_prohibited_product_title(row.get("title"))
    ]
    _score_catalog_candidate_cohort(eligible)
    ranked = sorted(eligible, key=catalog_candidate_sort_key, reverse=True)
    return ranked[:cap]

def _category_page_url(category_id: str, page: int) -> tuple[str, dict]:
    """Build the live Search API V2 category route for full category pagination."""
    return CATEGORY_SEARCH_URL_TEMPLATE.format(
        category_id=str(category_id)
    ), {
        "page": max(1, int(page)),
        "sort": BEST_SELLING_SORT_VALUE,
    }


def _publisher_seen_records(publisher_state_path: Path) -> dict[str, object]:
    """Read durable handoff fingerprints, retaining legacy timestamp-only records."""
    state = _read_json(publisher_state_path, {})
    handoff = state.get("catalog_sweep_handoff", {}) if isinstance(state, dict) else {}
    seen = handoff.get("seen_ids", {}) if isinstance(handoff, dict) else {}
    return {str(pid): record for pid, record in seen.items()} if isinstance(seen, dict) else {}


def _publisher_seen_ids(publisher_state_path: Path) -> set[str]:
    """Compatibility helper for callers that only need the acknowledged IDs."""
    return set(_publisher_seen_records(publisher_state_path))


def _clean_old_candidates(
    candidates: dict[str, dict],
    seen_ids: set[str],
    now: datetime,
    *,
    seen_records: dict[str, object] | None = None,
) -> dict[str, dict]:
    """Keep changed handoff cards eligible; discard only unchanged acknowledged cards.

    A price/discount/stock fingerprint change must survive catalog cleanup so
    the publisher can perform its deep live check immediately. Legacy
    timestamp-only acknowledgements have no fingerprint baseline and are
    allowed through once to establish one.
    """
    cleaned = {}
    cutoff = now - timedelta(hours=CANDIDATE_TTL_HOURS)
    for pid, row in candidates.items():
        if not isinstance(row, dict):
            continue
        if pid in seen_ids:
            record = (seen_records or {}).get(str(pid))
            previous_fingerprint = (
                str(record.get("fingerprint") or "")
                if isinstance(record, dict) else ""
            )
            # Preserve old conservative behavior for callers without records.
            # In production, a missing legacy fingerprint is allowed through once.
            if seen_records is None or str(pid) not in seen_records:
                continue
            if previous_fingerprint and previous_fingerprint == catalog_handoff_fingerprint(row):
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


def _catalog_handoff_seen_at(value: object) -> str:
    """Read timestamps from both legacy string entries and current records."""
    if isinstance(value, dict):
        return str(value.get("seen_at") or "")
    return str(value or "")


def _catalog_handoff_deferred_at(value: object) -> str:
    """Read retry timestamps from legacy strings and fingerprint-aware records."""
    if isinstance(value, dict):
        return str(value.get("retry_after") or "")
    return str(value or "")


def catalog_handoff_fingerprint(row: dict) -> str:
    """Fingerprint listing price/discount/stock fields to detect material card changes."""
    row = row if isinstance(row, dict) else {}
    fields = (
        "current_price", "selling_price", "selling_price_toman",
        "original_price", "rrp_price", "rrp_price_toman",
        "discount_percent", "availability", "in_stock", "is_in_stock",
        "stock", "stock_status", "stock_quantity", "available_quantity",
        "stock_count", "is_available", "catalog_cycle_completed_at",
    )
    payload = {}
    for field in fields:
        value = row.get(field)
        if value is None or isinstance(value, (str, int, float, bool)):
            payload[field] = value
        else:
            payload[field] = str(value)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_catalog_candidates_for_handoff(
    candidates_path: Path,
    publisher_state: dict,
    max_count: int = 100,
    now: datetime | None = None,
) -> list[dict]:
    """Select new, changed, safe cards and persist explicit rejection diagnostics."""
    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    rows = load_catalog_candidates(candidates_path)
    handoff = publisher_state.setdefault("catalog_sweep_handoff", {})
    if not isinstance(handoff, dict):
        handoff = {}
        publisher_state["catalog_sweep_handoff"] = handoff

    diagnostics = {
        "rows_seen": len(rows),
        "invalid_product_id": 0,
        "invalid_product_url": 0,
        "title_fallback_used": 0,
        "prohibited_health_title": 0,
        "unchanged_recently_seen": 0,
        "deferred_unchanged": 0,
        "fresh_eligible": 0,
        "selected": 0,
    }

    seen = handoff.setdefault("seen_ids", {})
    if not isinstance(seen, dict):
        seen = {}
        handoff["seen_ids"] = seen
    cutoff = current - timedelta(days=PUBLISHER_SEEN_TTL_DAYS)
    for pid, record in list(seen.items()):
        try:
            parsed = datetime.fromisoformat(_catalog_handoff_seen_at(record).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            seen.pop(pid, None)
            continue
        if parsed < cutoff:
            seen.pop(pid, None)

    deferred = handoff.setdefault("deferred_ids", {})
    if not isinstance(deferred, dict):
        deferred = {}
        handoff["deferred_ids"] = deferred
    for pid, raw_retry in list(deferred.items()):
        try:
            retry_after = datetime.fromisoformat(
                _catalog_handoff_deferred_at(raw_retry).replace("Z", "+00:00")
            )
            if retry_after.tzinfo is None:
                retry_after = retry_after.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            deferred.pop(pid, None)
            continue
        if retry_after <= current:
            deferred.pop(pid, None)

    fresh = []
    for row in rows:
        pid = str(row.get("product_id") or "")
        url = str(row.get("product_url") or "")
        if not re.fullmatch(r"dkp-\d{1,12}", pid):
            diagnostics["invalid_product_id"] += 1
            continue
        if not url.endswith(f"/{pid}/"):
            diagnostics["invalid_product_url"] += 1
            continue

        # Weak listing titles are replaced by a synthetic label; final publication
        # still fetches the canonical product page and validates the real title.
        if not is_publishable_product_title(row.get("title", "")):
            row = {**row, "title": f"محصول دیجی‌کالا {pid}"}
            diagnostics["title_fallback_used"] += 1
        # Apply the same hard exclusion as the final publisher before finite
        # shortlist capacity is consumed by cards that cannot be published.
        if is_prohibited_product_title(row.get("title", "")):
            diagnostics["prohibited_health_title"] += 1
            continue

        fingerprint = catalog_handoff_fingerprint(row)
        previous = seen.get(pid)
        previous_fingerprint = (
            str(previous.get("fingerprint") or "") if isinstance(previous, dict) else ""
        )
        # Legacy timestamp-only records have no baseline; pass them once so the
        # next acknowledgement establishes a complete fingerprint.
        unchanged_recently_seen = bool(
            previous_fingerprint and previous_fingerprint == fingerprint
        )
        deferred_record = deferred.get(pid)
        deferred_fingerprint = (
            str(deferred_record.get("fingerprint") or "")
            if isinstance(deferred_record, dict) else ""
        )
        deferred_retry_at = _catalog_handoff_deferred_at(deferred_record)
        try:
            deferred_retry = datetime.fromisoformat(deferred_retry_at.replace("Z", "+00:00"))
            if deferred_retry.tzinfo is None:
                deferred_retry = deferred_retry.replace(tzinfo=timezone.utc)
            deferred_active = deferred_retry > current
        except (TypeError, ValueError):
            deferred_active = False
        changed_since_deferred = bool(
            deferred_fingerprint and deferred_fingerprint != fingerprint
        )
        # Existing discovery-queue entries are refreshed when a listing changes;
        # deferral suppresses only the same unchanged card.
        if unchanged_recently_seen:
            diagnostics["unchanged_recently_seen"] += 1
            continue
        if deferred_active and not changed_since_deferred:
            diagnostics["deferred_unchanged"] += 1
            continue
        fresh.append(row)

    diagnostics["fresh_eligible"] = len(fresh)
    selected = retain_diverse_candidates(
        fresh,
        limit=max(0, int(max_count)),
        rotation=int(current.timestamp() // 300),
    )
    diagnostics["selected"] = len(selected)
    handoff["last_selection_diagnostics"] = diagnostics
    handoff["last_selection_at"] = current.isoformat() if selected else handoff.get("last_selection_at", "")
    handoff["last_selection_count"] = len(selected)
    return selected


def acknowledge_catalog_candidates_handoff(
    publisher_state: dict,
    product_ids: list[str] | set[str],
    now: datetime | None = None,
    candidates: list[dict] | None = None,
) -> int:
    """Acknowledge retained IDs with their observed price/stock fingerprints."""
    if not isinstance(publisher_state, dict):
        return 0
    handoff = publisher_state.setdefault("catalog_sweep_handoff", {})
    if not isinstance(handoff, dict):
        handoff = {}
        publisher_state["catalog_sweep_handoff"] = handoff
    seen = handoff.setdefault("seen_ids", {})
    if not isinstance(seen, dict):
        seen = {}
        handoff["seen_ids"] = seen
    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    stamp = current.astimezone(timezone.utc).isoformat()
    candidate_map = {
        str(row.get("product_id") or ""): row
        for row in (candidates or []) if isinstance(row, dict)
    }
    acknowledged = {
        str(pid) for pid in (product_ids or [])
        if re.fullmatch(r"dkp-\d{1,12}", str(pid))
    }
    for pid in acknowledged:
        candidate = candidate_map.get(pid)
        seen[pid] = {
            "seen_at": stamp,
            "fingerprint": catalog_handoff_fingerprint(candidate) if candidate else "",
        }
    deferred = handoff.setdefault("deferred_ids", {})
    if isinstance(deferred, dict):
        for pid in acknowledged:
            deferred.pop(pid, None)
    if len(seen) > MAX_PUBLISHER_SEEN_IDS:
        ordered = sorted(
            seen.items(),
            key=lambda pair: _catalog_handoff_seen_at(pair[1]),
            reverse=True,
        )
        handoff["seen_ids"] = dict(ordered[:MAX_PUBLISHER_SEEN_IDS])
    if acknowledged:
        handoff["last_handoff_at"] = stamp
        handoff["last_handoff_count"] = len(acknowledged)
    return len(acknowledged)


def defer_catalog_candidates_handoff(
    publisher_state: dict,
    product_ids: list[str] | set[str],
    now: datetime | None = None,
    retry_minutes: int = 15,
    candidates: list[dict] | None = None,
) -> int:
    """Temporarily rotate queue-overflow candidates without acknowledging or dropping them."""
    if not isinstance(publisher_state, dict):
        return 0
    handoff = publisher_state.setdefault("catalog_sweep_handoff", {})
    if not isinstance(handoff, dict):
        handoff = {}
        publisher_state["catalog_sweep_handoff"] = handoff
    deferred = handoff.setdefault("deferred_ids", {})
    if not isinstance(deferred, dict):
        deferred = {}
        handoff["deferred_ids"] = deferred
    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    try:
        delay = max(1, min(240, int(retry_minutes)))
    except (TypeError, ValueError, OverflowError):
        delay = 15
    retry_at = (current + timedelta(minutes=delay)).isoformat()
    ids = {str(pid) for pid in (product_ids or []) if re.fullmatch(r"dkp-\d{1,12}", str(pid))}
    candidate_map = {
        str(row.get("product_id") or ""): row
        for row in (candidates or []) if isinstance(row, dict)
    }
    for pid in ids:
        candidate = candidate_map.get(pid)
        deferred[pid] = {
            "retry_after": retry_at,
            "fingerprint": catalog_handoff_fingerprint(candidate) if candidate else "",
        }
    if len(deferred) > MAX_PUBLISHER_SEEN_IDS:
        ordered = sorted(deferred.items(), key=lambda pair: str(pair[1]), reverse=True)
        handoff["deferred_ids"] = dict(ordered[:MAX_PUBLISHER_SEEN_IDS])
    return len(ids)


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
    # An empty product page closes this category even if stale pagination
    # metadata reports a larger total; never spend the cursor on empty pages.
    effective_total = page if products_count == 0 else total_pages
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


def _category_cache_age_hours(refreshed_at: Any, now: datetime) -> float | None:
    if not refreshed_at:
        return None
    try:
        stamp = datetime.fromisoformat(str(refreshed_at).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return max(0.0, (now - stamp.astimezone(timezone.utc)).total_seconds() / 3600)
    except (TypeError, ValueError, OverflowError):
        return None


def _category_cache_is_usable(categories: Any, age_hours: float | None) -> bool:
    return bool(
        isinstance(categories, list)
        and categories
        and all(
            isinstance(row, dict) and str(row.get("id") or "").isdigit()
            for row in categories
        )
        and age_hours is not None
        and age_hours <= CATEGORY_CACHE_MAX_FALLBACK_AGE_HOURS
    )


def _category_discovery_retry_minutes(error: Exception) -> int:
    detail = str(error or "").lower()
    if "_http_403" in detail or "_http_401" in detail:
        return 360
    if "_http_429" in detail:
        return 60
    if "_http_5" in detail or "timeout" in detail or "connection_error" in detail:
        return 20
    return CATEGORY_DISCOVERY_RETRY_MINUTES


def refresh_categories(state: dict, session: requests.Session, force: bool = False) -> None:
    now = utc_now()
    current = state.get("categories")
    refreshed = state.get("categories_refreshed_at")
    age_hours = _category_cache_age_hours(refreshed, now)
    stale = age_hours is None or age_hours >= CATEGORY_REFRESH_HOURS
    if current and not force and not stale:
        return

    retry_after = None
    try:
        retry_after_raw = state.get("category_discovery_retry_after")
        if retry_after_raw:
            retry_after = datetime.fromisoformat(str(retry_after_raw).replace("Z", "+00:00"))
            if retry_after.tzinfo is None:
                retry_after = retry_after.replace(tzinfo=timezone.utc)
            retry_after = retry_after.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        retry_after = None

    cache_usable = _category_cache_is_usable(current, age_hours)
    if (
        cache_usable and not force and retry_after is not None and retry_after > now
    ):
        print(
            "CATALOG_CATEGORY_DISCOVERY_BACKOFF "
            f"retry_after={retry_after.isoformat()} cached_categories={len(current)} "
            f"cache_age_hours={age_hours:.1f} continuing_with_last_verified_taxonomy=true"
        )
        return

    try:
        categories = discover_categories(session)
        if not categories:
            raise CatalogSweepError("category_tree_empty")
    except Exception as exc:
        if cache_usable:
            retry_minutes = _category_discovery_retry_minutes(exc)
            retry_at = now + timedelta(minutes=retry_minutes)
            state["category_discovery_last_failed_at"] = now.isoformat()
            state["category_discovery_last_error"] = str(exc)[:220]
            state["category_discovery_retry_after"] = retry_at.isoformat()
            state["category_discovery_fallback_used"] = True
            print(
                "CATALOG_CATEGORY_DISCOVERY_FALLBACK "
                f"reason={str(exc)[:180]!r} cached_categories={len(current)} "
                f"cache_age_hours={age_hours:.1f} retry_minutes={retry_minutes} "
                "continuing_with_last_verified_taxonomy=true"
            )
            return
        raise

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
    state.pop("category_discovery_last_failed_at", None)
    state.pop("category_discovery_last_error", None)
    state.pop("category_discovery_retry_after", None)
    state["category_discovery_fallback_used"] = False
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
    """Scan a bounded page batch, checkpoint every page, and follow pagination without a depth cap."""
    http = session or SESSION
    state = _read_json(state_path, {})
    if not isinstance(state, dict):
        state = {}
    if not isinstance(state.get("stats"), dict):
        state["stats"] = {}
    stats = state["stats"]
    for key in (
        "pages_scanned_total", "product_rows_scanned_total",
        "discounted_candidates_found_total", "catalog_candidate_cards_found_total",
        "api_failures_total", "completed_cycles",
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
    seen_records = _publisher_seen_records(publisher_state_path)
    seen_ids = set(seen_records)
    candidates = _clean_old_candidates(
        candidates, seen_ids, now, seen_records=seen_records
    )

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
        if not category_id.isdigit():
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

        discounted_on_page = 0
        page_observed_at = iso_now()
        page_start_rank = (page - 1) * BEST_SELLING_PAGE_SIZE
        for row_index, row in enumerate(product_rows):
            pid = row["product_id"]
            # Every product card is handed to the bounded publisher detail queue.
            # A missing/zero list-card discount is not evidence of no live discount.
            old = candidates.get(pid, {})
            first_seen = old.get("first_seen_at") or page_observed_at
            previous_categories = old.get("catalog_category_ids", [])
            category_ids = {str(v) for v in previous_categories if str(v).isdigit()} if isinstance(previous_categories, list) else set()
            category_ids.add(category_id)

            # Preserve per-category ranks, then keep the strongest rank seen for this
            # product. This records the source category so the publisher can diagnose it.
            ranks_by_category = old.get("catalog_best_selling_ranks_by_category", {})
            ranks_by_category = dict(ranks_by_category) if isinstance(ranks_by_category, dict) else {}
            category_rank = page_start_rank + row_index + 1
            ranks_by_category[category_id] = {
                "rank": category_rank,
                "observed_at": page_observed_at,
                "category_name": category_name,
            }
            valid_ranks = []
            for rank_category_id, rank_record in ranks_by_category.items():
                if not str(rank_category_id).isdigit() or not isinstance(rank_record, dict):
                    continue
                saved_rank = _normal_int(rank_record.get("rank"))
                if not 1 <= saved_rank <= BEST_SELLING_PAGE_SIZE * BEST_SELLING_MAX_PAGES_PER_CATEGORY:
                    continue
                try:
                    rank_observed = datetime.fromisoformat(
                        str(rank_record.get("observed_at") or "").replace("Z", "+00:00")
                    )
                    if rank_observed.tzinfo is None:
                        rank_observed = rank_observed.replace(tzinfo=timezone.utc)
                    rank_age_hours = (
                        now.astimezone(timezone.utc) - rank_observed.astimezone(timezone.utc)
                    ).total_seconds() / 3600
                except (TypeError, ValueError, OverflowError):
                    continue
                if 0 <= rank_age_hours <= BEST_SELLING_MAX_AGE_HOURS:
                    valid_ranks.append((saved_rank, str(rank_category_id), rank_record))
            best_rank, best_category_id, best_rank_record = (
                min(valid_ranks, key=lambda item: item[0]) if valid_ranks
                else (category_rank, category_id, {
                    "observed_at": page_observed_at,
                    "category_name": category_name,
                })
            )
            candidate = {
                **old, **row,
                "first_seen_at": first_seen,
                "catalog_category_id": category_id,
                "catalog_category_name": category_name,
                "catalog_category_ids": sorted(category_ids, key=lambda value: int(value)),
                "catalog_sort_mode": "best_selling",
                "catalog_best_selling_ranks_by_category": ranks_by_category,
                "catalog_best_selling_rank": best_rank,
                "catalog_best_selling_category_id": best_category_id,
                "catalog_best_selling_category_name": str(best_rank_record.get("category_name") or category_name),
                "catalog_rank_observed_at": str(best_rank_record.get("observed_at") or page_observed_at),
            }
            candidates[pid] = candidate
            stats["catalog_candidate_cards_found_total"] += 1
            if row["discount_percent"] >= MIN_CANDIDATE_DISCOUNT:
                discounted_on_page += 1
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

        candidates = _clean_old_candidates(
            candidates, seen_ids, utc_now(), seen_records=seen_records
        )
        ordered_candidates = retain_diverse_candidates(
            list(candidates.values()), limit=MAX_RETAINED_CANDIDATES,
            rotation=stats["pages_scanned_total"],
        )
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
            f"product_rows={len(product_rows)} catalog_cards_queued={len(product_rows)} "
            f"listed_discounted={discounted_on_page} sort=best_selling "
            f"rank_range={page_start_rank + 1}-{page_start_rank + len(product_rows)} "
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
