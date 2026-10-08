from urllib.request import Request, urlopen
import re, html

url = "https://t.me/s/shop_memarketbiz"
req = Request(url, headers={"User-Agent":"Mozilla/5.0"})
with urlopen(req, timeout=30) as r:
    body = r.read().decode("utf-8", "ignore")

msgs = re.findall(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', body, re.S)
posts = [re.sub(r"<[^>]+>", " ", html.unescape(x)).strip() for x in msgs]
print("http_ok=true")
print("bytes=", len(body))
print("message_count=", len(posts))
for i, p in enumerate(posts[-5:], 1):
    print(f"POST_{i}:", " ".join(p.split())[:700])
