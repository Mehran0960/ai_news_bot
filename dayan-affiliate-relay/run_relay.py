"""
Compatibility launcher for relay.py.

Telethon reverses the min_id/max_id filtering semantics when reverse=True.
The wrapper keeps the simple min_id > last_seen filter and reverses results
after collection so that new posts are queued oldest-first. It also permits
automatic selection when exactly one code in a multi-code post has a configured
personal affiliate link.
"""
import asyncio
from telethon import TelegramClient
import relay as relay_module

_original_iter_messages = TelegramClient.iter_messages

def chronological_iter_messages(self, *args, **kwargs):
    requested_reverse = bool(kwargs.pop("reverse", False))

    async def collect_then_yield():
        messages = []
        async for message in _original_iter_messages(self, *args, **kwargs):
            messages.append(message)
        if requested_reverse:
            messages.reverse()
        for message in messages:
            yield message

    return collect_then_yield()

TelegramClient.iter_messages = chronological_iter_messages

def resolve_unambiguous_code(item, links, overrides):
    override = overrides.get(str(item["source_message_id"]))
    if isinstance(override, dict):
        override = override.get("product_code")
    if override:
        code = str(override).strip()
        url = links.get(code)
        if isinstance(url, str) and url.startswith("https://"):
            return code
        return None

    codes = [str(code) for code in item.get("product_codes", [])]
    mapped = [
        code for code in codes
        if isinstance(links.get(code), str) and links[code].startswith("https://")
    ]
    return mapped[0] if len(mapped) == 1 else None

relay_module.resolve_product_code = resolve_unambiguous_code

if __name__ == "__main__":
    asyncio.run(relay_module.main())
