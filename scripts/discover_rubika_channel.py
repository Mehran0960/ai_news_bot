#!/usr/bin/env python3
"""Resolve the configured Rubika channel chat_id without sending messages."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

API_BASE = "https://botapi.rubika.ir/v3"
TIMEOUT_SECONDS = 25
UPDATE_LIMIT = 100


def normalize_username(value: Any) -> str:
    return str(value or "").strip().removeprefix("@").strip().lower()


def extract_chat_ids(updates: list[dict]) -> list[str]:
    """Extract distinct chat IDs from official Update objects without reading text."""
    seen: set[str] = set()
    result: list[str] = []
    for update in updates:
        if not isinstance(update, dict):
            continue
        chat_id = str(update.get("chat_id") or "").strip()
        if chat_id and chat_id not in seen:
            seen.add(chat_id)
            result.append(chat_id)
    return result


def is_target_channel(chat: dict, expected_username: str) -> bool:
    """Match only a channel, by username or exact title fallback."""
    if not isinstance(chat, dict):
        return False
    chat_type = str(chat.get("chat_type") or "").strip().lower()
    if chat_type and chat_type != "channel":
        return False
    expected = normalize_username(expected_username)
    username = normalize_username(chat.get("username"))
    title = normalize_username(chat.get("title"))
    return bool(expected and (username == expected or title == expected))


def _post(token: str, method: str, body: dict | None = None) -> dict:
    if not token:
        raise RuntimeError("RUBIKA_BOT_TOKEN is not configured")
    request = urllib.request.Request(
        f"{API_BASE}/{token}/{method}",
        data=json.dumps(body or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Rubika {method} HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        # Never include the URL or raw exception; the URL contains the bot token.
        raise RuntimeError(f"Rubika {method} request failed") from None

    if not isinstance(payload, dict):
        raise RuntimeError(f"Rubika {method} returned an invalid response")
    status = str(payload.get("status") or "").upper()
    if status not in {"OK", "SUCCESS"}:
        raise RuntimeError(f"Rubika {method} rejected the request (status={status or 'unknown'})")
    data = payload.get("data")
    if not isinstance(data, dict):
        data = payload.get("result")
    if not isinstance(data, dict):
        raise RuntimeError(f"Rubika {method} returned no data object")
    return data


def resolve_channel_id(token: str, expected_username: str) -> tuple[str, dict]:
    if not normalize_username(expected_username):
        raise RuntimeError("Target Rubika channel username is empty")

    bot_data = _post(token, "getMe")
    bot = bot_data.get("bot") if isinstance(bot_data.get("bot"), dict) else bot_data
    bot_username = normalize_username(bot.get("username") if isinstance(bot, dict) else "")

    update_data = _post(token, "getUpdates", {"limit": UPDATE_LIMIT})
    updates = update_data.get("updates")
    if not isinstance(updates, list):
        raise RuntimeError("Rubika getUpdates response contained no updates array")

    chat_ids = extract_chat_ids(updates)
    matches: list[tuple[str, dict]] = []
    checked = 0
    for chat_id in chat_ids:
        try:
            chat_data = _post(token, "getChat", {"chat_id": chat_id})
        except RuntimeError:
            continue
        checked += 1
        chat = chat_data.get("chat") if isinstance(chat_data.get("chat"), dict) else chat_data
        if is_target_channel(chat, expected_username):
            matches.append((chat_id, chat))

    unique = {chat_id: chat for chat_id, chat in matches}
    if not unique:
        raise RuntimeError(
            "No matching channel update found. In Rubika BotFather, enable "
            "'Receive all messages of channels and groups', then post a fresh "
            "plain-text test message in the target channel and rerun this check."
        )
    if len(unique) > 1:
        raise RuntimeError(
            "More than one chat matched the requested channel username; refusing to choose ambiguously."
        )

    channel_id, chat = next(iter(unique.items()))
    details = {
        "bot_username": bot_username,
        "channel_username": normalize_username(chat.get("username")),
        "channel_title": str(chat.get("title") or ""),
        "chat_type": str(chat.get("chat_type") or ""),
        "updates_received": len(updates),
        "candidate_chats_checked": checked,
    }
    return channel_id, details


def main() -> int:
    token = os.environ.get("RUBIKA_BOT_TOKEN", "").strip()
    username = os.environ.get("RUBIKA_CHANNEL_USERNAME", "offerchin").strip()
    try:
        channel_id, details = resolve_channel_id(token, username)
    except RuntimeError as exc:
        print(f"RUBIKA_CHANNEL_DISCOVERY_FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"RUBIKA_CHANNEL_ID_FOUND={channel_id}")
    print(f"RUBIKA_CHANNEL_USERNAME={details['channel_username'] or username}")
    print(f"RUBIKA_CHANNEL_TITLE={details['channel_title']}")
    print(f"RUBIKA_CHAT_TYPE={details['chat_type']}")
    print(f"RUBIKA_UPDATES_RECEIVED={details['updates_received']}")
    print(f"RUBIKA_CANDIDATE_CHATS_CHECKED={details['candidate_chats_checked']}")
    print("RUBIKA_CHANNEL_DISCOVERY_OK")
    output_path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"channel_id={channel_id}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
