#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError

CHANNEL = os.getenv("MEMARKET_CHANNEL", "memarket").strip()
CHANNEL_URL = f"https://t.me/s/{CHANNEL}"
STATE = Path("memarket_radar/state.json")

AFF = os.getenv("MEMARKET_AFFILIATE_CODE", "").strip()
BOT = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()

MIN_PERCENT = float(os.getenv("MIN_DISCOUNT", "30"))
MAX_ALERTS = int(os.getenv("MAX_ALERTS", "3"))
COOLDOWN = float(os.getenv("COOLDOWN_HOURS", "6")) * 3600
BOOTSTRAP_SILENT = os.getenv("BOOTSTRAP_SILENT", "true").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
STATE_COMMIT = os.getenv("STATE_COMMIT", "true").lower() == "true"
MAX_SEEN = int(os.getenv("MAX_SEEN_POSTS", "500"))

if not DRY_RUN:
    for n, v in {
        "MEMARKET_AFFILIATE_CODE": AFF,
        "TELEGRAM_BOT_TOKEN": BOT,
        "TELEGRAM_CHAT_ID": CHAT,
    }.items():
        if not v:
            raise SystemExit(f"Missing required secret: {n}")


def fetch(url, timeout=30):
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 MeMarketDealRadar/2.0",
            "Accept": "text/html,application/xhtml+xml,*/*",
        },
    )
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def fa_to_en(s: str) -> str:
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٬٫", "0123456789,.")
    return s.translate(table)


def clean_text(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment)
    fragment = re.sub(r"[ \t]+", " ", fragment)
    fragment = re.sub(r"\n[ \t]+", "\n", fragment)
    return fragment.strip()


def extract_posts(page: str):
    posts = []

    # Telegram's public HTML is intentionally kept simple here: find every
    # message wrapper and then extract its visible text/links from inside.
    wrapper_re = re.compile(
        r'<div[^>]+data-post="([^"]+)"[^>]*>(.*?)(?=<div[^>]+data-post="[^"]+"[^>]*>|</main>|\Z)',
        re.S | re.I,
    )

    for m in wrapper_re.finditer(page):
        post_key, block = m.group(1), m.group(2)

        tm = re.search(
            r'<div[^>]+class="[^"]*tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            block,
            re.S | re.I,
        )
        if not tm:
            continue

        text_value = clean_text(tm.group(1))
        links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', tm.group(1), re.I)
        links += re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', block, re.I)

        images = re.findall(
            r'<img[^>]+src=["\'](https?://[^"\']+)["\']',
            block,
            re.I,
        )

        post_id = post_key.rsplit("/", 1)[-1]
        posts.append({
            "id": post_id,
            "key": post_key,
            "url": f"https://t.me/{post_key}",
            "text": text_value,
            "links": list(dict.fromkeys(links)),
            "image": images[0] if images else "",
        })

    return posts


def affiliate_link(url: str) -> str:
    try:
        p = urlsplit(url)
    except Exception:
        return ""

    host = (p.hostname or "").lower()

    # MeMarket has announced that memarketshop/mmkt domains are retired.
    # Never send buyers to that legacy domain, including custom subdomains.
    if host == "memarketshop.ir" or host.endswith(".memarketshop.ir") or host == "mmkt.ir" or host.endswith(".mmkt.ir"):
        return ""

    is_memarket24 = host == "memarket24.ir" or host.endswith(".memarket24.ir")
    is_shortlink = host == "l.memarket.me"
    if not (is_memarket24 or is_shortlink):
        return ""

    # Current MeMarket short links encode the affiliate code in /lp/{id}/{code}.
    parts = [x for x in p.path.split("/") if x]
    if is_shortlink and len(parts) >= 3 and parts[-1].isdigit():
        parts[-1] = AFF
        return urlunsplit((p.scheme, p.netloc, "/" + "/".join(parts), p.query, p.fragment))

    # Replace an existing seller-code path segment such as /landing/foo/4116.
    if "landing" in [x.lower() for x in parts] and parts:
        if parts[-1].isdigit():
            parts[-1] = AFF
            return urlunsplit((p.scheme, p.netloc, "/" + "/".join(parts), p.query, p.fragment))
        return urlunsplit((p.scheme, p.netloc, p.path.rstrip("/") + "/" + AFF, p.query, p.fragment))

    # Replace an existing ?s=code / &s=code, otherwise append it.
    query = parse_qsl(p.query, keep_blank_values=True)
    replaced = False
    new_query = []
    for k, v in query:
        if k.lower() == "s":
            new_query.append((k, AFF))
            replaced = True
        else:
            new_query.append((k, v))
    if not replaced:
        new_query.append(("s", AFF))

    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(new_query), p.fragment))


