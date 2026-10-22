"""One canonical parser for DigiKala's visible Incredible Offer countdown.

A source-relative timer on the offer card is the closest representation of the
countdown users see on DigiKala. Prefer it over nested variant timestamps, then
fall back to explicit absolute deadlines when no relative timer is provided.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ABSOLUTE_KEYS = (
    "ends_at", "endsAt", "deal_ends_at", "dealEndsAt",
    "expires_at", "expiresAt",
)
SECONDS_KEYS = (
    "ends_in_seconds", "endsInSeconds",
    "remaining_seconds", "remainingSeconds",
    "remaining_time_seconds", "remainingTimeSeconds",
    "countdown_seconds", "countdownSeconds",
)
DURATION_KEYS = (
    "ends_in", "endsIn",
    "remaining_time", "remainingTime",
    "time_remaining", "timeRemaining",
    "countdown",
)
CAMPAIGN_KEYS = (
    "campaign", "incredible_offer", "incredibleOffer", "deal", "offer",
    "promotion", "discount_campaign", "discountCampaign",
)
MAX_OFFER_SECONDS = 7 * 24 * 60 * 60
PERSIAN_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def parse_absolute_deadline(value):
    """Parse an explicitly absolute deadline to a UTC ISO timestamp."""
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
    text = str(value).translate(PERSIAN_DIGITS).strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{10,16}(?:\.\d+)?", text):
        try:
            return parse_absolute_deadline(float(text))
        except (TypeError, ValueError, OverflowError):
            return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        # DigiKala's naive deadline strings use Iran local time.
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Tehran"))
    return parsed.astimezone(timezone.utc).isoformat()


def _duration_seconds(value):
    """Parse a source-provided duration, never treating an epoch as a duration."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        normalized = {
            str(k).lower(): v
            for k, v in value.items()
        }
        units = (
            (("days", "day", "d", "روز"), 86400),
            (("hours", "hour", "h", "ساعت"), 3600),
            (("minutes", "minute", "mins", "min", "m", "دقیقه"), 60),
            (("seconds", "second", "secs", "sec", "s", "ثانیه"), 1),
        )
        total = 0.0
        found = False
        for names, factor in units:
            for name in names:
                if name in normalized:
                    try:
                        total += float(str(normalized[name]).translate(PERSIAN_DIGITS)) * factor
                        found = True
                    except (TypeError, ValueError, OverflowError):
                        return None
                    break
        if found and 0 <= total <= MAX_OFFER_SECONDS:
            return total
        return None

    text = str(value).translate(PERSIAN_DIGITS).strip().lower()
    if not text:
        return None
    try:
        seconds = float(text)
        if 0 <= seconds <= MAX_OFFER_SECONDS:
            return seconds
    except (TypeError, ValueError, OverflowError):
        pass

    # Common live countdown serializations:
    # "03:24:00" = hours:minutes:seconds; "03:24" = hours:minutes.
    match = re.fullmatch(r"(\d{1,3}):(\d{1,2}):(\d{1,2})", text)
    if match:
        hours, minutes, secs = map(int, match.groups())
        if minutes < 60 and secs < 60:
            total = hours * 3600 + minutes * 60 + secs
            return float(total) if total <= MAX_OFFER_SECONDS else None
    match = re.fullmatch(r"(\d{1,3}):(\d{1,2})", text)
    if match:
        hours, minutes = map(int, match.groups())
        if minutes < 60:
            total = hours * 3600 + minutes * 60
            return float(total) if total <= MAX_OFFER_SECONDS else None

    # Some source wrappers expose the human-readable timer rather than seconds.
    unit_pattern = re.compile(
        r"(\d+(?:\.\d+)?)\s*"
        r"(days?|d|روز|hours?|hrs?|h|ساعت|minutes?|mins?|m|دقیقه|seconds?|secs?|s|ثانیه)"
    )
    factors = {
        "d": 86400, "day": 86400, "days": 86400, "روز": 86400,
        "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600, "ساعت": 3600,
        "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60, "دقیقه": 60,
        "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "ثانیه": 1,
    }
    matches = list(unit_pattern.finditer(text))
    if matches:
        # Do not accept a partial parse of unrelated text.
        residue = unit_pattern.sub("", text)
        residue = re.sub(r"[\s،,وand]+", "", residue)
        if residue:
            return None
        total = sum(float(m.group(1)) * factors[m.group(2)] for m in matches)
        return total if 0 <= total <= MAX_OFFER_SECONDS else None
    return None


def _direct_duration(node):
    if not isinstance(node, dict):
        return None
    for key in SECONDS_KEYS:
        if key in node:
            seconds = _duration_seconds(node.get(key))
            if seconds is not None:
                return seconds
    for key in DURATION_KEYS:
        if key in node:
            seconds = _duration_seconds(node.get(key))
            if seconds is not None:
                return seconds
    return None


def _direct_absolute(node):
    if not isinstance(node, dict):
        return ""
    for key in ABSOLUTE_KEYS:
        if key in node:
            deadline = parse_absolute_deadline(node.get(key))
            if deadline:
                return deadline
    return ""


def extract_offer_expiry(obj, now=None):
    """Return the offer's best source-backed deadline as UTC ISO, or empty string.

    Priority:
    1. Explicit relative timer on the offer card or its campaign (what the site
       visibly counts down from).
    2. Absolute deadline on the offer card or its campaign.
    3. Descendant timer/deadline fields as a last resort, never before the card's
       own fields; this prevents a default_variant from overriding the campaign.
    """
    if not isinstance(obj, dict):
        return ""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    campaigns = []
    for key in CAMPAIGN_KEYS:
        child = obj.get(key)
        if isinstance(child, dict):
            campaigns.append(child)
        elif isinstance(child, list):
            campaigns.extend(item for item in child if isinstance(item, dict))

    # Prefer the actual countdown value present on the card/campaign over
    # another absolute timestamp deeper in product/variant metadata.
    for node in (obj, *campaigns):
        seconds = _direct_duration(node)
        if seconds is not None:
            return (current + timedelta(seconds=seconds)).isoformat()

    for node in (obj, *campaigns):
        deadline = _direct_absolute(node)
        if deadline:
            return deadline

    protected = {id(obj), *(id(node) for node in campaigns)}
    descendants = [node for node in walk_dicts(obj) if id(node) not in protected]
    for node in descendants:
        seconds = _direct_duration(node)
        if seconds is not None:
            return (current + timedelta(seconds=seconds)).isoformat()
    for node in descendants:
        deadline = _direct_absolute(node)
        if deadline:
            return deadline
    return ""
