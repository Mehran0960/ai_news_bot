#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

BASE = "http://api.memarketbot.ir/api"
STATE = Path("memarket_radar/state.json")

USER = os.environ.get("MEMARKET_USERNAME", "").strip()
PASS = os.environ.get("MEMARKET_PASSWORD", "").strip()
AFF = os.environ.get("MEMARKET_AFFILIATE_CODE", "").strip()
BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

MIN_DISC = float(os.getenv("MIN_DISCOUNT", "30"))
DROP = float(os.getenv("PRICE_DROP_THRESHOLD", "8"))
LOW_STOCK = int(os.getenv("LOW_STOCK", "5"))
COOLDOWN = float(os.getenv("COOLDOWN_HOURS", "6")) * 3600
MAX_ALERTS = int(os.getenv("MAX_ALERTS", "3"))
PER_PAGE = int(os.getenv("PER_PAGE", "200"))
MAX_PAGES = int(os.getenv("MAX_PAGES", "50"))
BOOTSTRAP_SILENT = os.getenv("BOOTSTRAP_SILENT", "true").lower() == "true"


def fail_missing():
    missing = [
        k for k, v in {
            "MEMARKET_USERNAME": USER,
            "MEMARKET_PASSWORD": PASS,
            "MEMARKET_AFFILIATE_CODE": AFF,
            "TELEGRAM_BOT_TOKEN": BOT,
            "TELEGRAM_CHAT_ID": CHAT,
        }.items() if not v
    ]
    if missing:
        raise SystemExit("Missing GitHub Actions secrets: " + ", ".join(missing))


def _doh_ipv4(host, timeout=10):
    doh = f"https://dns.google/resolve?name={host}&type=A"
    req = Request(doh, headers={"User-Agent": "MeMarketDealRadar/1.0", "Accept": "application/dns-json"})
    with urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode("utf-8"))
    answers = payload.get("Answer", [])
    for item in answers:
        value = item.get("data", "")
        try:
            socket.inet_aton(value)
            return value
        except OSError:
            continue
    raise RuntimeError(f"DoH returned no IPv4 address for {host}: {payload.get('Status')}")


