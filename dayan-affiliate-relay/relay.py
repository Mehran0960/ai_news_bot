import asyncio
import json
import os
import re
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from telethon import TelegramClient
from telethon.sessions import StringSession

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
STATE_FILE = ROOT / "state.json"
LINKS_FILE = CONFIG / "affiliate_links.json"
OVERRIDES_FILE = CONFIG / "post_overrides.json"

SOURCE_CHANNEL = os.getenv("SOURCE_CHANNEL", "Dayan_video")
TIMEZONE = ZoneInfo("Asia/Tehran")

# Conservative launch: poll every 30 minutes, publish at up to eight spread-out
# Tehran-time slots per day. Increase only after real click/sale results.
PUBLISH_SLOTS = ["09:00", "11:00", "13:00", "15:00",
                  "17:00", "19:00", "20:30", "22:00"]
SLOT_GRACE_MINUTES = 55
MAX_QUEUE_ITEMS = 500
MAX_SENT_IDS = 2000

DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
CODE_RE = re.compile(r"(?<!\d)\d{4,7}(?!\d)")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
HANDLE_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_]{4,}")

def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc

def write_state(state):
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

def normalize_digits(text):
    return (text or "").translate(DIGIT_TRANSLATION)

def extract_codes(caption):
    text = normalize_digits(caption)
    found = []
    for value in CODE_RE.findall(text):
        number = int(value)
        # Avoid common Persian calendar years being mistaken for product codes.
        if 1300 <= number <= 1499:
            continue
        if value not in found:
            found.append(value)
    return found

def is_video_message(message):
    if not message or not message.media:
        return False
    if getattr(message, "video", None) or getattr(message, "gif", None):
        return True
    document = getattr(message.media, "document", None)
    if document:
        mime = (getattr(document, "mime_type", "") or "").lower()
        if mime.startswith("video/"):
            return True
        for attribute in getattr(document, "attributes", []) or []:
            if attribute.__class__.__name__ == "DocumentAttributeVideo":
                return True
    return False

def clean_source_caption(text):
    cleaned = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        low = line.lower()
        skip_terms = [
            "کد دریافت محتوا", "نحوه دریافت محتوا", "دیگر محصولات",
            "ربات تلگرامی همکار", "dayanpartnerbot", "dayanaff_pr",
            "dayan_video", "dayanaffiliate.com", "کدهای دریافت",
        ]
        if any(term in low for term in skip_terms):
            continue
        line = URL_RE.sub("", line)
        line = HANDLE_RE.sub("", line)
        line = re.sub(r"\s+", " ", line).strip(" \t|،;:")
        if line and not re.fullmatch(r"[\W_]+", line):
            cleaned.append(line)
    result = []
    for line in cleaned:
        if line not in result:
            result.append(line)
    return "\n".join(result).strip()

def valid_affiliate_url(url):
    if not isinstance(url, str):
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme == "https" and bool(parsed.netloc)

def resolve_product_code(item, links, overrides):
    override = overrides.get(str(item["source_message_id"]))
    if isinstance(override, dict):
        override = override.get("product_code")
    if override:
        code = str(override).strip()
        if code in links and valid_affiliate_url(links[code]):
            return code
        return None

    # Auto-link only when the source caption identifies exactly one product.
    # Posts listing several codes need a deliberate per-post choice.
    codes = item.get("product_codes", [])
    if len(codes) == 1:
        code = str(codes[0])
        if code in links and valid_affiliate_url(links[code]):
            return code
    return None

def build_caption(source_caption, affiliate_url):
    intro = clean_source_caption(source_caption)
    suffix = (
        "\n\n🛍 مشاهده و خرید:\n" + affiliate_url +
        "\n\nℹ️ این لینک همکاری در فروش است؛ ممکن است از خرید شما کمیسیون دریافت کنم."
    )
    max_intro = max(0, 1024 - len(suffix) - 2)
    if len(intro) > max_intro:
        intro = intro[:max_intro].rstrip() + "…"
    return (intro + suffix) if intro else suffix.lstrip()

def due_slot(now, published_slots):
    today = now.date().isoformat()
    for slot in PUBLISH_SLOTS:
        key = f"{today}|{slot}"
        if key in published_slots:
            continue
        hour, minute = map(int, slot.split(":"))
        slot_time = datetime.combine(now.date(), time(hour, minute), tzinfo=TIMEZONE)
        elapsed = (now - slot_time).total_seconds()
        if 0 <= elapsed <= SLOT_GRACE_MINUTES * 60:
            return key
    return None