def extract_percent(text: str):
    nums = []
    for m in re.finditer(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:٪|%)", fa_to_en(text)):
        try:
            nums.append(float(m.group(1).replace(",", "")))
        except Exception:
            pass
    return max(nums) if nums else 0.0


MARKETER_ONLY_PATTERNS = [
    ("وبمستر/بازاریاب", r"وب\s*مستر|بازاریاب"),
    ("پورسانت یا کمیسیون همکاران", r"پورسانت|کمیسیون"),
    ("تارگت فروش همکاران", r"تارگت"),
    ("جذب یا ثبت‌نام همکار", r"جذب.{0,20}(?:همکار|بازاریاب)|ثبت\s*نام.{0,25}(?:همکاری|بازاریاب)"),
    ("پیام مخصوص همکاران", r"همکاران\s+(?:عزیز|محترم)|بات\s+همکار"),
    ("تبلیغ و جذب سفارش", r"تبلیغ\s+کن(?:ی)?\s+و\s+سفارش\s+بگیر|مخاطبات|مشتریهات"),
    ("دریافت محتوای تبلیغاتی", r"دریافت\s+کاور|کاور\s+تبلیغی|ویدئوی?\s+هر\s+محصول"),
    ("اطلاعیه پنل یا تسویه همکاران", r"پشتیبان\s+اختصاصی|شماره\s+شبای?\s+خود|تغییر\s+آدرس.{0,20}پنل"),
    ("پاداش وابسته به عملکرد فروش", r"(?:پاداش|جایزه).{0,50}(?:فروش|همکار|سفارش)|(?:فروش|همکار|سفارش).{0,50}(?:پاداش|جایزه)"),
    ("دعوت به کسب درآمد", r"اولین\s+درآمد|درآمد\s+آنلاین|کسب\s+درآمد"),
]


def marketing_only_reason(text: str) -> str:
    normalized = text.replace("ي", "ی").replace("ك", "ک")
    normalized = re.sub(r"[\u200c\u200d]", " ", normalized)
    for reason, pattern in MARKETER_ONLY_PATTERNS:
        if re.search(pattern, normalized, flags=re.I):
            return reason
    return ""


def score_post(post):
    text_value = post["text"]
    low = text_value.lower()
    percent = extract_percent(text_value)

    aff_links = []
    for u in post["links"]:
        x = affiliate_link(u)
        if x:
            aff_links.append(x)
    aff_links = list(dict.fromkeys(aff_links))

    # Do not send affiliate recruitment, commission, dashboard, or marketer-instruction
    # messages to the buyer-facing deal feed, even if they mention discounts or links.
    filtered_reason = marketing_only_reason(text_value)
    if filtered_reason:
        return {
            **post,
            "score": 0,
            "percent": percent,
            "reasons": [],
            "affiliate_links": aff_links,
            "qualifies": False,
            "filtered_reason": filtered_reason,
        }

    score = 0
    reasons = []

    if percent >= MIN_PERCENT:
        score += 4
        reasons.append(f"تخفیف {percent:.0f}%")
        if percent >= 50:
            score += 2
    elif any(k in low for k in ("تخفیف", "حراج", "آفر", "کاهش قیمت")):
        score += 2
        reasons.append("آفر/تخفیف")

    if any(k in low for k in ("فقط", "ویژه", "شگفت", "استثنایی", "پولساز")):
        score += 1

    if aff_links:
        score += 4

    # Qualification is now buyer-oriented: posts explicitly aimed at marketers
    # are removed before scoring, and a real offer/link is still required.
    deal_words = (
        "تخفیف", "حراج", "آفر", "کاهش قیمت", "قیمت ویژه",
        "کمپین", "فقط", "شگفت", "استثنایی"
    )
    qualifies = (
        score >= 7
        and bool(aff_links)  # An alert must have a verified, non-retired buyer link.
        and (percent >= MIN_PERCENT or any(k in low for k in deal_words))
        and any(k in low for k in deal_words)
    )

    return {
        **post,
        "score": score,
        "percent": percent,
        "reasons": reasons,
        "affiliate_links": aff_links,
        "qualifies": qualifies,
        "filtered_reason": "",
    }

