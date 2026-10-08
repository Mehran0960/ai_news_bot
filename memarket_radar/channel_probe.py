from urllib.request import Request, urlopen
from urllib.parse import urlencode
import re, html, os

def fetch(url, data=None):
    body = urlencode(data).encode() if data else None
    req = Request(url, data=body, headers={"User-Agent":"Mozilla/5.0 (panel-probe-3)","Accept":"text/html,application/xhtml+xml"}, method="POST" if data else "GET")
    with urlopen(req, timeout=30) as r:
        return r.status, r.geturl(), r.headers, r.read().decode("utf-8","ignore")

status, final, headers, body = fetch("https://t.me/s/shop_memarketbiz")
msgs = re.findall(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', body, re.S)
posts = [re.sub(r"<[^>]+>", " ", html.unescape(x)).strip() for x in msgs]
print("CHANNEL status=", status, "bytes=", len(body), "message_count=", len(posts))
for i, p in enumerate(posts[-5:], 1):
    print(f"POST_{i}:", " ".join(p.split())[:700])

try:
    status, final, headers, body = fetch("https://aff.memarket24.ir/login")
    title = re.search(r"<title[^>]*>(.*?)</title>", body, re.I|re.S)
    scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)', body, re.I)
    forms = re.findall(r'<form[^>]*?(?:action=["\']([^"\']*)["\'])?[^>]*>', body, re.I|re.S)
    print("PANEL status=", status, "final=", final, "bytes=", len(body))
    print("PANEL title=", re.sub(r"\\s+"," ",html.unescape(title.group(1))).strip() if title else "")
    print("PANEL scripts=", scripts[:20])
    print("PANEL forms=", forms[:10])
except Exception as e:
    print("PANEL_ERROR=", type(e).__name__, str(e))
