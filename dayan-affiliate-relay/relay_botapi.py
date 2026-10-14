import json
import os
import re
import sys
from datetime import datetime, time
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
STATE_FILE = ROOT / "state.json"
LINKS_FILE = CONFIG / "affiliate_links.json"
OVERRIDES_FILE = CONFIG / "post_overrides.json"

SOURCE_CHANNEL = "Dayan_video"
TARGET_CHANNEL = "@Iran_gajet"
SOURCE_URL = f"https://t.me/s/{SOURCE_CHANNEL}"
TIMEZONE = ZoneInfo("Asia/Tehran")
PUBLISH_SLOTS = ["09:00", "11:00", "13:00", "15:00", "17:00", "19:00", "20:30", "22:00"]
SLOT_GRACE_MINUTES = 55
MAX_QUEUE_ITEMS = 500
MAX_SENT_IDS = 2000
HTTP_TIMEOUT = 25

DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
CODE_RE = re.compile(r"(?<!\d)(\d{4,8})(?!\d)")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
HANDLE_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_]{4,}")
SKIP_LINE_TERMS = [
    "کد دریافت محتوا", "نحوه دریافت محتوا", "دیگر محصولات",
    "ربات تلگرامی همکار", "dayanpartnerbot", "dayanaff_pr",
    "dayan_video", "dayanaffiliate.com", "کدهای دریافت",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; DayanAffiliateRelay/1.0; +https://github.com/Mehran0960/ai_news_bot)"
})

def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc

def write_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def normalize_digits(text):
    return (text or "").translate(DIGIT_TRANSLATION)

def extract_codes(caption):
    found = []
    for value in CODE_RE.findall(normalize_digits(caption)):
        if 1300 <= int(value) <= 1499:
            continue
        if value not in found:
            found.append(value)
    return found

def clean_caption(text):
    lines = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        low = line.lower()
        if any(term in low for term in SKIP_LINE_TERMS):
            continue
        line = URL_RE.sub("", line)
        line = HANDLE_RE.sub("", line)
        line = re.sub(r"\s+", " ", line).strip(" \t|،;:")
        if line and line not in lines:
            lines.append(line)
    return "\n".join(lines).strip()

def video_url_from_node(node):
    # Accept only explicit video sources, never a poster/thumbnail image.
    selectors = [
        "video.tgme_widget_message_video[src]",
        ".tgme_widget_message_video[src]",
        ".js-video-player video[src]",
        ".tgme_widget_message_video_player video[src]",
    ]
    for selector in selectors:
        element = node.select_one(selector)
        if element:
            url = (element.get("src") or "").strip()
            if urlparse(url).scheme in ("http", "https"):
                return url
    for element in node.select("[data-video]"):
        url = (element.get("data-video") or "").strip()
        if urlparse(url).scheme in ("http", "https") and any(x in url.lower() for x in (".mp4", "video")):
            return url
    return None

def parse_preview(html):
    soup = BeautifulSoup(html, "html.parser")
    parsed = []
    seen = set()
    for node in soup.select(".tgme_widget_message"):
        post_ref = node.get("data-post")
        if not post_ref:
            parent = node.find_parent(attrs={"data-post": True})
            post_ref = parent.get("data-post") if parent else None
        if not post_ref:
            for parent in node.parents:
                post_ref = parent.get("data-post")
                if post_ref:
                    break
        if not post_ref or "/" not in post_ref:
            continue
        try:
            _, raw_id = post_ref.rsplit("/", 1)
            message_id = int(raw_id)
        except (ValueError, TypeError):
            continue
        if message_id in seen:
            continue
        seen.add(message_id)

        text_node = node.select_one(".tgme_widget_message_text")
        caption = text_node.get_text("\n", strip=True) if text_node else ""
        video_url = video_url_from_node(node)
        time_node = node.select_one(".tgme_widget_message_date time[datetime]")
        parsed.append({
            "source_message_id": message_id,
            "source_url": f"https://t.me/{SOURCE_CHANNEL}/{message_id}",
            "source_caption": caption,
            "product_codes": extract_codes(caption),
            "video_url": video_url,
            "source_date": time_node.get("datetime") if time_node else None,
        })
    return sorted(parsed, key=lambda item: item["source_message_id"])