def request_json(url, params=None, data=None, timeout=30):
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    body = urlencode(data).encode() if data is not None else None
    headers = {
        "User-Agent": "MeMarketDealRadar/1.0",
        "Accept": "application/json,text/plain,*/*",
    }
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    req = Request(url, data=body, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8-sig", "replace")
        return json.loads(raw)
    except socket.gaierror:
        parsed = urlsplit(url)
        if parsed.hostname != "api.memarketbot.ir":
            raise
        ip = _doh_ipv4(parsed.hostname, timeout=10)
        resolved = urlunsplit((parsed.scheme, ip + (f":{parsed.port}" if parsed.port else ""), parsed.path, parsed.query, parsed.fragment))
        headers["Host"] = parsed.hostname
        print(f"DNS fallback: {parsed.hostname} -> {ip}")
        req = Request(resolved, data=body, headers=headers, method="POST" if data is not None else "GET")
        with urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8-sig", "replace")
        return json.loads(raw)


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def pick(obj, names):
    wanted = {x.lower() for x in names}
    for d in walk(obj):
        for k, v in d.items():
            if k.lower() in wanted and v not in (None, ""):
                return v
    return None


def as_num(v, default=0.0):
    try:
        s = str(v).replace(",", "").replace("٬", "").strip()
        return float(s)
    except Exception:
        return default


def goods_from_response(obj):
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for d in walk(obj):
            for k, v in d.items():
                if k.lower() in {"data", "goods", "items", "result", "rows", "products"} and isinstance(v, list):
                    return [x for x in v if isinstance(x, dict)]
    return []


def login():
    payload = request_json(f"{BASE}/users/Login", params={"u": USER, "p": PASS})
    token = pick(payload, {"token", "strToken", "access_token", "accessToken", "authToken", "jwt"})
    if isinstance(token, str) and token.strip():
        return token.strip().strip('"')
    if isinstance(payload, str) and payload.strip():
        return payload.strip().strip('"')
    raise RuntimeError(f"MeMarket token not found in login response: {str(payload)[:300]}")


def get_goods(token):
    all_goods = []
    for page in range(1, MAX_PAGES + 1):
        payload = request_json(
            f"{BASE}/goods/getAllGoods",
            params={"page": page, "perpage": PER_PAGE, "token": token},
        )
        goods = goods_from_response(payload)
        print(f"page={page} count={len(goods)}")
        if not goods:
            break
        all_goods.extend(goods)
        if len(goods) < PER_PAGE:
            break
    return all_goods


def normalize(raw):
    pid = pick(raw, {"numApiGoodRef", "numGoodRef", "id", "productId"})
    code = str(pick(raw, {"strGoodref", "goodRef", "code", "productCode"}) or pid or "").strip()
    name = str(pick(raw, {"strGoodName", "goodName", "name", "productName"}) or "").strip()
    regular = as_num(pick(raw, {"numGoodPrice", "regularPrice", "price"}))
    sale = as_num(pick(raw, {"numPriceWithDiscount", "discountPrice", "salePrice"}))
    stock = as_num(pick(raw, {"numStock", "stock", "quantity"}))
    images = str(pick(raw, {"strGoodImages", "images", "image"}) or "").strip()
    product_url = str(pick(raw, {"PostLink", "purchaseLink", "buyLink", "productUrl", "url"}) or "").strip()

    if not code or not name or regular <= 0 or sale <= 0 or sale >= regular or stock <= 0:
        return None

    discount = (regular - sale) * 100 / regular
    if discount < MIN_DISC:
        return None

    image = ""
    for part in images.replace(",", "^").split("^"):
        part = part.strip()
        if part.startswith(("http://", "https://")):
            image = part

    pid_num = int(as_num(pid)) if as_num(pid) > 0 else 0
    purchase = product_url
    if pid_num and AFF:
        purchase = f"https://memarket24.ir/product/{pid_num}?s={AFF}"

    if not purchase:
        return None

    return {
        "code": code,
        "name": name,
        "regular": int(regular),
        "sale": int(sale),
        "stock": int(stock),
        "discount": round(discount, 1),
        "image": image,
        "purchase": purchase,
    }


def evaluate(p, old):
    previous_sale = as_num(old.get("sale")) if old else 0
    drop = ((previous_sale - p["sale"]) / previous_sale * 100) if previous_sale > p["sale"] > 0 else 0

    score = 45 if p["discount"] >= 50 else 35 if p["discount"] >= 40 else 20
    reasons = [f"تخفیف {p['discount']:.0f}%"]

    if drop >= 15:
        score += 30
        reasons.append(f"افت قیمت {drop:.0f}%")
    elif drop >= DROP:
        score += 20
        reasons.append(f"افت قیمت {drop:.0f}%")

    if 0 < p["stock"] <= LOW_STOCK:
        score += 12
        reasons.append(f"موجودی {p['stock']}")

    now = time.time()
    last_alert_ts = as_num(old.get("last_alert_ts")) if old else 0
    last_alert_sale = as_num(old.get("last_alert_sale")) if old else 0
    cooldown_ok = now - last_alert_ts >= COOLDOWN
    materially_lower = (
        last_alert_sale > 0 and
        p["sale"] <= last_alert_sale * (1 - DROP / 100)
    )

    trigger = (
        p["discount"] >= 40
        or drop >= DROP
        or (p["discount"] >= MIN_DISC and p["stock"] <= LOW_STOCK)
    )
    qualifies = trigger and score >= 35 and (cooldown_ok or materially_lower)

    return score, reasons, drop, qualifies


def send_telegram(p, reasons, drop, score):
    name = html.escape(p["name"])
    caption = [
        "🔥 <b>آفر داغ می‌مارکت</b>",
        f"<b>{name}</b>",
        "",
        f"💰 <s>{p['regular']:,}</s> → <b>{p['sale']:,} ریال</b>",
        f"🏷 تخفیف: <b>{p['discount']:.0f}%</b>",
        "📌 " + " • ".join(html.escape(x) for x in reasons),
    ]

    if drop >= DROP:
        caption.append(f"📉 افت قیمت مشاهده‌شده: <b>{drop:.1f}%</b>")
    if 0 < p["stock"] <= LOW_STOCK:
        caption.append(f"⚠️ موجودی: <b>{p['stock']}</b>")

    caption += [
        "",
        "⚠️ درصد تخفیف بر اساس قیمت مرجع خود می‌مارکت است؛ مقایسه مستقل بازار نیست.",
        f'🛒 <a href="{html.escape(p["purchase"], quote=True)}">مشاهده / خرید</a>',
        f"⭐ امتیاز رادار: {score}",
    ]
    text = "\n".join(caption)

    if p["image"]:
        try:
            request_json(
                f"https://api.telegram.org/bot{BOT}/sendPhoto",
                data={"chat_id": CHAT, "photo": p["image"], "caption": text, "parse_mode": "HTML"},
            )
            return
        except Exception as exc:
            print(f"photo send failed; fallback to message: {exc}")

    request_json(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        data={"chat_id": CHAT, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "false"},
    )


def load_state():
    if not STATE.exists():
        return {"products": {}}
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("products"), dict):
            return data
    except Exception:
        pass
    return {"products": {}}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def commit_state():
    changed = subprocess.run(
        ["git", "status", "--porcelain", "--", str(STATE)],
        capture_output=True, text=True, check=True
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

    subprocess.run(
        ["git", "commit", "-m", "chore: update MeMarket radar state [skip ci]"],
        check=True,
    )
    subprocess.run(["git", "push"], check=True)


def main():
    fail_missing()

    state = load_state()
    products = state["products"]
    token = login()
    goods = get_goods(token)

    candidates = []
    now = time.time()

    for raw in goods:
        p = normalize(raw)
        if not p:
            continue

        old = products.get(p["code"])
        score, reasons, drop, qualifies = evaluate(p, old)

        # First scan is state-building only: no spam on bootstrap.
        if BOOTSTRAP_SILENT and old is None:
            qualifies = False

        if qualifies:
            candidates.append((score, p, reasons, drop))

        previous = products.get(p["code"], {})
        products[p["code"]] = {
            "regular": p["regular"],
            "sale": p["sale"],
            "discount": p["discount"],
            "last_alert_ts": previous.get("last_alert_ts", 0),
            "last_alert_sale": previous.get("last_alert_sale", 0),
            "last_seen_ts": now,
        }

    candidates.sort(
        key=lambda item: (item[0], item[1]["discount"], -item[1]["sale"]),
        reverse=True,
    )

    sent = 0
    for score, p, reasons, drop in candidates[:MAX_ALERTS]:
        try:
            send_telegram(p, reasons, drop, score)
            products[p["code"]]["last_alert_ts"] = now
            products[p["code"]]["last_alert_sale"] = p["sale"]
            sent += 1
            time.sleep(0.5)
        except Exception as exc:
            print(f"telegram failed code={p['code']}: {exc}", file=sys.stderr)

    save_state(state)
    commit_state()
    print(f"goods={len(goods)} qualifying={len(candidates)} alerts_sent={sent}")


if __name__ == "__main__":
    main()