async def main():
    api_id_text = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session = os.getenv("TELEGRAM_SESSION", "").strip()
    target_name = os.getenv("TARGET_CHANNEL", "").strip()

    if not all([api_id_text, api_hash, session, target_name]):
        print("Relay is not configured. Set TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION and TARGET_CHANNEL as Actions secrets.")
        sys.exit(2)

    api_id = int(api_id_text)
    state = read_json(STATE_FILE, {
        "initialized": False, "last_seen_id": 0, "queue": [],
        "published_slots": [], "sent_source_ids": []
    })
    links = read_json(LINKS_FILE, {})
    overrides = read_json(OVERRIDES_FILE, {})
    changed = False
    now = datetime.now(TIMEZONE)

    async with TelegramClient(StringSession(session), api_id, api_hash) as client:
        source = await client.get_entity(SOURCE_CHANNEL)
        target = await client.get_entity(target_name)

        latest = await client.get_messages(source, limit=1)
        latest_id = latest[0].id if latest else 0

        # Safe first run: establish a baseline and do not flood the destination
        # with old content. Only posts arriving after activation are considered.
        if not state.get("initialized"):
            state["initialized"] = True
            state["last_seen_id"] = latest_id
            write_state(state)
            print(f"Baseline established at source message {latest_id}; existing posts will not be republished.")
            return

        last_seen = int(state.get("last_seen_id", 0))
        queue = state.setdefault("queue", [])
        queued_ids = {int(item["source_message_id"]) for item in queue}
        sent_ids = {int(x) for x in state.get("sent_source_ids", [])}

        new_messages = []
        async for message in client.iter_messages(source, min_id=last_seen, reverse=True):
            if message.id > last_seen:
                new_messages.append(message)

        if new_messages:
            for message in new_messages:
                if message.id in queued_ids or message.id in sent_ids:
                    continue
                if not is_video_message(message):
                    continue
                caption = message.message or ""
                codes = extract_codes(caption)
                queue.append({
                    "source_message_id": int(message.id),
                    "source_date": message.date.isoformat() if message.date else None,
                    "source_caption": caption,
                    "product_codes": codes,
                    "status": "queued",
                })
                queued_ids.add(int(message.id))
                changed = True
                post_url = f"https://t.me/{SOURCE_CHANNEL}/{message.id}"
                print(f"Queued video: {post_url}; codes={codes or 'none (needs manual override)'}")
            new_last_seen = max([last_seen] + [int(m.id) for m in new_messages])
            if new_last_seen != last_seen:
                state["last_seen_id"] = new_last_seen
                changed = True
            if len(queue) > MAX_QUEUE_ITEMS:
                del queue[:-MAX_QUEUE_ITEMS]
                changed = True

        slot_key = due_slot(now, state.get("published_slots", []))
        if slot_key:
            chosen = None
            chosen_code = None
            for item in queue:
                code = resolve_product_code(item, links, overrides)
                if code:
                    chosen, chosen_code = item, code
                    break

            if chosen is not None:
                source_message = await client.get_messages(
                    source, ids=int(chosen["source_message_id"])
                )
                if source_message and is_video_message(source_message):
                    url = str(links[chosen_code]).strip()
                    caption = build_caption(source_message.message or chosen.get("source_caption", ""), url)
                    await client.send_file(
                        target,
                        source_message.media,
                        caption=caption,
                        parse_mode=None,
                        force_document=False,
                        supports_streaming=True,
                    )
                    queue.remove(chosen)
                    state.setdefault("sent_source_ids", []).append(int(chosen["source_message_id"]))
                    state["sent_source_ids"] = state["sent_source_ids"][-MAX_SENT_IDS:]
                    state.setdefault("published_slots", []).append(slot_key)
                    state["published_slots"] = state["published_slots"][-60:]
                    state["last_published_at"] = now.isoformat()
                    changed = True
                    print(f"Published source message {chosen['source_message_id']} using product code {chosen_code}.")
                else:
                    print(f"Skipped source message {chosen['source_message_id']}: source media is no longer available.")
            else:
                print(f"No link-ready video for slot {slot_key}. Queue remains unchanged.")

        if changed:
            write_state(state)
        else:
            print("No state changes; no commit is needed.")
        print(f"Queue size: {len(state.get('queue', []))}; last seen source id: {state.get('last_seen_id')}")

if __name__ == "__main__":
    asyncio.run(main())