def fetch_preview(before_id=None):
    url = SOURCE_URL
    if before_id is not None:
        url += f"?before={int(before_id)}"
    response = SESSION.get(url, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    if "tgme_widget_message" not in response.text:
        raise RuntimeError("Telegram preview did not contain expected public-channel message markup.")
    return parse_preview(response.text)

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
        return code if code in links and valid_affiliate_url(links[code]) else None
    codes = [str(code) for code in item.get("product_codes", [])]
    mapped = [code for code in codes if code in links and valid_affiliate_url(links[code])]
    return mapped[0] if len(mapped) == 1 else None

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

def build_caption(source_caption, affiliate_url):
    intro = clean_caption(source_caption)
    tail = "\n\n🛍 مشاهده و خرید:\n" + affiliate_url + "\n\nℹ️ لینک همکاری در فروش است؛ ممکن است از خرید شما کمیسیون دریافت کنم."
    if len(intro) + len(tail) > 1024:
        intro = intro[:max(0, 1020 - len(tail))].rstrip() + "…"
    return (intro + tail) if intro else tail.lstrip()

def send_video(bot_token, item, affiliate_url):
    fresh = None
    try:
        current = fetch_preview()
        fresh = next((p for p in current if p["source_message_id"] == item["source_message_id"]), None)
    except Exception as exc:
        print(f"Current preview refresh failed: {type(exc).__name__}: {exc}")

    if fresh is None:
        try:
            older = fetch_preview(before_id=item["source_message_id"] + 1)
            fresh = next((p for p in older if p["source_message_id"] == item["source_message_id"]), None)
        except Exception as exc:
            print(f"Historical preview refresh failed: {type(exc).__name__}: {exc}")

    media_url = fresh.get("video_url") if fresh else item.get("video_url")
    if not media_url or urlparse(media_url).scheme not in ("http", "https"):
        raise RuntimeError("Could not resolve a direct video URL for this source post.")

    caption = build_caption(item.get("source_caption", ""), affiliate_url)
    payload = {
        "chat_id": TARGET_CHANNEL,
        "video": media_url,
        "caption": caption,
        "supports_streaming": True,
        "reply_markup": json.dumps({
            "inline_keyboard": [[{"text": "🛍 مشاهده و خرید", "url": affiliate_url}]]
        }, ensure_ascii=False),
    }
    response = SESSION.post(
        f"https://api.telegram.org/bot{bot_token}/sendVideo",
        data=payload,
        timeout=60,
    )
    try:
        result = response.json()
    except ValueError:
        result = {"description": response.text[:300]}
    if response.status_code != 200 or not result.get("ok"):
        raise RuntimeError(f"Telegram sendVideo failed ({response.status_code}): {result.get('description', 'unknown error')}")
    return result["result"]["message_id"]

def main():
    if "--check" in sys.argv:
        posts = fetch_preview()
        video_posts = [item for item in posts if item.get("video_url")]
        print("Public Telegram preview diagnostic")
        print(f"Parsed channel messages: {len(posts)}")
        print(f"Messages with direct video source: {len(video_posts)}")
        print(f"Newest message ID in preview: {max((int(p['source_message_id']) for p in posts), default=0)}")
        print("Video message IDs and number of extracted product codes:")
        for item in video_posts[:20]:
            print(f"- {item['source_message_id']}: {len(item.get('product_codes', []))} product code(s)")
        if not video_posts:
            print("No direct video URLs were extracted. Do not activate auto-publishing until the parser is corrected.")
            sys.exit(3)
        return

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        print("Missing GitHub Actions secret TELEGRAM_BOT_TOKEN; workflow remains unconfigured.", file=sys.stderr)
        sys.exit(2)

    state = read_json(STATE_FILE, {
        "initialized": False, "last_seen_id": 0, "queue": [],
        "published_slots": [], "sent_source_ids": []
    })
    raw_link_map = os.getenv("AFFILIATE_LINKS_JSON", "").strip()
    links = json.loads(raw_link_map) if raw_link_map else read_json(LINKS_FILE, {})
    if not isinstance(links, dict):
        raise RuntimeError("AFFILIATE_LINKS_JSON must be a JSON object mapping product codes to personal affiliate URLs.")
    overrides = read_json(OVERRIDES_FILE, {})
    now = datetime.now(TIMEZONE)
    posts = fetch_preview()
    if not posts:
        raise RuntimeError("No channel messages were parsed from the public Telegram preview.")

    latest_id = max(p["source_message_id"] for p in posts)
    if not state.get("initialized"):
        state["initialized"] = True
        state["last_seen_id"] = latest_id
        write_state(state)
        print(f"Baseline established at source message {latest_id}. Old posts will not be republished.")
        return

    last_seen = int(state.get("last_seen_id", 0))
    queue = state.setdefault("queue", [])
    queued_ids = {int(x["source_message_id"]) for x in queue}
    sent_ids = {int(x) for x in state.get("sent_source_ids", [])}
    new_ids = []

    for item in posts:
        mid = int(item["source_message_id"])
        if mid <= last_seen:
            continue
        new_ids.append(mid)
        if mid in queued_ids or mid in sent_ids:
            continue
        # Advance the polling cursor for all posts, but queue only actual videos.
        if not item.get("video_url"):
            continue
        queued_item = {
            "source_message_id": int(item["source_message_id"]),
            "source_url": item["source_url"],
            "source_caption": item["source_caption"],
            "product_codes": item["product_codes"],
            "source_date": item.get("source_date"),
            "status": "queued",
            "queued_at": now.isoformat(),
        }
        # Do not persist expiring CDN media URLs in this public repository.
        queue.append(queued_item)
        queued_ids.add(mid)

    if new_ids:
        state["last_seen_id"] = max([last_seen] + new_ids)
    if len(queue) > MAX_QUEUE_ITEMS:
        queue[:] = queue[-MAX_QUEUE_ITEMS:]

    slot_key = due_slot(now, state.get("published_slots", []))
    if slot_key:
        chosen = None
        chosen_code = None
        for item in queue:
            code = resolve_product_code(item, links, overrides)
            if code:
                chosen, chosen_code = item, code
                break
        if chosen:
            telegram_message_id = send_video(bot_token, chosen, str(links[chosen_code]).strip())
            queue.remove(chosen)
            state.setdefault("sent_source_ids", []).append(int(chosen["source_message_id"]))
            state["sent_source_ids"] = state["sent_source_ids"][-MAX_SENT_IDS:]
            state.setdefault("published_slots", []).append(slot_key)
            state["published_slots"] = state["published_slots"][-60:]
            state["last_published_at"] = now.isoformat()
            state["last_destination_message_id"] = str(telegram_message_id)
            print(f"Published source {chosen['source_message_id']} to {TARGET_CHANNEL} using affiliate code {chosen_code}.")
        else:
            print(f"No video with an unambiguous personal affiliate link for slot {slot_key}; nothing published.")

    write_state(state)
    print(f"Completed. Found {len(posts)} recent videos; queued={len(queue)}; newest source ID={state['last_seen_id']}")

if __name__ == "__main__":
    main()
