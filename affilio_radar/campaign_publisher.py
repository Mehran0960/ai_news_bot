"""One-off publisher for explicitly allowlisted Affilio campaigns.

Campaign links are not product links and must never be passed through the product
affiliate-link builder or the product click tracker. This module deliberately
accepts only the exact campaign URL supplied and tested by the OfferChin owner.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "campaigns" / "digikala-digitalchoices-1405-aban.json"
STATE_PATH = ROOT / "campaign_publication_state.json"
TEHRAN = ZoneInfo("Asia/Tehran")

# Exact allowlist: do not generalize this to arbitrary aflo.ir destinations.
ALLOWED_CAMPAIGNS = {
    "digikala-digitalchoices-1405-aban": {
        "affiliate_url": "https://aflo.ir/Dwndykmy",
        "landing_url": "https://www.digikala.com/landing/digitalchoices/",
    }
}
DESTINATIONS = ("telegram", "bale")


def validate_campaign(config: dict[str, Any]) -> None:
    campaign_id = str(config.get("campaign_id") or "")
    if campaign_id not in ALLOWED_CAMPAIGNS:
        raise ValueError("campaign_id_not_allowlisted")
    allowed = ALLOWED_CAMPAIGNS[campaign_id]
    affiliate_url = str(config.get("affiliate_url") or "").strip()
    landing_url = str(config.get("landing_url") or "").strip()
    if affiliate_url != allowed["affiliate_url"] or landing_url != allowed["landing_url"]:
        raise ValueError("campaign_destination_does_not_match_allowlist")
    parsed = urlsplit(affiliate_url)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != "aflo.ir"
        or parsed.path != "/Dwndykmy"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("campaign_affiliate_url_invalid")
    expires = str(config.get("expires_through_local_date") or "")
    if not re.fullmatch(r"2026-11-21", expires):
        raise ValueError("campaign_expiry_not_expected")
    if not str(config.get("title") or "").strip():
        raise ValueError("campaign_title_missing")


def load_campaign() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as stream:
        config = json.load(stream)
    if not isinstance(config, dict):
        raise ValueError("campaign_config_must_be_object")
    validate_campaign(config)
    return config


def load_state() -> dict[str, Any]:
    try:
        with STATE_PATH.open("r", encoding="utf-8") as stream:
            state = json.load(stream)
    except FileNotFoundError:
        state = {"campaigns": {}}
    if not isinstance(state, dict):
        state = {"campaigns": {}}
    if not isinstance(state.get("campaigns"), dict):
        state["campaigns"] = {}
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(STATE_PATH)


def campaign_is_expired(config: dict[str, Any], now: datetime | None = None) -> bool:
    current = now or datetime.now(TEHRAN)
    if current.tzinfo is None:
        current = current.replace(tzinfo=TEHRAN)
    local_date = current.astimezone(TEHRAN).date()
    end_date = date.fromisoformat(config["expires_through_local_date"])
    return local_date > end_date


def campaign_message(config: dict[str, Any]) -> str:
    deadline = str(config.get("deadline_label") or "۳۰ آبان ۱۴۰۵")
    return (
        "🔥 تخفیف ویژه کالاهای دیجیتال دیجی‌کالا\n\n"
        "🎁 با ورود به صفحه اختصاصی کمپین، کد تخفیف خودتان را دریافت کنید؛ "
        "تخفیف اضافه تا سقف ۱۵ میلیون تومان برای کالاهای دیجیتال منتخب اعلام شده است.\n\n"
        "🔎 کالاهای مشمول و شرایط استفاده را در صفحه کمپین ببینید.\n"
        f"⏳ مهلت اعلام‌شده: {deadline}\n\n"
        "آفِرچین | شکار تخفیف‌های واقعی"
    )


def _api_post(platform: str, token: str, chat_id: str, message: str, button_url: str) -> int:
    if platform == "telegram":
        endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    elif platform == "bale":
        endpoint = f"https://tapi.bale.ai/bot{token}/sendMessage"
    else:
        raise ValueError("unsupported_campaign_destination")

    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": "true",
        "reply_markup": json.dumps(
            {"inline_keyboard": [[{"text": "🎁 مشاهده تخفیف‌های دیجیتال", "url": button_url}]]},
            ensure_ascii=False,
        ),
    }
    request = Request(
        endpoint,
        data=urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        # Do not print the request URL: it contains the private bot token.
        detail = exc.read(512).decode("utf-8", errors="replace")
        raise RuntimeError(f"{platform}_http_{exc.code}: {detail[:160]}") from None
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"{platform}_{type(exc).__name__}") from None

    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"{platform}_invalid_json_response") from None
    if result.get("ok") is not True or not isinstance(result.get("result"), dict):
        detail = str(result.get("description") or "api_ok_false")[:160]
        raise RuntimeError(f"{platform}_{detail}")
    message_id = result["result"].get("message_id")
    if not str(message_id or "").isdigit():
        raise RuntimeError(f"{platform}_message_id_missing")
    return int(message_id)


def publish_campaign(*, dry_run: bool = False) -> int:
    config = load_campaign()
    if campaign_is_expired(config):
        print(f"CAMPAIGN_EXPIRED id={config['campaign_id']} no_publication=true")
        return 0

    state = load_state()
    campaign_state = state["campaigns"].setdefault(
        config["campaign_id"], {"platforms": {}}
    )
    if not isinstance(campaign_state.get("platforms"), dict):
        campaign_state["platforms"] = {}

    message = campaign_message(config)
    if dry_run:
        print("CAMPAIGN_DRY_RUN")
        print(message)
        print(f"BUTTON_URL={config['affiliate_url']}")
        return 0

    failures = 0
    for platform in DESTINATIONS:
        target = campaign_state["platforms"].setdefault(platform, {"status": "pending", "attempts": 0})
        status = str(target.get("status") or "pending")
        if status == "sent":
            print(f"CAMPAIGN_DESTINATION_ALREADY_SENT platform={platform} message_id={target.get('message_id')}")
            continue
        if status in {"sending", "manual_review"}:
            if status == "sending":
                target["status"] = "manual_review"
                target["last_error"] = "previous_send_outcome_unknown"
                save_state(state)
            print(f"CAMPAIGN_DESTINATION_REQUIRES_REVIEW platform={platform}")
            continue

        if platform == "telegram":
            token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            chat_id = os.getenv("AFFILIO_TELEGRAM_CHAT_ID", "@OfferChin").strip()
        else:
            token = os.getenv("BALE_BOT_TOKEN", "").strip()
            chat_id = os.getenv("BALE_CHANNEL_ID", "").strip()

        if not token or not chat_id:
            target["status"] = "not_connected"
            target["last_error"] = "credentials_not_configured"
            save_state(state)
            print(f"CAMPAIGN_DESTINATION_NOT_CONNECTED platform={platform}")
            continue

        target["status"] = "sending"
        target["attempts"] = int(target.get("attempts") or 0) + 1
        target["updated_at"] = datetime.now(TEHRAN).isoformat()
        save_state(state)
        try:
            message_id = _api_post(platform, token, chat_id, message, config["affiliate_url"])
            target.update({
                "status": "sent",
                "message_id": message_id,
                "updated_at": datetime.now(TEHRAN).isoformat(),
            })
            target.pop("last_error", None)
            print(f"CAMPAIGN_DELIVERY_OK campaign_id={config['campaign_id']} platform={platform} message_id={message_id}")
        except Exception as exc:
            failures += 1
            target["status"] = "failed"
            target["last_error"] = str(exc)[:200]
            target["updated_at"] = datetime.now(TEHRAN).isoformat()
            print(f"CAMPAIGN_DELIVERY_FAILED campaign_id={config['campaign_id']} platform={platform} error={type(exc).__name__}")
        save_state(state)

    return 1 if failures else 0


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv[1:]
    raise SystemExit(publish_campaign(dry_run=dry_run))
