"""Platform delivery worker for the OfferChin selected-content queue.

Discovery and ranking happen in affilio_radar.py. This module only consumes the
persisted hand-off contract, revalidates price/stock, and invokes destination
adapters independently. A platform failure never blocks another adapter.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import affilio_radar as radar
from content_delivery import (
    _active_publication, due_content, enforce_queue_limit, finish_queue_item,
    promote_fallback_selection,
)
from platform_registry import (
    CORE_PHOTO_PLATFORMS, PLATFORM_NAMES, PHOTO_PLATFORMS,
    VIDEO_PLATFORMS, validate_registry,
)
from integrity_audit_state import apply_integrity_audit_ledger


RETRY_BASE_SECONDS = max(60, int(os.getenv("AFFILIO_PUBLISH_RETRY_BASE_SECONDS", "300")))
MAX_ITEMS_PER_RUN = max(1, min(3, int(os.getenv("AFFILIO_PUBLISHER_BATCH_SIZE", "1"))))
MAX_INLINE_FALLBACK_ATTEMPTS = 50
TERMINAL_PLATFORM = {"sent", "not_connected", "manual_review"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _save(state: dict) -> None:
    radar.save_json(radar.STATE, state)


def _utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _safe_delivery_error(exc: Exception) -> str:
    """Keep actionable delivery diagnostics while redacting URLs and credentials."""
    detail = " ".join(str(exc or "").split())
    detail = re.sub(r"https?://\S+", "[redacted-url]", detail)
    detail = re.sub(r"(?i)\b(token|secret|authorization)\b\s*[:=]\s*\S+", r"\1=[redacted]", detail)
    detail = re.sub(r"\b[A-Za-z0-9_-]{28,}\b", "[redacted-id]", detail)
    return detail[:150] or type(exc).__name__


def _has_successful_destination(entry: dict) -> bool:
    """Allow an already-started multi-platform delivery to finish after evidence ages out."""
    platforms = entry.get("platforms")
    if not isinstance(platforms, dict):
        return False
    return any(
        isinstance(target, dict)
        and str(target.get("status") or "").lower() in {"sent", "success", "published"}
        for target in platforms.values()
    )


def _eligible_fallback_candidates(candidates: Any, now: datetime, catalog_context: dict | None = None) -> list[dict]:
    """Keep backups with a genuine current markdown; ranked backups share the primary policy."""
    if not isinstance(candidates, list):
        return []
    eligible: list[dict] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if catalog_context is not None and not radar.catalog_candidate_is_publishable(candidate, catalog_context):
            continue
        if not radar.has_verified_market_demand(candidate, now=now):
            continue
        raw_floor = candidate.get("selection_discount_floor")
        if raw_floor is None:
            selected_floor = radar.DISCOUNT_FALLBACK_FLOORS[0]
        else:
            try:
                selected_floor = int(raw_floor)
            except (TypeError, ValueError, OverflowError):
                continue
        selected_floor = radar.MIN_DISCOUNT_FALLBACK_PERCENT
        candidate = dict(candidate)
        candidate["selection_discount_floor"] = selected_floor
        candidate["selection_discount_band"] = "1%+"
        # Demand evidence is a hard gate; a markdown alone is never enough.
        # Fresh verified contradictory price evidence is checked independently.
        if radar.is_discount_publish_eligible(
            candidate, minimum_discount_percent=selected_floor, now=now
        ):
            eligible.append(candidate)
    return eligible



def _duplicate_guard_reason(existing: Any, delivery_id: str) -> str:
    """Prevent a new queue generation from reposting an already-active product."""
    if not isinstance(existing, dict) or not _active_publication(existing):
        return ""
    previous_delivery = str(existing.get("distribution_queue_id") or "")
    if previous_delivery and previous_delivery == str(delivery_id or ""):
        # This is a retry of the same hand-off, not a duplicate new selection.
        return ""
    return "active_publication_exists"


def _target(entry: dict, name: str) -> dict:
    platforms = entry.setdefault("platforms", {})
    value = platforms.get(name)
    if not isinstance(value, dict):
        value = {"status": "pending", "attempts": 0}
        platforms[name] = value
    value.setdefault("status", "pending")
    value.setdefault("attempts", 0)
    return value


def _target_ready(name: str) -> bool:
    if name == "telegram":
        return bool(radar.BOT_TOKEN)
    if name == "bale":
        return bool(radar.BALE_BOT_TOKEN and radar.BALE_CHANNEL_ID)
    if name == "rubika":
        return bool(
            os.getenv("RUBIKA_ENABLE_PUBLISHING", "false").strip().lower() in {"1", "true", "yes", "on"}
            and os.getenv("RUBIKA_BOT_TOKEN", "").strip()
            and os.getenv("RUBIKA_CHANNEL_ID", "").strip()
        )
    if name == "eitaa":
        return bool(
            os.getenv("EITAA_ENABLE_PUBLISHING", "false").strip().lower() in {"1", "true", "yes", "on"}
            and os.getenv("EITAA_BOT_TOKEN", "").strip()
            and os.getenv("EITAA_CHANNEL_ID", "").strip()
        )
    if name == "youtube":
        try:
            from short_video import youtube_credentials_available
            return bool(youtube_credentials_available())
        except Exception:
            return False
    if name == "aparat":
        try:
            from aparat_uploader import aparat_credentials_available
            return bool(radar.APARAT_UPLOAD_ENABLED and aparat_credentials_available())
        except Exception:
            return False
    return False


def _set_target(entry: dict, name: str, status: str, now: datetime, detail: str = "") -> None:
    target = _target(entry, name)
    target["status"] = status
    target["updated_at"] = now.isoformat()
    if detail:
        target["last_error"] = str(detail)[:300]
    elif status == "sent":
        target.pop("last_error", None)
        target.pop("next_attempt_at", None)


def _target_retry(entry: dict, name: str, now: datetime, detail: str = "") -> None:
    target = _target(entry, name)
    try:
        attempts = int(target.get("attempts") or 0) + 1
    except (TypeError, ValueError, OverflowError):
        attempts = 1
    target["attempts"] = attempts
    target["status"] = "failed"
    target["last_error"] = str(detail or "delivery_failed")[:300]
    target["next_attempt_at"] = (
        now + timedelta(seconds=min(3600, RETRY_BASE_SECONDS * (2 ** min(attempts - 1, 4))))
    ).isoformat()


def _record_from_item(item: dict, old: dict | None, now: datetime, delivery_id: str) -> dict:
    expiry_at = str(item.get("deal_expires_at") or "").strip()
    same_delivery = isinstance(old, dict) and str(old.get("distribution_queue_id") or "") == delivery_id
    record = {
        "ts": now.timestamp(),
        "content_type": str(item.get("content_type") or "product"),
        "content_id": str(item.get("content_id") or item.get("product_id") or ""),
        "sequence_number": item.get("sequence_number"),
        "title": str(item.get("title") or "پیشنهاد منتخب آفرچین"),
        "brand": str(item.get("brand") or item.get("brand_name") or ""),
        "publication_category": radar._publication_diversity_group(item)[0],
        "publication_family": radar._publication_diversity_group(item)[1],
        "publication_use_case": radar._publication_use_case_group(item),
        "catalog_category_id": str(item.get("catalog_category_id") or ""),
        "catalog_category_name": str(item.get("catalog_category_name") or ""),
        "catalog_category_ids": list(item.get("catalog_category_ids") or []),
        "catalog_category_path": item.get("catalog_category_path") or item.get("category_path") or "",
        "catalog_best_selling_category_id": str(item.get("catalog_best_selling_category_id") or ""),
        "catalog_best_selling_category_name": str(item.get("catalog_best_selling_category_name") or ""),
        "catalog_best_selling_ranks_by_category": (
            dict(item.get("catalog_best_selling_ranks_by_category"))
            if isinstance(item.get("catalog_best_selling_ranks_by_category"), dict) else {}
        ),
        "product_url": str(item.get("product_url") or ""),
        "image_url": str(item.get("image_url") or ""),
        "video_generation_status": "pending",
        "youtube_upload_status": "pending",
        "aparat_upload_status": "pending",
        "filo_upload_status": "pending",
        "click_tracking_url": "",
        "telegram_message_id": None,
        "bale_message_id": None,
        "delivery_version": 1,
        "delivery_status": {name: "pending" for name in PLATFORM_NAMES},
        "delivery_attempts": {name: 0 for name in PLATFORM_NAMES},
        "expires_at": expiry_at,
        "expiry_source": str(item.get("expiry_source") or "unavailable"),
        "expiry_estimated": bool(item.get("expiry_estimated")),
        "expiry_deadline_verified_directly": (
            item.get("expiry_deadline_verified_directly") is True
            and str(item.get("expiry_source") or "") in {
                "digikala_live_deals_feed", "digikala_product_detail_api"
            }
        ),
        "expiry_deadline_verified_from_site_card": (
            item.get("expiry_deadline_verified_from_site_card") is True
            and str(item.get("expiry_source") or "") == "digikala_mcp_offer_card"
        ),
        "caption_deadline_format_version": radar.CAPTION_DEADLINE_FORMAT_VERSION,
        "posted_discount_percent": int(item.get("discount_percent") or 0),
        "selection_discount_floor": int(
            item.get("selection_discount_floor") or radar.DISCOUNT_FALLBACK_FLOORS[0]
        ),
        "selection_discount_band": str(item.get("selection_discount_band") or ""),
        "creative_experiment_id": str(item.get("creative_experiment_id") or ""),
        "creative_variant": str(item.get("creative_variant") or "A").upper(),
        "caption_experiment_id": str(item.get("caption_experiment_id") or ""),
        "caption_variant": str(item.get("caption_variant") or "A").upper(),
        "selection_demand_evidence": str(item.get("selection_demand_evidence") or "none"),
        "selection_demand_quality": str(item.get("selection_demand_quality") or "unknown"),
        "selection_continuity_mode": str(item.get("selection_continuity_mode") or ""),
        "emergency_continuity_snapshot_sha256": str(item.get("emergency_continuity_snapshot_sha256") or ""),
        "emergency_continuity_baseline_completed_at": str(item.get("emergency_continuity_baseline_completed_at") or ""),
        "selection_four_factor": (
            dict(item.get("selection_four_factor"))
            if isinstance(item.get("selection_four_factor"), dict) else {}
        ),
        "emergency_continuity_quality_score": item.get("emergency_continuity_quality_score"),
        "selection_bestseller_rank": item.get("selection_bestseller_rank"),
        "selection_bestseller_category_count": int(item.get("selection_bestseller_category_count") or 0),
        "selection_bestseller_rank_improvement": int(item.get("selection_bestseller_rank_improvement") or 0),
        "posted_current_price": int(item.get("current_price") or 0),
        "posted_original_price": int(item.get("original_price") or 0),
        "selection_review_growth_evidence": str(item.get("selection_review_growth_evidence") or "none"),
        "review_growth_proxy_verified": item.get("selection_review_growth_evidence") == "verified_indirect_proxy_not_sales",
        "review_growth_proxy_count": int(item.get("recent_review_growth_window", item.get("recent_review_growth_7d")) or 0),
        "review_growth_proxy_window_hours": float(item.get("demand_window_hours") or 0),
        "review_growth_proxy_observed_at": str(item.get("demand_observed_at") or ""),
        "review_growth_proxy_source": str(item.get("demand_signal_source") or ""),
        "history_status": str(item.get("history_status") or ""),
        "historical_deal_eligible": item.get("historical_deal_eligible") is True,
        "discount_vs_30d_median_pct": item.get("discount_vs_30d_median_pct"),
        "history_days": int(item.get("history_days") or 0),
        "history_checked_at": str(item.get("history_checked_at") or ""),
        "market_price_checked_at": str(item.get("market_price_checked_at") or ""),
        "market_status": str(item.get("market_status") or ""),
        "market_reference_kind": str(item.get("market_reference_kind") or ""),
        "market_price_advantage_pct": item.get("market_price_advantage_pct"),
        "catalog_sort_mode": str(item.get("catalog_sort_mode") or ""),
        "catalog_best_selling_rank": item.get("catalog_best_selling_rank"),
        "catalog_best_selling_category_id": str(item.get("catalog_best_selling_category_id") or ""),
        "catalog_best_selling_category_name": str(item.get("catalog_best_selling_category_name") or ""),
        "catalog_rank_observed_at": str(item.get("catalog_rank_observed_at") or ""),
        "catalog_cycle_completed_at": str(item.get("catalog_cycle_completed_at") or ""),
        "catalog_cycle_snapshot_rank": item.get("catalog_cycle_snapshot_rank"),
        "promo_score": int(item.get("promo_score") or 0),
        "click_count_30d": int(item.get("click_count_30d") or 0),
        "distribution_queue_id": str(item.get("product_id") or ""),
    }
    old_history = list(old.get("post_history") or []) if isinstance(old, dict) and isinstance(old.get("post_history"), list) else []
    if isinstance(old, dict) and old and not same_delivery:
        snapshot = dict(old)
        snapshot.pop("post_history", None)
        if any(str(snapshot.get(k) or "").isdigit() for k in ("telegram_message_id", "bale_message_id")) or snapshot.get("youtube_video_id") or snapshot.get("aparat_video_hash") or snapshot.get("filo_video_url") or snapshot.get("filo_video_code"):
            old_history.append(snapshot)
    if old_history:
        record["post_history"] = old_history[-12:]
    # Only reuse destination IDs for a retry of the exact queue generation.
    # A later campaign for the same product must never inherit old platform IDs.
    if same_delivery:
        for field in (
            "telegram_message_id", "bale_message_id", "youtube_video_id",
            "youtube_video_url", "youtube_upload_status", "youtube_uploaded_at",
            "aparat_video_hash", "aparat_video_url", "aparat_upload_status",
            "aparat_uploaded_at", "filo_video_url", "filo_video_code",
            "filo_upload_status", "filo_submitted_at", "filo_visibility",
            "filo_last_error", "filo_upload_attempts", "filo_next_attempt_at",
            "filo_review_required", "video_file_name", "video_generation_status",
            "platform_message_ids", "platform_delivery_receipts",
        ):
            if old.get(field) not in (None, ""):
                record[field] = old[field]
        if isinstance(old.get("delivery_status"), dict):
            record["delivery_status"].update(old["delivery_status"])
        if isinstance(old.get("delivery_attempts"), dict):
            record["delivery_attempts"].update(old["delivery_attempts"])
    record["distribution_queue_id"] = delivery_id
    return record


def _valid_emergency_continuity_override(
    payload: dict,
    state: dict | None,
    now: datetime,
) -> bool:
    """Verify a demand-only exception against the active, hash-pinned lead snapshot."""
    if not isinstance(state, dict):
        return False
    if (
        payload.get("selection_continuity_mode") != "temporary_three_factor_demand_relaxation"
        or payload.get("selection_demand_evidence") != "not_verified_emergency_continuity_override"
        or payload.get("selection_demand_quality") != "demand_not_verified_three_factor_proxy_only"
    ):
        return False
    record = state.get("emergency_continuity")
    if not isinstance(record, dict) or record.get("status") != "active":
        return False
    expires = _utc(record.get("expires_at"))
    if expires is None or expires <= now:
        return False
    snapshot_sha = str(record.get("baseline_snapshot_sha256") or "").strip()
    baseline_completed = str(record.get("baseline_clean_cycle_completed_at") or "").strip()
    if (
        not re.fullmatch(r"[a-f0-9]{64}", snapshot_sha)
        or payload.get("emergency_continuity_snapshot_sha256") != snapshot_sha
        or payload.get("emergency_continuity_baseline_completed_at") != baseline_completed
    ):
        return False
    factors = payload.get("selection_four_factor")
    if not isinstance(factors, dict):
        factors = payload.get("offerchin_four_factor")
    if not isinstance(factors, dict):
        return False
    try:
        discount = float(factors.get("discount_attractiveness") or 0)
        affordability = float(factors.get("affordability") or 0)
        generality = float(factors.get("generality") or 0)
    except (TypeError, ValueError, OverflowError):
        return False
    if min(discount, affordability, generality) <= 0:
        return False
    harmonic = 3 / (1 / discount + 1 / affordability + 1 / generality)
    if discount < 55 or affordability < 40 or generality < 50 or harmonic < 55:
        return False
    try:
        verified_leads = radar.load_emergency_continuity_candidates(
            record,
            radar.CATALOG_SWEEP_CANDIDATES,
            now=now,
            limit=1,
            required_product_id=str(payload.get("product_id") or ""),
        )
    except Exception as exc:
        print(f"EMERGENCY_CONTINUITY_VERIFY_FAILED error={type(exc).__name__}")
        return False
    if not verified_leads or not verified_leads.get("candidates"):
        return False
    return True


def _fresh_selected_item(
    entry: dict,
    now: datetime,
    catalog_context: dict | None = None,
    *,
    require_catalog_membership: bool = True,
    state: dict | None = None,
) -> tuple[dict | None, str]:
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return None, "missing_selection_payload"
    # New products need fresh demand evidence. Once any destination has been
    # successfully delivered, retries only finish that same publication; do not
    # strand already-sent Telegram/Bale posts because the evidence later ages out.
    emergency_override = _valid_emergency_continuity_override(payload, state, now)
    if (
        not radar.has_verified_market_demand(payload, now=now)
        and not emergency_override
        and not _has_successful_destination(entry)
    ):
        return None, "selection_demand_evidence_missing_or_stale"
    if (
        require_catalog_membership
        and catalog_context is not None
        and not emergency_override
        and not radar.catalog_candidate_is_publishable(payload, catalog_context)
    ):
        return None, "catalog_snapshot_candidate_stale"
    product_url = radar.safe_product_url(str(payload.get("product_url") or ""))
    product_id = str(payload.get("product_id") or "").lower()
    if not product_url or radar.product_id(product_url) != product_id:
        return None, "invalid_product_identity"
    # Older persisted selections may carry the former 35–50% tiers and
    # review-growth requirements. The current policy accepts every real markdown;
    # the live product read below is authoritative for stock, price and contents.
    minimum_discount_percent = radar.MIN_DISCOUNT_FALLBACK_PERCENT

    try:
        fresh = radar.fetch_product_record(product_url)
    except Exception as exc:
        return None, f"live_product_fetch_{type(exc).__name__}"
    if not isinstance(fresh, dict):
        return None, "live_product_details_incomplete"
    if radar.is_prohibited_product_title(fresh.get("title")):
        return None, "live_product_prohibited_title"
    if not radar.is_publishable_product_title(fresh.get("title")) or not fresh.get("image_url"):
        return None, "live_product_details_incomplete"
    fresh["product_id"] = product_id
    fresh["product_url"] = product_url
    fresh["merchant"] = "اسنپ‌شاپ" if product_id.startswith("snp-") else "دیجی‌کالا"
    fresh["selection_discount_floor"] = radar.MIN_DISCOUNT_FALLBACK_PERCENT
    fresh["selection_discount_band"] = "1%+"

    try:
        selected_price = int(payload.get("current_price") or 0)
        live_price = int(fresh.get("current_price") or 0)
    except (TypeError, ValueError, OverflowError):
        return None, "live_price_unusable"
    if selected_price <= 0 or live_price <= 0:
        return None, "live_price_unusable"
    if live_price != selected_price:
        return None, f"selected_price_stale_selected={selected_price}_live={live_price}"

    # Never reuse stale listing values. The fresh product read below is authoritative.
    fresh["affiliate_url"] = str(payload.get("affiliate_url") or "").strip()
    if not fresh["affiliate_url"]:
        fresh["affiliate_url"] = radar.build_affilio_tracking_link(product_url)
    fresh["has_affiliate_link"] = bool(fresh["affiliate_url"])
    for key in (
        "recent_review_growth_7d", "recent_review_growth_window",
        "demand_window_hours", "demand_observed_at", "demand_signal_source",
        "history_status", "historical_deal_eligible",
        "discount_vs_30d_median_pct", "history_days", "history_checked_at", "promo_score",
        "click_count_30d", "market_status", "market_reference_kind",
        "market_reference_price_toman", "market_price_advantage_pct", "market_price_checked_at",
        "market_match_score", "market_seller_count", "catalog_sort_mode",
        "catalog_best_selling_rank", "catalog_category_id", "catalog_category_name",
        "catalog_category_ids", "catalog_category_path", "catalog_best_selling_ranks_by_category",
        "catalog_best_selling_category_id", "catalog_best_selling_category_name",
        "catalog_rank_observed_at", "catalog_cycle_completed_at", "catalog_cycle_snapshot_rank",
        "publication_policy", "selection_demand_evidence", "selection_demand_quality",
        "selection_continuity_mode", "emergency_continuity_snapshot_sha256",
        "emergency_continuity_baseline_completed_at", "selection_four_factor",
        "emergency_continuity_quality_score",
        "selection_bestseller_rank", "selection_bestseller_category_count",
        "selection_bestseller_rank_improvement", "selection_review_growth_evidence",
        "selection_value_evidence", "selection_fallback_mode",
        "creative_experiment_id", "creative_variant",
        "caption_experiment_id", "caption_variant",
    ):
        if key in payload:
            fresh[key] = payload[key]
    if not fresh.get("affiliate_url") or not radar._is_valid_affilio_tracking_url(fresh["affiliate_url"]):
        return None, "affiliate_link_not_verified"

    try:
        fresh = radar.score_product(fresh)
    except Exception:
        pass
    price_check = radar.verify_live_page_price(fresh)
    if not price_check.get("ok"):
        return None, f"live_price_recheck_{price_check.get('reason') or 'unconfirmed'}"
    if price_check.get("page_price") and int(price_check["page_price"]) != live_price:
        return None, "live_page_price_changed_during_validation"

    # Prefer a current page/API deadline, otherwise keep the selected card timer
    # only if the price still matches; the price-audit monitor will invalidate
    # open-ended offers if price/stock later changes.
    # Preserve the selected live-card deadline only when the fresh product price
    # still matches. Prefer any newer deadline returned by the page/API.
    current_deadline = str(
        price_check.get("deal_expires_at")
        or fresh.get("deal_expires_at")
        or payload.get("deal_expires_at")
        or ""
    ).strip()
    if current_deadline:
        fresh["deal_expires_at"] = current_deadline
        source_candidates = [
            str(price_check.get("expiry_source") or ""),
            str(fresh.get("expiry_source") or ""),
            str(payload.get("expiry_source") or ""),
        ]
        valid_deadline_sources = {
            "digikala_live_deals_feed",
            "digikala_product_detail_api",
            "digikala_mcp_offer_card",
        }
        source = next((value for value in source_candidates if value in valid_deadline_sources), "")
        if not source:
            source = next((value for value in source_candidates if value), "")
        if source:
            fresh["expiry_source"] = source
        if source in {"digikala_live_deals_feed", "digikala_product_detail_api"}:
            fresh["expiry_deadline_verified_directly"] = True
            fresh["expiry_deadline_verified_from_site_card"] = False
            fresh["expiry_estimated"] = False
        elif source == "digikala_mcp_offer_card":
            fresh["expiry_deadline_verified_from_site_card"] = (
                price_check.get("expiry_deadline_verified_from_site_card") is True
                or fresh.get("expiry_deadline_verified_from_site_card") is True
                or payload.get("expiry_deadline_verified_from_site_card") is True
            )
            fresh["expiry_deadline_verified_directly"] = False
            fresh["expiry_estimated"] = False
    else:
        fresh["deal_expires_at"] = ""
        fresh["expiry_source"] = "unavailable"
        fresh["expiry_deadline_verified_directly"] = False
        fresh["expiry_deadline_verified_from_site_card"] = False
        fresh["expiry_estimated"] = False

    if fresh.get("availability") != "in_stock":
        return None, "live_stock_not_confirmed"
    if not radar.is_discount_publish_eligible(
        fresh, minimum_discount_percent=minimum_discount_percent, now=now
    ):
        return None, "live_discount_no_longer_eligible"

    # Demand/review-growth and independent positive market/history signals never
    # gate an already selected live markdown. Fresh verified contradictions were
    # already applied by is_discount_publish_eligible above.
    if not radar.has_publishable_expiry_or_open_offer(fresh, now):
        return None, "live_offer_expired_or_unverified"
    expiry = _utc(fresh.get("deal_expires_at"))
    if expiry and expiry <= now + timedelta(minutes=radar.MIN_PUBLICATION_RUNWAY_MINUTES):
        return None, "insufficient_publication_runway"
    return fresh, ""


def _process_photo_destination(
    state: dict,
    entry: dict,
    record: dict,
    item: dict,
    image_bytes: bytes,
    destination: str,
    now: datetime,
) -> None:
    target = _target(entry, destination)
    record_status = record.setdefault("delivery_status", {})
    status = str(target.get("status") or "pending")
    if status == "sent":
        return
    if status == "sending":
        started = _utc(target.get("attempt_started_at"))
        if started and (now - started).total_seconds() < 1800:
            return
        _set_target(entry, destination, "manual_review", now, "previous_send_outcome_unknown")
        record_status[destination] = "manual_review"
        _save(state)
        print(f"PLATFORM_DELIVERY_MANUAL_REVIEW product_id={entry['product_id']} platform={destination} reason=previous_send_outcome_unknown")
        return
    if not _target_ready(destination):
        _set_target(entry, destination, "not_connected", now, "credentials_not_configured")
        record_status[destination] = "not_connected"
        _save(state)
        return
    retry_at = _utc(target.get("next_attempt_at"))
    if status in {"failed", "retry"} and retry_at and retry_at > now:
        return

    # Persist an in-flight marker before the external side effect. If a runner is
    # interrupted here, don't blindly repeat an uncertain send on the next cycle.
    target["status"] = "sending"
    target["attempt_started_at"] = now.isoformat()
    try:
        target["attempts"] = int(target.get("attempts") or 0) + 1
    except (TypeError, ValueError, OverflowError):
        target["attempts"] = 1
    _save(state)
    try:
        if destination in {"rubika", "eitaa"}:
            from messenger_adapters import send_photo
            result = send_photo(destination, item, image_bytes, str(item["affiliate_url"]), radar)
        else:
            result = radar._send_platform_photo(destination, item, image_bytes, str(item["affiliate_url"]))
        message_id = result.get("message_id")
        delivery_receipt = result.get("delivery_receipt")
        if not message_id and not delivery_receipt:
            raise RuntimeError("platform returned neither message_id nor acceptance receipt")
        sent_at = _now()
        _set_target(entry, destination, "sent", sent_at)
        record_status[destination] = "sent"
        record[f"{destination}_posted_at"] = sent_at.isoformat()
        if destination == "telegram":
            record["telegram_message_id"] = message_id
        elif destination == "bale":
            record["bale_message_id"] = message_id
        elif message_id:
            # Store only real message identifiers returned by the destination API.
            record.setdefault("platform_message_ids", {})[destination] = message_id
        elif delivery_receipt:
            # Some APIs confirm acceptance without exposing a message ID.
            record.setdefault("platform_delivery_receipts", {})[destination] = str(delivery_receipt)
        record.setdefault("delivery_attempts", {})[destination] = target["attempts"]
        record["delivery_last_attempt_at"] = _now().isoformat()
        _save(state)
        print(
            f"PLATFORM_DELIVERY_OK product_id={entry['product_id']} platform={destination} "
            f"message_id={message_id or 'not_returned'} receipt_only={bool(delivery_receipt and not message_id)}"
        )
    except Exception as exc:
        safe_detail = _safe_delivery_error(exc)
        _target_retry(entry, destination, _now(), f"{type(exc).__name__}: {safe_detail}"[:180])
        record_status[destination] = "failed"
        record.setdefault("delivery_attempts", {})[destination] = target["attempts"]
        record["delivery_last_attempt_at"] = _now().isoformat()
        _save(state)
        print(
            f"PLATFORM_DELIVERY_FAILED product_id={entry['product_id']} platform={destination} "
            f"error={type(exc).__name__} detail={safe_detail}"
        )


def _process_video_destinations(state: dict, entry: dict, record: dict, now: datetime) -> None:
    product_id = str(entry.get("product_id") or "")
    for target_name in VIDEO_PLATFORMS:
        target = _target(entry, target_name)
        if target.get("status") == "sent":
            continue
        if not _target_ready(target_name):
            _set_target(entry, target_name, "not_connected", now, "credentials_not_configured")
            _save(state)
        elif target.get("status") == "not_connected":
            # A later-added platform becomes eligible without rerunning discovery.
            target["status"] = "pending"
            target.pop("last_error", None)
            _save(state)
    if any(_target(entry, name).get("status") in {"pending", "failed", "retry", "sending"} for name in VIDEO_PLATFORMS):
        try:
            # The same selected product is processed immediately. The video processor
            # bypasses only its normal cross-item time slot, not platform quotas or errors.
            radar.process_pending_short_video(
                state,
                now=now,
                destinations={"youtube", "aparat"},
                # Respect each video platform's own quota/cadence. The selected
                # content remains queued for that destination until its next slot.
                force_due=False,
                only_product_id=product_id,
            )
        except Exception as exc:
            print(f"VIDEO_DESTINATION_DISPATCH_FAILED product_id={product_id} error={type(exc).__name__}")
            record["video_delivery_last_error"] = type(exc).__name__
            _save(state)

    youtube_status = str(record.get("youtube_upload_status") or "pending")
    if youtube_status == "uploaded":
        _set_target(entry, "youtube", "sent", _now())
    elif not _target_ready("youtube"):
        _set_target(entry, "youtube", "not_connected", _now(), "credentials_not_configured")
    elif youtube_status == "upload_result_unknown":
        _set_target(entry, "youtube", "manual_review", _now(), str(record.get("youtube_last_error") or "upload_result_unknown"))
    elif youtube_status == "skipped_unverified_deadline":
        _target(entry, "youtube")["status"] = "pending"
        _target(entry, "youtube")["last_error"] = "waiting_for_verified_deadline"
    elif youtube_status in {"retry", "pending", "pending_credentials", "uploading"}:
        t = _target(entry, "youtube")
        t["status"] = "failed" if youtube_status == "retry" else "pending"
        t["last_error"] = str(record.get("youtube_last_error") or youtube_status)
        next_slot = (
            _utc(record.get("youtube_next_attempt_at"))
            or _utc(state.get("youtube_uploads_paused_until"))
            or _utc(state.get("youtube_next_upload_at"))
        )
        t["next_attempt_at"] = (
            next_slot if next_slot and next_slot > now else now + timedelta(minutes=15)
        ).isoformat()
    else:
        _target(entry, "youtube")["status"] = "pending"

    aparat_status = str(record.get("aparat_upload_status") or "pending")
    if aparat_status == "uploaded":
        _set_target(entry, "aparat", "sent", _now())
    elif not _target_ready("aparat"):
        _set_target(entry, "aparat", "not_connected", _now(), "credentials_not_configured")
    elif aparat_status == "upload_result_unknown":
        _set_target(entry, "aparat", "manual_review", _now(), str(record.get("aparat_last_error") or "upload_result_unknown"))
    elif aparat_status == "waiting_shorts_uploader":
        _set_target(entry, "aparat", "manual_review", _now(), "shorts_uploader_not_supported_by_current_path")
    elif aparat_status == "skipped_unverified_deadline":
        _target(entry, "aparat")["status"] = "pending"
        _target(entry, "aparat")["last_error"] = "waiting_for_verified_deadline"
    elif aparat_status in {"retry", "pending", "pending_credentials", "uploading"}:
        t = _target(entry, "aparat")
        t["status"] = "failed" if aparat_status == "retry" else "pending"
        t["last_error"] = str(record.get("aparat_last_error") or aparat_status)
        next_slot = _utc(record.get("aparat_next_attempt_at")) or _utc(state.get("aparat_next_upload_at"))
        t["next_attempt_at"] = (
            next_slot if next_slot and next_slot > now else now + timedelta(minutes=15)
        ).isoformat()
    else:
        _target(entry, "aparat")["status"] = "pending"
    _save(state)


def editorial_fifo_lock_entry(state: dict) -> dict | None:
    """Apply the editorial FIFO only when its scheduled gap has arrived.

    Products whose slots precede the editorial remain first. Editorial items whose
    slots are later than the upcoming editorial are not allowed to block those products.
    Video uploads retain their own FIFO and never hold back channel publication.
    """
    enabled = os.getenv("OFFERCHIN_EDITORIAL_PUBLISH_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if not enabled:
        return None
    now = _now()
    queue = state.get("editorial_delivery_queue")
    active = [
        value for value in (queue.values() if isinstance(queue, dict) else [])
        if isinstance(value, dict) and value.get("status") not in {"completed", "cancelled", "failed"}
    ]
    locks = []
    for entry in active:
        platforms = entry.get("platforms") if isinstance(entry.get("platforms"), dict) else {}
        core_statuses = [
            (str((platforms.get(destination) or {}).get("status") or "pending").strip().lower()
             if isinstance(platforms.get(destination), dict) else "pending")
            for destination in CORE_PHOTO_PLATFORMS
        ]
        core_sent = any(status == "sent" for status in core_statuses)
        core_pending = any(status not in TERMINAL_PLATFORM for status in core_statuses)
        # Keep the related editorial ahead of its product until both core photo
        # channels are terminal, but the bounded max-block timeout below prevents a stall.
        if not core_pending:
            continue
        scheduled = _utc(entry.get("scheduled_at")) or _utc(entry.get("selected_at")) or now
        attempt_anchor = _utc(entry.get("last_attempt_at")) or _utc(entry.get("selected_at")) or scheduled
        max_block = max(1, min(30, int(os.getenv("OFFERCHIN_EDITORIAL_PRODUCT_BLOCK_MAX_MINUTES", "8"))))
        if now - attempt_anchor > timedelta(minutes=max_block):
            print(
                "PUBLISHER_EDITORIAL_LOCK_RELEASED "
                f"content_id={entry.get('content_id', 'unknown')} reason=max_block_wait_exceeded "
                f"minutes={max_block}"
            )
            continue
        if scheduled <= now:
            locks.append((scheduled, entry))
    if not locks:
        return None

    editorial_at, editorial = min(
        locks,
        key=lambda row: (row[0], int(row[1].get("sequence_number") or 0)),
    )
    product_queue = state.get("content_delivery_queue")
    for product_id, entry in (product_queue.items() if isinstance(product_queue, dict) else []):
        if not isinstance(entry, dict) or entry.get("status") in {"published", "cancelled", "stale_selection"}:
            continue
        if str(entry.get("content_type") or "product") != "product":
            continue
        platforms = entry.get("platforms") if isinstance(entry.get("platforms"), dict) else {}
        if any(
            isinstance(platforms.get(name), dict) and platforms[name].get("status") == "sent"
            for name in CORE_PHOTO_PLATFORMS
        ):
            continue
        product_at = _utc(entry.get("scheduled_at"))
        if product_at is not None and product_at <= editorial_at:
            print(
                "PUBLISHER_EDITORIAL_WAIT_FOR_EARLIER_PRODUCT "
                f"editorial_id={editorial.get('content_id', 'unknown')} "
                f"product_id={product_id} product_slot={product_at.isoformat()} "
                f"editorial_slot={editorial_at.isoformat()}"
            )
            return None
    return editorial


def publish_due_queue(_fallback_depth: int = 0) -> int:
    validate_registry()
    state = radar.load_state(apply_integrity_ledger=False)
    if apply_integrity_audit_ledger(state):
        _save(state)
        print("PUBLISHER_INTEGRITY_LEDGER_APPLIED")
    now = _now()
    oldest_editorial = editorial_fifo_lock_entry(state)
    if oldest_editorial:
        print(
            "PUBLISHER_EDITORIAL_FIFO_LOCK "
            f"content_id={oldest_editorial.get('content_id', 'unknown')} "
            f"sequence={oldest_editorial.get('sequence_number', 'unknown')}; "
            "newer product selections remain queued until editorial destinations are terminal"
        )
        return 0
    catalog_context = radar.publication_catalog_context()
    evicted = enforce_queue_limit(state, now=now)
    if evicted:
        _save(state)
        print(f"PUBLISHER_RETRY_QUEUE_BOUNDED evicted={evicted}")
    queue = state.get("content_delivery_queue")
    if not isinstance(queue, dict) or not queue:
        print("PUBLISHER_QUEUE_EMPTY")
        return 0
    due = due_content(state, now=now, limit=MAX_ITEMS_PER_RUN)
    if not due:
        print(f"PUBLISHER_NOTHING_DUE queue_size={len(queue)}")
        return 0

    sent_content = 0
    fallback_promoted = False
    for product_id, entry in due:
        if not isinstance(entry, dict):
            continue
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        delivery_id = f"{product_id}:{entry.get('selected_at') or entry.get('scheduled_at') or 'unknown'}"
        existing = state.get("published", {}).get(product_id)
        duplicate_reason = _duplicate_guard_reason(existing, delivery_id)
        if duplicate_reason:
            # A stale queue entry can survive after another run has already sent the
            # same product. Cancel it before any media/network side effects and preserve
            # the current public record; this is a last-line guard beyond discovery dedupe.
            entry["status"] = "cancelled"
            entry["last_detail"] = duplicate_reason
            finish_queue_item(state, product_id, "cancelled", now=now, detail=duplicate_reason)
            state.get("pending_queue", {}).pop(product_id, None)
            _save(state)
            print(f"CONTENT_DUPLICATE_BLOCKED product_id={product_id} reason={duplicate_reason}")
            continue
        delivery_targets = entry.get("platforms")
        already_partially_delivered = isinstance(delivery_targets, dict) and any(
            isinstance(target, dict) and target.get("status") == "sent"
            for target in delivery_targets.values()
        )
        emergency_override = _valid_emergency_continuity_override(payload, state, now)
        if (
            not already_partially_delivered
            and catalog_context.get("mode") == "blocked"
            and not emergency_override
        ):
            entry["status"] = "queued"
            entry["last_detail"] = "verified_full_catalog_snapshot_unavailable"
            entry["next_attempt_at"] = (now + timedelta(minutes=5)).isoformat()
            _save(state)
            print(
                f"PUBLISHER_CATALOG_GATE_BLOCKED product_id={product_id} "
                "reason=verified_full_catalog_snapshot_unavailable"
            )
            continue
        if not already_partially_delivered:
            allowed = radar._filter_recent_publication_repeats(
                [payload],
                state.get("published"),
                state.get("recent_publications"),
                now,
                limit=1,
                label="PUBLISHER_LAST_MILE",
            )
            if not allowed:
                raw_fallbacks = list(entry.get("fallback_candidates") or [])
                safe_fallbacks = radar._filter_recent_publication_repeats(
                    raw_fallbacks,
                    state.get("published"),
                    state.get("recent_publications"),
                    now,
                    label="PUBLISHER_FALLBACK",
                )
                reason = "recent_product_family_or_brand_cooldown"
                entry["status"] = "stale_selection"
                entry["last_detail"] = reason
                finish_queue_item(state, product_id, "stale_selection", now=now, detail=reason)
                state.get("pending_queue", {}).pop(product_id, None)
                promoted_id = promote_fallback_selection(
                    state, safe_fallbacks, now=now, reason=reason
                ) if safe_fallbacks else None
                if promoted_id:
                    fallback_promoted = True
                _save(state)
                print(
                    f"CONTENT_DIVERSITY_BLOCKED product_id={product_id} "
                    f"fallback_promoted={bool(promoted_id)}"
                )
                continue
        entry["status"] = "publishing"
        entry["last_attempt_at"] = now.isoformat()
        try:
            entry["attempt_count"] = int(entry.get("attempt_count") or 0) + 1
        except (TypeError, ValueError, OverflowError):
            entry["attempt_count"] = 1
        _save(state)

        fresh, reason = _fresh_selected_item(
            entry,
            now,
            catalog_context,
            require_catalog_membership=not already_partially_delivered,
            state=state,
        )
        if fresh is None:
            # A selected item that no longer matches its live price is removed
            # from the delivery queue and will re-enter only after fresh selection.
            if reason.startswith("selected_price_stale") or reason in {
                "invalid_product_identity", "live_product_details_incomplete",
                "catalog_snapshot_candidate_stale",
                "live_stock_not_confirmed", "live_discount_no_longer_eligible",
                "live_market_value_rejected", "live_offer_expired_or_unverified",
                "insufficient_publication_runway",
            }:
                radar.mark_selection_candidate_rejected(state, payload, reason, now=now)
                raw_fallback_candidates = list(entry.get("fallback_candidates") or [])
                fallback_candidates = _eligible_fallback_candidates(raw_fallback_candidates, now, catalog_context)
                rejected_fallbacks = len(raw_fallback_candidates) - len(fallback_candidates)
                if rejected_fallbacks:
                    print(
                        f"INLINE_FALLBACK_FILTERED rejected={rejected_fallbacks} "
                        "reason=live_discount_or_product_safety_gate"
                    )
                entry["status"] = "stale_selection"
                entry["last_detail"] = reason
                finish_queue_item(state, product_id, "stale_selection", now=now, detail=reason)
                state.get("pending_queue", {}).pop(product_id, None)
                promoted_id = promote_fallback_selection(
                    state, fallback_candidates, now=now, reason=reason
                ) if fallback_candidates else None
                if promoted_id:
                    fallback_promoted = True
                _save(state)
                print(f"CONTENT_SELECTION_STALE product_id={product_id} reason={reason}")
                continue
            entry["status"] = "queued"
            entry["last_detail"] = reason
            entry["next_attempt_at"] = (now + timedelta(seconds=RETRY_BASE_SECONDS)).isoformat()
            for name in ("telegram", "bale", "youtube", "aparat"):
                target = _target(entry, name)
                if target.get("status") not in {"sent", "not_connected", "manual_review"}:
                    _target_retry(entry, name, now, reason)
            _save(state)
            print(f"CONTENT_REVALIDATION_DEFERRED product_id={product_id} reason={reason}")
            continue

        # The product-detail API response is a fresh SKU snapshot, not the hand-off
        # envelope. Reattach immutable queue identity/order before creating a video record.
        fresh["content_type"] = "product"
        fresh["content_id"] = str(entry.get("content_id") or payload.get("content_id") or product_id)
        fresh["sequence_number"] = entry.get("sequence_number") or payload.get("sequence_number")
        old = state.get("published", {}).get(product_id)
        if not isinstance(old, dict):
            old = {}
        record = _record_from_item(fresh, old, now, delivery_id)
        state.setdefault("published", {})[product_id] = record
        _save(state)

        try:
            image_bytes = radar._fetch_image(str(fresh.get("image_url") or ""))
        except Exception as exc:
            reason = f"image_fetch_{type(exc).__name__}"
            entry["status"] = "queued"
            entry["last_detail"] = reason
            entry["next_attempt_at"] = (now + timedelta(seconds=RETRY_BASE_SECONDS)).isoformat()
            _save(state)
            print(f"CONTENT_IMAGE_UNAVAILABLE product_id={product_id} error={type(exc).__name__}")
            continue

        prior_public_status = {
            name: str(_target(entry, name).get("status") or "pending")
            for name in PHOTO_PLATFORMS
        }
        for destination in PHOTO_PLATFORMS:
            _process_photo_destination(state, entry, record, fresh, image_bytes, destination, now)
        # The canonical selected-product record already exists in state.json.
        # The video dispatcher consumes that same record independently: no photo
        # destination needs to report "sent" before YouTube/Aparat/Filo can start.
        # Each video workflow applies only its own rate, quota, credential and expiry gates.
        state.setdefault("published", {})[product_id] = record
        _save(state)

        platforms = {name: str(_target(entry, name).get("status") or "pending") for name in PLATFORM_NAMES}
        photo_platforms = {name: platforms.get(name, "pending") for name in PHOTO_PLATFORMS}
        core_photo_platforms = {
            name: photo_platforms.get(name, "pending") for name in CORE_PHOTO_PLATFORMS
        }
        core_complete = all(
            status in TERMINAL_PLATFORM for status in core_photo_platforms.values()
        )
        core_success = any(status == "sent" for status in core_photo_platforms.values())
        completed = all(status in TERMINAL_PLATFORM for status in photo_platforms.values())
        any_success = any(status == "sent" for status in photo_platforms.values())
        unresolved = [name for name, status in photo_platforms.items() if status not in TERMINAL_PLATFORM]
        new_public_delivery = any(
            prior_public_status.get(name) != "sent" and platforms.get(name) == "sent"
            for name in CORE_PHOTO_PLATFORMS
        )
        if new_public_delivery:
            public_posted_at = _now().isoformat()
            state["last_channel_published_at"] = public_posted_at
            state["last_product_channel_published_at"] = public_posted_at
            state["last_published_at"] = public_posted_at

        # Preserve the original post timestamp when retrying pending channel platforms.
        # Video destination timestamps are maintained by their own upload workflows.
        existing_same_delivery = (
            isinstance(old, dict)
            and str(old.get("distribution_queue_id") or "") == delivery_id
        )
        if existing_same_delivery:
            sent_epochs = [
                dt.timestamp()
                for name in CORE_PHOTO_PLATFORMS
                if _target(entry, name).get("status") == "sent"
                and (dt := _utc(_target(entry, name).get("updated_at"))) is not None
            ]
            if sent_epochs:
                try:
                    previous_epoch = float(old.get("ts") or 0)
                except (TypeError, ValueError, OverflowError):
                    previous_epoch = 0
                first_channel_epoch = min(sent_epochs)
                record["ts"] = (
                    min(previous_epoch, first_channel_epoch)
                    if previous_epoch > 0 else first_channel_epoch
                )
        if completed:
            if any_success:
                record["delivery_status"] = {
                    name: ("sent" if status == "sent" else status)
                    for name, status in photo_platforms.items()
                }
                state.get("pending_queue", {}).pop(product_id, None)
                finish_queue_item(state, product_id, "published", now=_now(), detail=",".join(f"{k}={v}" for k, v in photo_platforms.items()))
                sent_content += 1
                print(f"CONTENT_CHANNEL_DELIVERY_COMPLETE product_id={product_id} photo_platforms={photo_platforms} video_uploads=independent_workflows")
            else:
                finish_queue_item(state, product_id, "cancelled", now=_now(), detail="no_connected_platform_delivered")
                print(f"CONTENT_CHANNEL_DELIVERY_CANCELLED product_id={product_id} photo_platforms={photo_platforms}")
        else:
            entry["status"] = "partial"
            retry_times = []
            for name in unresolved:
                t = _target(entry, name)
                retry_at = _utc(t.get("next_attempt_at"))
                if retry_at:
                    retry_times.append(retry_at)
                elif t.get("status") in {"pending", "failed", "retry"}:
                    retry_times.append(now + timedelta(minutes=15))
            entry["next_attempt_at"] = (min(retry_times) if retry_times else now + timedelta(minutes=15)).isoformat()
            if core_complete and core_success:
                # Telegram/Bale have completed this publication. Keep optional messenger
                # retries bounded in the background queue, but never hold the next core slot.
                optional_unresolved = [
                    name for name in unresolved if name not in CORE_PHOTO_PLATFORMS
                ]
                entry["last_detail"] = "optional_unresolved=" + ",".join(optional_unresolved)
                state.get("pending_queue", {}).pop(product_id, None)
                sent_content += 1
                print(
                    f"CONTENT_CHANNEL_CORE_COMPLETE_OPTIONAL_PENDING product_id={product_id} "
                    f"core={core_photo_platforms} optional_unresolved={optional_unresolved} "
                    f"retry_at={entry['next_attempt_at']}"
                )
            else:
                entry["last_detail"] = "unresolved=" + ",".join(unresolved)
                if core_success:
                    state.get("pending_queue", {}).pop(product_id, None)
                print(f"CONTENT_CHANNEL_DELIVERY_PARTIAL product_id={product_id} photo_platforms={photo_platforms} retry_at={entry['next_attempt_at']}")
        _save(state)

    if fallback_promoted:
        if _fallback_depth < MAX_INLINE_FALLBACK_ATTEMPTS:
            print(
                f"PUBLISHER_INLINE_FALLBACK_RETRY depth={_fallback_depth + 1} "
                "reason=primary_selection_failed_live_validation"
            )
            return publish_due_queue(_fallback_depth + 1)
        print("PUBLISHER_INLINE_FALLBACK_LIMIT_REACHED")
    print(f"PUBLISHER_RUN_SUMMARY due={len(due)} completed={sent_content} remaining={sum(1 for x in state.get('content_delivery_queue', {}).values() if isinstance(x, dict))}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(publish_due_queue())
    except Exception as exc:
        print(f"PUBLISHER_RUN_FAILED error={type(exc).__name__}: {str(exc)[:240]}")
        raise