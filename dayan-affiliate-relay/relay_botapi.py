import json
import os
import re
import sys
import tempfile
from datetime import datetime, time
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
STATE_FILE = ROOT / "state.json"
OVERRIDES_FILE = CONFIG / "post_overrides.json"

SOURCE_CHANNEL = "Dayan_video"
TARGET_CHANNEL = "@Iran_gajet"
SOURCE_URL = f"https://t.me/s/{SOURCE_CHANNEL}"
TIMEZONE = ZoneInfo("Asia/Tehran")
PUBLISH_SLOTS = ["09:00", "11:00", "13:00", "15:00", "17:00", "19:00", "20:30", "22:00"]
SLOT_GRACE_MINUTES = 55
MAX_QUEUE_ITEMS = 500
MAX_SENT_IDS = 2000
MAX_VIDEO_BYTES = 49 * 1024 * 1024
MAX_POLL_PAGES = 25
HTTP_TIMEOUT = 25

DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# Only extract codes explicitly labeled as a product code; do not mistake
# four-digit prices, model numbers, or sizes for product IDs.
CODE_RE = re.compile(r"(?:کد(?:\s+محصول)?|product\s*code)\s*[:#\-]?\s*(\d{4,8})", re.IGNORECASE)
PATH_CODE_RE = re.compile(r"/(lead|fastcart)/(\d{4,8})", re.IGNORECASE)
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

def extract_product_refs(caption):
    text = normalize_digits(caption)
    refs = []
    seen = set()
    route_codes = set()

    for route, code in PATH_CODE_RE.findall(text):
        route = route.lower()
        route_codes.add(code)
        key = (route, code)
        if key not in seen:
            refs.append({"route": route, "code": code})
            seen.add(key)

    for code in CODE_RE.findall(text):
        if code in route_codes:
            continue
        key = ("fastcart", code)
        if key not in seen:
            refs.append({"route": "fastcart", "code": code})
            seen.add(key)
    return refs

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
        if re.search(r"(?:آدرس|ادرس)\s*فروشگا\S*\s*/\s*(?:lead|fastcart)/\d+", line, re.IGNORECASE):
            continue
        line = HANDLE_RE.sub("", line)
        line = re.sub(r"\s+", " ", line).strip(" \t|،;:")
        if line and line not in lines:
            lines.append(line)
    return "\n".join(lines).strip()

def direct_video_url(element):
    for attr in ("src", "data-src", "data-video"):
        value = (element.get(attr) or "").strip()
        if urlparse(value).scheme in ("http", "https"):
            return value
    return None

