import os
import sys
from urllib.parse import urlparse

import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
STORE_HOST = os.getenv("DAYAN_STORE_HOST", "").strip()
TARGET = "@Iran_gajet"
TIMEOUT = 20

def validate_store_host(value):
    if not value:
        print("DAYAN_STORE_HOST: MISSING")
        return False
    raw = value if "://" in value else "https://" + value
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    accepted = (
        parsed.scheme == "https"
        and (host.endswith(".affdn.ir") or host.endswith(".affdn.com"))
        and host not in ("affdn.ir", "affdn.com")
        and not parsed.username
        and not parsed.password
        and not parsed.port
        and parsed.path in ("", "/")
        and not parsed.query
        and not parsed.fragment
    )
    print("DAYAN_STORE_HOST: OK" if accepted else "DAYAN_STORE_HOST: INVALID — use only your personal subdomain ending .affdn.ir or .affdn.com")
    return accepted

def api(method, **params):
    response = requests.get(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        params=params,
        timeout=TIMEOUT,
    )
    try:
        body = response.json()
    except ValueError:
        body = {}
    return response.status_code, body

def main():
    store_ok = validate_store_host(STORE_HOST)
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN: MISSING")
        print("No Telegram API request was made.")
        sys.exit(2)

    status, body = api("getMe")
    if status != 200 or not body.get("ok"):
        print("TELEGRAM_BOT_TOKEN: INVALID_OR_UNAVAILABLE")
        sys.exit(3)

    bot = body.get("result", {})
    bot_id = bot.get("id")
    username = bot.get("username", "(no username)")
    print(f"TELEGRAM_BOT_TOKEN: OK (bot @{username}; token value hidden)")

    status, body = api("getChat", chat_id=TARGET)
    if status != 200 or not body.get("ok"):
        print("TARGET_CHANNEL: BOT_CANNOT_READ_CHANNEL — ensure the same bot is an administrator of @Iran_gajet")
        sys.exit(4)
    print("TARGET_CHANNEL: OK (@Iran_gajet is reachable)")

    status, body = api("getChatMember", chat_id=TARGET, user_id=bot_id)
    if status != 200 or not body.get("ok"):
        print("BOT_ADMIN_STATUS: UNVERIFIED")
        sys.exit(5)

    member = body.get("result", {})
    role = member.get("status", "unknown")
    can_post = member.get("can_post_messages")
    if role not in ("administrator", "creator") or can_post is False:
        print(f"BOT_ADMIN_STATUS: NOT_READY (role={role}; can_post_messages={can_post})")
        sys.exit(6)
    print(f"BOT_ADMIN_STATUS: OK (role={role}; can_post_messages={can_post})")

    if not store_ok:
        print("RESULT: Telegram is ready, but the personal Dayan store hostname must be corrected before activation.")
        sys.exit(7)
    print("RESULT: Configuration checks passed. No message was sent to the channel.")

if __name__ == "__main__":
    main()
