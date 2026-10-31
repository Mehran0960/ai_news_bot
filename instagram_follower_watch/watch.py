#!/usr/bin/env python3
"""Read-only monitor for publicly advertised Instagram follower-service limits.

This script never submits forms, follows accounts, logs in to Instagram,
solves CAPTCHAs, or places orders.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "state" / "manual_requests.json"
BERLIN = ZoneInfo("Europe/Berlin")

SERVICES = {
    "smm8": {
        "name": "SMM8",
        "url": "https://smm8.com/free-instagram-followers",
        "amount": 10,
        "cooldown": timedelta(minutes=30),
        "limit_note": "حدود ۴۸۰ فالوور در ۲۴ ساعت (حدود ۴۸ درخواست)",
        "profile_scope": "فاصلهٔ هر درخواست ۳۰ دقیقه اعلام شده؛ دامنهٔ دقیق محدودیت پروفایل/IP تفکیک نشده",
        "ip_scope": "اعلام نشده",
        "captcha_note": "در متن عمومی CAPTCHA ذکر نشده؛ تایمر ۳۰ دقیقه‌ای خود سایت لازم است",
        "amount_pattern": re.compile(r"10\s+(?:free\s+)?followers?\s+every\s+30\s+minutes", re.I),
        "no_password_pattern": re.compile(r"no\s+(?:instagram\s+)?password", re.I),
        "no_signup_pattern": re.compile(r"(?:no\s+account|no\s+login|needs?\s+no\s+account)", re.I),
    },
    "mefreesocial": {
        "name": "MeFreeSocial",
        "url": "https://mefreesocial.com/instagram/free-followers",
        "amount": 15,
        "cooldown": timedelta(hours=6),
        "limit_note": "یک بسته برای همان پروفایل در هر ۶ ساعت، حتی اگر درخواست‌کننده شخص دیگری باشد",
        "profile_scope": "محدودیت هر پروفایل صریحاً اعلام شده",
        "ip_scope": "اعلام نشده",
        "captcha_note": "Cloudflare security check / CAPTCHA انسانی لازم است",
        "amount_pattern": re.compile(r"15\s+followers?\s+(?:are\s+sent\s+to\s+it,\s*)?once\s+every\s+6\s+hours|15\s+followers?\s+every\s+6\s+hours", re.I),
        "no_password_pattern": re.compile(r"no\s+password", re.I),
        "no_signup_pattern": re.compile(r"(?:no\s+(?:account|sign.?up|registration)\s+(?:required|needed)|you\s+do\s+not\s+need\s+an\s+account)", re.I),
    },
}

class VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

def fetch_visible_text(url: str) -> tuple[int | None, str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ReadOnlyServiceMonitor/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            status = response.status
            final_url = response.geturl()
            raw = response.read(1_500_001)
            if len(raw) > 1_500_000:
                return status, final_url, ""
            html = raw.decode("utf-8", errors="replace")
            parser = VisibleText()
            parser.feed(html)
            return status, final_url, " ".join(parser.parts)
    except HTTPError as exc:
        return exc.code, url, ""
    except (URLError, TimeoutError, OSError) as exc:
        return None, url, f"FETCH_ERROR:{type(exc).__name__}"

def load_state() -> dict[str, list[str]]:
    if not STATE_FILE.exists():
        return {key: [] for key in SERVICES}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"فایل وضعیت قابل‌خواندن نیست: {exc}") from exc
    result: dict[str, list[str]] = {}
    for key in SERVICES:
        values = data.get(key, [])
        if not isinstance(values, list):
            raise RuntimeError(f"مقدار {key} باید آرایه باشد")
        result[key] = [str(value) for value in values]
    return result

def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp باید timezone یا پسوند Z داشته باشد")
    return parsed.astimezone(timezone.utc)

def calculate_next(service_id: str, timestamps: list[str], now: datetime) -> tuple[str, datetime | None]:
    if not timestamps:
        return "زمان آخرین درخواست دستی ثبت نشده؛ موعد دقیق قابل محاسبه نیست.", None

    events = sorted(parse_utc(item) for item in timestamps)
    latest = events[-1]
    service = SERVICES[service_id]
    next_at = latest + service["cooldown"]

    if service_id == "smm8":
        rolling = [event for event in events if now - event < timedelta(hours=24)]
        if len(rolling) >= 48:
            cap_reset = rolling[-48] + timedelta(hours=24)
            if cap_reset > next_at:
                next_at = cap_reset

    if next_at <= now:
        return "بازهٔ زمانی اسمی گذشته است؛ پذیرش واقعی را فقط تایمر/فرم خود سایت مشخص می‌کند.", next_at
    return "موعد اسمی بعدی بر اساس زمان ثبت‌شده؛ پذیرش واقعی هنوز باید در سایت بررسی شود.", next_at

def check_service(service_id: str) -> dict:
    service = SERVICES[service_id]
    status, final_url, text = fetch_visible_text(service["url"])
    normalized = " ".join(text.split())
    if status == 200:
        amount_ok = bool(service["amount_pattern"].search(normalized))
        password_ok = bool(service["no_password_pattern"].search(normalized))
        signup_ok = bool(service["no_signup_pattern"].search(normalized))
        if amount_ok and password_ok and signup_ok:
            verification = "تأیید متن صفحه"
        elif amount_ok and password_ok:
            verification = "تأیید جزئی؛ شرط بدون ثبت‌نام از متن صفحه کامل تأیید نشد"
        else:
            verification = "تأییدنشده؛ متن/سهمیه با ادعای ذخیره‌شده تطبیق کامل ندارد"
        blocked = any(word in normalized.lower() for word in ("captcha", "cloudflare check", "security check"))
        captcha = "در صفحه دیده شد" if blocked else service["captcha_note"]
        return {
            "status": verification,
            "http": status,
            "final_url": final_url,
            "captcha": captcha,
        }
    return {
        "status": f"تأییدنشده؛ پاسخ صفحه HTTP {status if status is not None else 'نامشخص'}",
        "http": status,
        "final_url": final_url,
        "captcha": "قابل بررسی نبود",
    }

def fmt_local(value: datetime | None) -> str:
    if value is None:
        return "نامشخص"
    return value.astimezone(BERLIN).strftime("%Y-%m-%d %H:%M:%S %Z")

def build_report() -> str:
    now = datetime.now(timezone.utc)
    state = load_state()
    lines = [
        "# گزارش پایش فقط‌خواندنی فالوور اینستاگرام",
        "",
        "- هدف: @Negin.firuzjaei_70",
        f"- آخرین بررسی: {fmt_local(now)} (زمان اجرای GitHub Actions؛ امکان تأخیر وجود دارد)",
        "- عملیات انجام‌شده: فقط خواندن صفحه‌های عمومی؛ هیچ فرم یا سفارش ارسال نشده است.",
        "",
    ]
    for service_id, service in SERVICES.items():
        check = check_service(service_id)
        next_text, next_at = calculate_next(service_id, state[service_id], now)
        lines += [
            f"## {service['name']}",
            f"- لینک: {service['url']}",
            f"- مقدار ادعایی: {service['amount']} فالوور در هر درخواست (ادعای سایت، نه تحویل تأییدشده)",
            f"- فاصلهٔ اعلام‌شده: {service['cooldown']}",
            f"- سقف/محدودیت پروفایل: {service['limit_note']}",
            f"- دامنهٔ پروفایل: {service['profile_scope']}",
            f"- محدودیت IP: {service['ip_scope']}",
            f"- CAPTCHA: {check['captcha']}",
            "- ایران: محدودیت کشوری در صفحهٔ عمومی اعلام نشده؛ دسترسی از IP ایران تأیید نشده است.",
            f"- وضعیت صفحه: **{check['status']}** (HTTP: {check['http']})",
            f"- موعد بعدی: {next_text}",
            f"- زمان محاسبه‌شده: {fmt_local(next_at)}",
            "",
        ]
    lines += [
        "## موارد خارج از چرخه",
        "- SocialFollow: ارسال ۱۰۰ فالوور را به دنبال‌کردن ۱۰ حساب و حفظ آن دنبال‌کردن‌ها مشروط می‌کند؛ اقدام تعاملی انجام نمی‌شود.",
        "- FameDude: استفادهٔ یک‌باره/محدودیت دستگاه گزارش شده؛ موعد دوره‌ای ندارد.",
        "- سرویس‌هایی که زمان‌بندی یا فرم عمومی‌شان قابل‌تأیید نیست، به‌عنوان آمادهٔ اقدام معرفی نمی‌شوند.",
        "",
        "## هشدار سیاست پلتفرم",
        "راهنمای جامعهٔ اینستاگرام جمع‌آوری مصنوعی فالوورها را منع می‌کند. این گزارش مجوز یا توصیهٔ استفاده از این سرویس‌ها نیست؛ چنین فعالیتی می‌تواند به حذف فالوورهای غیرواقعی یا محدودیت حساب منجر شود.",
    ]
    return "\n".join(lines) + "\n"

def record_request(service_id: str, timestamp: str) -> None:
    if service_id not in SERVICES:
        raise ValueError(f"سرویس ناشناخته: {service_id}")
    parsed = parse_utc(timestamp)
    state = load_state()
    normalized = parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
    if normalized not in state[service_id]:
        state[service_id].append(normalized)
        state[service_id].sort()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"زمان درخواست دستی {service_id} ثبت شد: {normalized}")

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.add_argument("--output", default="-")
    record = sub.add_parser("record")
    record.add_argument("service", choices=SERVICES.keys())
    record.add_argument("timestamp_utc")
    args = parser.parse_args()

    try:
        if args.command == "record":
            record_request(args.service, args.timestamp_utc)
            return 0
        report = build_report()
        if args.output == "-":
            sys.stdout.write(report)
        else:
            Path(args.output).write_text(report, encoding="utf-8")
            sys.stdout.write(f"گزارش ساخته شد: {args.output}\n")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