def video_url_from_node(node):
    # Do not confuse a thumbnail/image with a playable video.
    selectors = [
        "video.tgme_widget_message_video",
        ".tgme_widget_message_video video",
        ".js-video-player video",
        ".tgme_widget_message_video_player video",
        "video[src]",
        "video[data-src]",
    ]
    for selector in selectors:
        element = node.select_one(selector)
        if element:
            url = direct_video_url(element)
            if url:
                return url

    for element in node.select("[data-video]"):
        url = direct_video_url(element)
        if url and any(part in url.lower() for part in (".mp4", "video", "stream")):
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
        media_url = video_url_from_node(node)
        time_node = node.select_one(".tgme_widget_message_date time[datetime]")
        parsed.append({
            "source_message_id": message_id,
            "source_url": f"https://t.me/{SOURCE_CHANNEL}/{message_id}",
            "source_caption": caption,
            "product_refs": extract_product_refs(caption),
            "video_url": media_url,
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

def normalize_store_host(value):
    raw = (value or "").strip()
    if not raw:
        raise RuntimeError("Missing DAYAN_STORE_HOST secret. Add your personal Dayan store host from your affiliate panel.")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    supported = host.endswith(".affdn.ir") or host.endswith(".affdn.com")
    if parsed.scheme != "https" or not supported or host in ("affdn.ir", "affdn.com"):
        raise RuntimeError("DAYAN_STORE_HOST must be your personal HTTPS subdomain ending in .affdn.ir or .affdn.com.")
    if parsed.username or parsed.password or parsed.port or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise RuntimeError("DAYAN_STORE_HOST must contain only your personal hostname, without credentials, a path, query, or port.")
    return f"https://{host}"

def make_affiliate_url(store_base, product_ref):
    if isinstance(product_ref, str):
        product_ref = {"route": "fastcart", "code": product_ref}
    route = str(product_ref.get("route", "fastcart")).lower()
    code = str(product_ref.get("code", "")).strip()
    if route not in ("fastcart", "lead") or not re.fullmatch(r"\d{4,8}", code):
        raise RuntimeError("Refusing to create an affiliate URL from an invalid route or product code.")
    return f"{store_base}/{route}/{code}"

def resolve_product_ref(item, overrides):
    override = overrides.get(str(item["source_message_id"]))
    if isinstance(override, dict):
        code = str(override.get("product_code", override.get("code", ""))).strip()
        route = str(override.get("route", "fastcart")).strip().lower()
        if route in ("fastcart", "lead") and re.fullmatch(r"\d{4,8}", code):
            return {"route": route, "code": code}
        return None
    if override:
        code = str(override).strip()
        if re.fullmatch(r"\d{4,8}", code):
            matches = [ref for ref in item.get("product_refs", []) if str(ref.get("code")) == code]
            if len(matches) == 1:
                return matches[0]
            if not matches:
                return {"route": "fastcart", "code": code}
        return None
    refs = item.get("product_refs", [])
    unique = {(str(ref.get("route", "fastcart")).lower(), str(ref.get("code", ""))) for ref in refs}
    if len(unique) != 1:
        return None
    route, code = next(iter(unique))
    if route not in ("fastcart", "lead") or not re.fullmatch(r"\d{4,8}", code):
        return None
    return {"route": route, "code": code}

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

def refresh_video_url(source_message_id):
    # Telegram CDN URLs may expire; fetch current public preview near publication.
    try:
        current = fetch_preview()
        fresh = next((p for p in current if p["source_message_id"] == source_message_id), None)
    except Exception as exc:
        print(f"Current preview refresh failed: {type(exc).__name__}: {exc}")
        fresh = None

    if fresh is None:
        try:
            older = fetch_preview(before_id=source_message_id + 1)
            fresh = next((p for p in older if p["source_message_id"] == source_message_id), None)
        except Exception as exc:
            print(f"Historical preview refresh failed: {type(exc).__name__}: {exc}")

    media_url = fresh.get("video_url") if fresh else None
    parsed = urlparse(media_url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "telesco.pe" or host.endswith(".telesco.pe")):
        raise RuntimeError("Refusing to download media from an unexpected host; only HTTPS Telegram telesco.pe media URLs are accepted.")
    return media_url

def send_video(bot_token, item, affiliate_url):
    media_url = refresh_video_url(int(item["source_message_id"]))
    caption = build_caption(item.get("source_caption", ""), affiliate_url)
    payload = {
        "chat_id": TARGET_CHANNEL,
        "caption": caption,
        "supports_streaming": "true",
        "reply_markup": json.dumps({
            "inline_keyboard": [[{"text": "🛍 مشاهده و خرید", "url": affiliate_url}]]
        }, ensure_ascii=False),
    }

    # Download to a temporary file, then upload through Bot API. This avoids
    # depending on Telegram's URL-fetch size/format limitations and never saves
    # the expiring CDN URL in the repository.
    temp_path = None
    try:
        with SESSION.get(media_url, stream=True, timeout=(15, 120)) as media_response:
            media_response.raise_for_status()
            content_type = (media_response.headers.get("Content-Type") or "").lower()
            if "video" not in content_type and "octet-stream" not in content_type:
                raise RuntimeError(f"Source media is not a recognized video (Content-Type={content_type or 'missing'}).")
            length_header = media_response.headers.get("Content-Length")
            if length_header and int(length_header) > MAX_VIDEO_BYTES:
                raise RuntimeError(f"Video exceeds the configured upload limit of {MAX_VIDEO_BYTES // (1024 * 1024)} MiB.")
            total = 0
            with tempfile.NamedTemporaryFile(prefix="dayan-", suffix=".mp4", delete=False) as temp_file:
                temp_path = temp_file.name
                for chunk in media_response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_VIDEO_BYTES:
                        raise RuntimeError(f"Video exceeds the configured upload limit of {MAX_VIDEO_BYTES // (1024 * 1024)} MiB.")
                    temp_file.write(chunk)
        if not temp_path or os.path.getsize(temp_path) < 1024:
            raise RuntimeError("Downloaded video is empty or unexpectedly small; refusing to publish.")
        with open(temp_path, "rb") as media_file:
            files = {"video": (f"dayan-{item['source_message_id']}.mp4", media_file, "video/mp4")}
            response = SESSION.post(
                f"https://api.telegram.org/bot{bot_token}/sendVideo",
                data=payload,
                files=files,
                timeout=(20, 180),
            )
        try:
            result = response.json()
        except ValueError:
            result = {"description": response.text[:300]}
        if response.status_code != 200 or not result.get("ok"):
            raise RuntimeError(f"Telegram sendVideo failed ({response.status_code}): {result.get('description', 'unknown error')}")
        return result["result"]["message_id"]
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

def fetch_posts_since(last_seen_id, max_pages=MAX_POLL_PAGES):
    """Fetch all preview pages newer than the cursor, up to a safe page cap."""
    first_page = fetch_preview()
    collected = {int(item["source_message_id"]): item for item in first_page}
    if last_seen_id is None or not first_page:
        return sorted(collected.values(), key=lambda item: item["source_message_id"])

    page = first_page
    pages = 1
    while page and pages < max_pages:
        oldest_id = min(int(item["source_message_id"]) for item in page)
        if oldest_id <= int(last_seen_id):
            break
        next_page = fetch_preview(before_id=oldest_id)
        new_items = []
        for item in next_page:
            item_id = int(item["source_message_id"])
            if item_id not in collected:
                collected[item_id] = item
                new_items.append(item)
        if not new_items:
            break
        page = next_page
        pages += 1
    if pages >= max_pages:
        print(f"Warning: reached MAX_POLL_PAGES={max_pages}; unusually high source volume may require a larger page cap.")
    return sorted(collected.values(), key=lambda item: item["source_message_id"])


def main():
    if "--check" in sys.argv:
        posts = fetch_posts_since(None)
        video_posts = [item for item in posts if item.get("video_url")]
        latest = max(posts, key=lambda item: int(item["source_message_id"])) if posts else None
        print("Public Telegram preview diagnostic — no publishing occurs.")
        print(f"Parsed channel messages in current preview: {len(posts)}")
        print(f"Messages with direct video sources: {len(video_posts)}")
        if latest:
            print(f"Newest source post: {latest['source_url']}")
            print(f"Newest source post date: {latest.get('source_date') or 'not exposed'}")
        print("Recent source entries (newest first):")
        for item in list(reversed(posts))[:20]:
            snippet = re.sub(r"\s+", " ", item.get("source_caption", "")).strip()[:110]
            media_type = "video-url" if item.get("video_url") else "no-video-url"
            print(f"- id={item['source_message_id']} date={item.get('source_date') or '?'} media={media_type} refs={item.get('product_refs', [])} caption={snippet!r}")
        if not video_posts:
            print("No direct video URLs were extracted from the current public preview.")
            sys.exit(3)
        for item in video_posts[:2]:
            try:
                media_response = SESSION.get(
                    item["video_url"], headers={"Range": "bytes=0-1"},
                    timeout=15, stream=True
                )
                print(
                    f"Media check id={item['source_message_id']}: "
                    f"HTTP {media_response.status_code}; "
                    f"type={media_response.headers.get('Content-Type', 'unknown')}; "
                    f"length={media_response.headers.get('Content-Length', 'unknown')}"
                )
                media_response.close()
            except requests.RequestException as exc:
                print(f"Media check id={item['source_message_id']} failed: {type(exc).__name__}")
        return

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    store_base = normalize_store_host(os.getenv("DAYAN_STORE_HOST", ""))
    if not bot_token:
        print("Missing GitHub Actions secret TELEGRAM_BOT_TOKEN.", file=sys.stderr)
        sys.exit(2)

    state = read_json(STATE_FILE, {
        "initialized": False, "last_seen_id": 0, "queue": [],
        "published_slots": [], "sent_source_ids": []
    })
    overrides = read_json(OVERRIDES_FILE, {})
    now = datetime.now(TIMEZONE)
    posts = fetch_posts_since(int(state.get("last_seen_id", 0)) if state.get("initialized") else None)
    if not posts:
        raise RuntimeError("No channel messages were parsed from the public Telegram preview.")

    latest_id = max(int(p["source_message_id"]) for p in posts)
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
        if mid in queued_ids or mid in sent_ids or not item.get("video_url"):
            continue
        item["status"] = "queued"
        item["queued_at"] = now.isoformat()
        # Do not persist expiring media URLs or affiliate URLs in the public repo.
        item.pop("video_url", None)
        queue.append(item)
        queued_ids.add(mid)

    if new_ids:
        state["last_seen_id"] = max([last_seen] + new_ids)
    if len(queue) > MAX_QUEUE_ITEMS:
        queue[:] = queue[-MAX_QUEUE_ITEMS:]

    slot_key = due_slot(now, state.get("published_slots", []))
    if slot_key:
        chosen = None
        chosen_ref = None
        for item in queue:
            product_ref = resolve_product_ref(item, overrides)
            if product_ref:
                chosen, chosen_ref = item, product_ref
                break
        if chosen:
            affiliate_url = make_affiliate_url(store_base, chosen_ref)
            telegram_message_id = send_video(bot_token, chosen, affiliate_url)
            queue.remove(chosen)
            state.setdefault("sent_source_ids", []).append(int(chosen["source_message_id"]))
            state["sent_source_ids"] = state["sent_source_ids"][-MAX_SENT_IDS:]
            state.setdefault("published_slots", []).append(slot_key)
            state["published_slots"] = state["published_slots"][-60:]
            state["last_published_at"] = now.isoformat()
            state["last_destination_message_id"] = str(telegram_message_id)
            print(f"Published source {chosen['source_message_id']} to {TARGET_CHANNEL} with {chosen_ref['route']} code {chosen_ref['code']}.")
        else:
            print(f"No new video with one unambiguous product route/code for slot {slot_key}; nothing published.")

    write_state(state)
    write_state(state)
    print(f"Completed. Parsed {len(posts)} source messages; queued={len(queue)}; newest source ID={state['last_seen_id']}")

if __name__ == "__main__":
    main()