def short_copy(post) -> str:
    text_value = post["text"]
    lines = [x.strip() for x in text_value.splitlines() if x.strip()]
    # Remove repetitive footer lines that do not help the buyer.
    filtered = []
    for line in lines:
        low = line.lower()
        if any(x in low for x in ("@memarket", "@shop_memarketbiz", "@memarket_content", "@memarketcobot", "@sup_memarket")):
            continue
        filtered.append(line)

    body = "\n".join(filtered)
    body = body[:650].strip()
    return body


def telegram_request(method: str, data: dict):
    url = f"https://api.telegram.org/bot{BOT}/{method}"
    body = urlencode(data).encode()
    req = Request(
        url,
        data=body,
        headers={"User-Agent": "MeMarketDealRadar/2.0", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        raise RuntimeError(f"Telegram {method} HTTP {exc.code}: {detail[:700]}") from exc


def send_telegram(post):
    body = html.escape(short_copy(post))
    link = post["affiliate_links"][0]
    source = html.escape(post["url"], quote=True)

    parts = [
        "🔥 <b>آفر داغ می‌مارکت</b>",
        "",
        body,
        "",
    ]
    if post["reasons"]:
        parts.append("📌 " + " • ".join(html.escape(x) for x in post["reasons"]))
    parts += [
        "",
        f'🛒 <a href="{html.escape(link, quote=True)}">مشاهده / خرید با لینک همکاری</a>',
        f'🔗 <a href="{source}">منبع اصلی</a>',
    ]
    message = "\n".join(parts)

    if post.get("image"):
        try:
            return telegram_request(
                "sendPhoto",
                {"chat_id": CHAT, "photo": post["image"], "caption": message, "parse_mode": "HTML"},
            )
        except Exception as exc:
            print(f"photo_send_failed_fallback={exc}", file=sys.stderr)

    return telegram_request(
        "sendMessage",
        {"chat_id": CHAT, "text": message, "parse_mode": "HTML", "disable_web_page_preview": "false"},
    )


def load_state():
    if not STATE.exists():
        return {"seen": [], "alerts": {}}
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("seen", [])
            data.setdefault("alerts", {})
            return data
    except Exception:
        pass
    return {"seen": [], "alerts": {}}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def commit_state():
    if not STATE_COMMIT or DRY_RUN:
        return

    changed = subprocess.run(
        ["git", "status", "--porcelain", "--", str(STATE)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not changed:
        return

    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(
        ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
        check=True,
    )
    subprocess.run(["git", "add", str(STATE)], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        return
    subprocess.run(["git", "commit", "-m", "chore: update MeMarket radar state [skip ci]"], check=True)
    subprocess.run(["git", "push"], check=True)


def main():
    state = load_state()
    page = fetch(CHANNEL_URL)
    posts = extract_posts(page)
    if not posts:
        raise SystemExit("No Telegram channel posts parsed.")

    print(f"channel={CHANNEL} posts={len(posts)}")

    seen = set(str(x) for x in state.get("seen", []))
    new_posts = [p for p in posts if p["id"] not in seen]
    print(f"new_posts={len(new_posts)}")

    scored_posts = [score_post(p) for p in new_posts]
    for p in scored_posts:
        if p.get("filtered_reason"):
            print(f"FILTERED_MARKETER_POST id={p['id']} reason={p['filtered_reason']}")
    candidates = [p for p in scored_posts if p["qualifies"]]
    candidates.sort(key=lambda p: (p["score"], p["percent"]), reverse=True)

    for p in candidates[:10]:
        print(
            f"CANDIDATE id={p['id']} score={p['score']} percent={p['percent']:.0f} "
            f"links={len(p['affiliate_links'])} reasons={' | '.join(p['reasons'])} "
            f"text={short_copy(p)[:450]!r}"
        )
        if p["affiliate_links"]:
            print("AFF_LINK", p["affiliate_links"][0])

    if not BOOTSTRAP_SILENT or seen:
        sent = 0
        now = time.time()
        for p in candidates:
            if sent >= MAX_ALERTS:
                break

            old = state["alerts"].get(p["id"], {})
            last_alert = float(old.get("ts", 0))
            if now - last_alert < COOLDOWN:
                continue

            if DRY_RUN:
                print(f"DRY_RUN would_send id={p['id']}")
            else:
                send_telegram(p)

            state["alerts"][p["id"]] = {"ts": now, "score": p["score"]}
            sent += 1

        print(f"alerts_sent={sent}")
    else:
        print("bootstrap=quiet")

    state["seen"] = list(dict.fromkeys([*state.get("seen", []), *[p["id"] for p in posts]]))[-MAX_SEEN:]
    save_state(state)
    commit_state()


if __name__ == "__main__":
    main()
