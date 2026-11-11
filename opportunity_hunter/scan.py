#!/usr/bin/env python3
"""Conservative public-source discovery for Iranian classifieds. No posting or outreach."""
from __future__ import annotations
import argparse, datetime as dt, email.utils, html, json, re, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
UA = "OpportunityHunter/0.1 public-source research"


def norm(s: str) -> str:
    return (s or "").translate(DIGITS).replace("ي", "ی").replace("ك", "ک").replace("٬", ",").replace("٫", ".")


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"): self.skip += 1
        elif tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3"): self.out.append("\n")
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip: self.skip -= 1
        elif tag in ("p", "div", "li", "tr", "h1", "h2", "h3"): self.out.append("\n")
    def handle_data(self, data):
        if not self.skip: self.out.append(data)


def visible(raw):
    p = TextParser(); p.feed(raw)
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t\xa0]+", " ", html.unescape(" ".join(p.out)))).strip()


def fetch(url, limit=3_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/rss+xml,application/xml,*/*"})
    with urllib.request.urlopen(req, timeout=25) as res:
        data = res.read(limit + 1)
        if len(data) > limit: raise ValueError("response too large")
        return data.decode(res.headers.get_content_charset() or "utf-8", "replace"), res.geturl()


def meta_tags(raw):
    out = {}
    for tag in re.findall(r"(?is)<meta\b[^>]*>", raw):
        attrs = {m.group(1).lower(): next((x for x in m.groups()[1:] if x is not None), "")
                 for m in re.finditer(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", tag)}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key and attrs.get("content"): out[key] = html.unescape(attrs["content"])
    return out


def discount_claim(text):
    vals = []
    for m in re.finditer(r"(?<!\d)(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:٪|%)\s*(?:تخفیف)?", norm(text)):
        try:
            v = float(m.group(1).replace(",", ""))
            if 0 < v <= 100: vals.append(v)
        except ValueError: pass
    return max(vals) if vals else None


def price_points(text):
    found = []
    for m in re.finditer(r"(?<!\d)(\d{1,3}(?:,\d{3})+|\d{6,12})\s*(تومان|تومن|ریال)", norm(text)):
        n = int(m.group(1).replace(",", ""))
        if m.group(2) == "ریال": n //= 10
        if n >= 1000: found.append(n)
    return sorted(set(found))


def parse_page(src):
    raw, url = fetch(src["url"])
    text = visible(raw); ntext = norm(text)
    m = meta_tags(raw)
    rec = {"id": src["id"], "type": src["type"], "topic": src.get("topic", ""),
           "url": url, "title": m.get("og:title") or m.get("title") or src.get("label", ""),
           "text": text, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    d = discount_claim(text)
    if d is not None: rec["discount_percent_claimed"] = d
    phones = sorted(set(re.findall(r"(?:\+98|0098|0)?(?:21\s*)?[0-9۰-۹٠-٩][0-9۰-۹٠-٩\- ]{7,12}", text)))
    phones = [re.sub(r"\s+", " ", p).strip() for p in phones if len(re.sub(r"\D", "", norm(p))) >= 10]
    if phones: rec["published_contact_numbers"] = phones[:8]
    if re.search(r"یک\s*سال\s*ضمانت|۱\s*سال\s*ضمانت|یکسال\s*ضمانت", ntext):
        rec["warranty_claim"] = "ادعای ضمانت یک‌ساله در صفحه عرضه‌کننده؛ نیازمند تأیید کتبی"
    area = re.search(r"(?:منطقه|مناطق)\s*(?:های)?\s*([0-9 ،،–-]{1,50})", ntext)
    if area:
        nums = list(dict.fromkeys(re.findall(r"\d{1,2}", area.group(1))))
        if nums: rec["service_area_numbers"] = nums
    active = re.search(r"(\d[\d,]*)\s*خدمت\s*دیگر\s*در[^\n]{0,40}فعال\s*است", ntext)
    if active: rec["active_service_listings"] = int(active.group(1).replace(",", ""))
    reviews = re.search(r"(\d[\d,]*)\s*نظر\s*[|｜]\s*([0-9.]+)", ntext)
    if reviews:
        rec["review_count"] = int(reviews.group(1).replace(",", ""))
        rec["average_rating"] = float(reviews.group(2))
    dates = list(dict.fromkeys(re.findall(r"140[0-9]/\d{1,2}/\d{1,2}", ntext)))
    if dates: rec["visible_recent_review_dates_jalali"] = dates[:8]
    prices = price_points(text)
    if prices: rec["price_points_toman"] = prices[:30]
    return rec


def parse_feed(src):
    raw, feed_url = fetch(src["url"], 4_000_000)
    root = ET.fromstring(raw)
    items = root.findall(".//item") or root.findall(".//{*}entry")
    out = []
    for item in items[:int(src.get("limit", 60))]:
        def child(name):
            el = item.find(name)
            if el is None: el = item.find(f"{{*}}{name}")
            return "" if el is None else " ".join(el.itertext()).strip()
        title = child("title")
        link = child("link")
        if not link:
            el = item.find("link")
            if el is None: el = item.find("{*}link")
            if el is not None: link = el.attrib.get("href", "")
        desc = child("description") or child("summary") or child("content")
        pub = child("pubDate") or child("published") or child("updated")
        try:
            stamp = email.utils.parsedate_to_datetime(pub)
            if stamp.tzinfo is None: stamp = stamp.replace(tzinfo=dt.timezone.utc)
            stamp = stamp.astimezone(dt.timezone.utc).isoformat()
        except Exception:
            try: stamp = dt.datetime.fromisoformat(pub.replace("Z", "+00:00")).astimezone(dt.timezone.utc).isoformat()
            except Exception: stamp = None
        text = title + "\n" + visible(desc)
        out.append({"source_id": src["id"], "source_url": feed_url, "title": title,
                    "description": visible(desc)[:1000], "url": link, "published_at": stamp,
                    "topic_type": classify(text), "discount_percent_claimed": discount_claim(text),
                    "price_points_toman": price_points(text), "text": text})
    return out


def classify(text):
    t = norm(text).lower()
    # Product bundles can contain "service" (سرویس); don't tag kitchenware sets as services.
    product_bundle_markers = ("سرویس پخت و پز", "سرویس قابلمه", "سرویس غذاخوری", "سرویس قاشق", "سرویس چایخوری")
    if any(w in t for w in product_bundle_markers): return "product"
    if any(w in t for w in ("عمده", "تخلیه انبار", "موجودی مازاد", "تولیدکننده", "تأمین کننده", "تامین کننده")): return "wholesale_or_surplus"
    if any(w in t for w in ("تعمیر", "سرویس", "نصب", "لوله کشی", "حمل بار", "نظافت", "آموزش", "مشاوره", "خدمات")): return "service"
    return "product"


def parse_telegram(channel):
    url = "https://t.me/s/" + urllib.parse.quote(channel)
    raw, final = fetch(url)
    blocks = re.findall(r'<div[^>]+data-post="([^"]+)"[^>]*>(.*?)(?=<div[^>]+data-post="[^"]+"[^>]*>|</main>|\Z)', raw, re.S | re.I)
    out = []
    for key, block in blocks:
        m = re.search(r'<div[^>]+class="[^"]*tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S | re.I)
        if not m: continue
        text = visible(m.group(1))
        if len(text) < 15: continue
        tm = re.search(r'<time\b[^>]*datetime=["\']([^"\']+)', block, re.I)
        try: stamp = dt.datetime.fromisoformat(tm.group(1).replace("Z", "+00:00")).astimezone(dt.timezone.utc).isoformat() if tm else None
        except Exception: stamp = None
        links = re.findall(r'<a[^>]+href=["\']([^"\']+)', block, re.I)
        out.append({"source_id": "telegram:" + channel, "source_url": final, "title": text.splitlines()[0][:160],
                    "description": text[:1000], "url": "https://t.me/" + key, "linked_urls": links[:15],
                    "published_at": stamp, "topic_type": classify(text), "discount_percent_claimed": discount_claim(text),
                    "price_points_toman": price_points(text), "text": text})
    return out


def jalali_to_gregorian(jy, jm, jd):
    breaks = [-61,9,38,199,426,686,756,818,1111,1181,1210,1635,2060,2097,2192,2262,2324,2394,2456,3178]
    gy, leap_j, jp = jy + 621, -14, breaks[0]
    jump = 0
    for jb in breaks[1:]:
        if jy < jb: break
        jump = jb - jp
        if jy - jp < jump: break
        leap_j += (jump // 33) * 8 + (jump % 33) // 4
        jp = jb
    n = jy - jp
    leap_j += (n // 33) * 8 + ((n % 33) + 3) // 4
    if jump and jump % 33 == 4 and jump - n == 4: leap_j += 1
    leap_g = gy // 4 - ((gy // 100 + 1) * 3) // 4 - 150
    march = 20 + leap_j - leap_g
    if jump and jump - n < 6: n = n - jump + ((jump + 4) // 33) * 33
    g = dt.date(gy, 3, march)
    days = (jm - 1) * 31 + jd - 1 if jm <= 6 else 186 + (jm - 7) * 30 + jd - 1
    return g + dt.timedelta(days=days)


def build_service_opportunity(group, records, now):
    supplier = next((r for r in records if r["type"] == "supplier_offer"), {})
    market = next((r for r in records if r["type"] == "market_signal"), {})
    price = next((r for r in records if r["type"] == "price_benchmark"), {})
    reasons, demand, value = [], 4, 7
    recent = 0
    for stamp in market.get("visible_recent_review_dates_jalali", []):
        try:
            y, m, d = map(int, stamp.split("/"))
            age = (now.date() - jalali_to_gregorian(y, m, d)).days
            if 0 <= age <= 7: recent += 1
        except Exception: pass
    if recent:
        demand += min(6, recent * 2); reasons.append(f"{recent} نظر تاریخ‌دار در ۷ روز اخیر؛ سیگنال ضعیف فعالیت بازار، نه شمار خریدار")
    if market.get("review_count", 0) >= 1000:
        demand += 2; reasons.append(f"{market['review_count']} نظر تجمعی؛ سابقه بازار، نه تقاضای لحظه‌ای")
    competition = int(market.get("active_service_listings", 0) or 0)
    if competition:
        reasons.append(f"{competition} خدمت فعال؛ شاخص عرضه/رقابت و بدون امتیاز تقاضا")
    discount = supplier.get("discount_percent_claimed")
    if isinstance(discount, (int,float)) and 0 < discount <= 25:
        value += min(8, round(discount * .6)); reasons.append(f"ادعای {discount:g}٪ تخفیف؛ اعتبار و قیمت پایه هنوز تأیید نشده")
    if supplier.get("warranty_claim"): value += 3; reasons.append("ادعای ضمانت یک‌ساله؛ نیازمند تأیید کتبی")
    prices = price.get("price_points_toman", [])
    if prices: value += 2; reasons.append("جدول قیمت مرجع مستقل موجود است؛ اقلام مصرفی جدا هستند")
    supplier_score = 8
    if supplier.get("published_contact_numbers"): supplier_score += 3; reasons.append("راه تماس عمومی درج شده")
    if supplier.get("service_area_numbers"): supplier_score += 2; reasons.append("محدوده خدمت درج شده")
    if supplier.get("warranty_claim"): supplier_score += 2
    if supplier.get("url"): supplier_score += 1
    scores = {"demand": min(25,demand), "value": min(25,value), "supplier": min(20,supplier_score),
              "monetization": 3, "ease": 7 if supplier.get("service_area_numbers") else 5, "risk": 2}
    gates = {"offer_terms_confirmed_with_supplier": bool(supplier.get("offer_terms_confirmed_with_supplier")),
             "final_customer_price_confirmed": bool(supplier.get("final_customer_price_confirmed")),
             "commission_or_lead_fee_agreed": bool(supplier.get("commercial_agreement_verified")),
             "permission_to_advertise_verified": bool(supplier.get("permission_to_advertise_verified")),
             "availability_and_capacity_confirmed": bool(supplier.get("availability_and_capacity_confirmed"))}
    ready = all(gates.values())
    return {"opportunity_id":group["id"],"title":group["title"],"category":"service",
            "city_or_area":group.get("city_or_area","نامشخص"),"total_score":sum(scores.values()),"scores":scores,
            "status":"READY_FOR_AD_REVIEW" if ready else "PROMISING_BUT_UNVERIFIED","publish_ready":ready,
            "recommended_revenue_models":["lead_fee","commission"],"monetization_status":"NO_AGREEMENT_VERIFIED",
            "claimed_discount_percent":discount,"market_price_benchmark_toman":[min(prices),max(prices)] if prices else None,
            "active_competing_service_listings":competition or None,"cumulative_reviews":market.get("review_count"),
            "market_average_rating":market.get("average_rating"),"recent_review_dates_jalali":market.get("visible_recent_review_dates_jalali",[])[:5],
            "recent_review_count_7d":recent,"evidence_urls":[r.get("url") for r in (supplier,market,price) if r.get("url")],
            "reasons":reasons,"blocking_gates":[k for k,v in gates.items() if not v],
            "warning":"تا زمان تأیید شرایط، قیمت، توافق درآمدی، اجازه تبلیغ و ظرفیت، آگهی منتشر نشود."}


def unreliable_discount(item):
    t = norm(item.get("title","") + " " + item.get("text","")).lower()
    return any(w in t for w in ("غیرواقعی","قیمت قبلی نامعتبر","تخفیف نامطمئن","قیمت‌سازی"))


def quarantine_reason(item):
    if unreliable_discount(item):
        return "منبع، ادعای تخفیف را غیرواقعی/نامطمئن علامت زده است."
    discount = item.get("discount_percent_claimed")
    if discount is None:
        discount = discount_claim(item.get("text", ""))
    if isinstance(discount, (int,float)) and discount >= 80:
        return "ادعای تخفیف ۸۰٪ یا بیشتر؛ قرنطینه تا تطبیق قیمت پایه، تاریخچه و حداقل سه مرجع همسان. این ادعا به‌تنهایی تخفیف واقعی نیست."
    return ""


def run(config):
    now = dt.datetime.now(dt.timezone.utc)
    pages, leads, errors = [], [], []
    pages_cfg, feeds, queries, channels = (config.get(k,[]) for k in ("pages","rss_feeds","google_news_queries","telegram_channels"))
    attempted = len(pages_cfg)+len(feeds)+len(queries)+len(channels)
    for src in pages_cfg:
        try: pages.append(parse_page(src))
        except Exception as e: errors.append({"id":src["id"],"error":f"{type(e).__name__}: {e}"})
    raw_items = []
    for src in feeds:
        try: raw_items.extend(parse_feed(src))
        except Exception as e: errors.append({"id":src["id"],"error":f"{type(e).__name__}: {e}"})
    for src in queries:
        url = "https://news.google.com/rss/search?q="+urllib.parse.quote(src["query"])+"&hl=fa&gl=IR&ceid=IR:fa"
        try: raw_items.extend(parse_feed({"id":src["id"],"url":url,"limit":30}))
        except Exception as e: errors.append({"id":src["id"],"error":f"{type(e).__name__}: {e}"})
    for ch in channels:
        try: raw_items.extend(parse_telegram(ch))
        except Exception as e: errors.append({"id":"telegram:"+ch,"error":f"{type(e).__name__}: {e}"})
    cutoff = now - dt.timedelta(days=21)
    rejected, discovery = [], []
    for item in raw_items:
        if not item.get("title"): continue
        hold_reason = quarantine_reason(item)
        if hold_reason:
            rejected.append({"title":item["title"],"url":item.get("url"),"discount_percent_claimed":item.get("discount_percent_claimed"),"reason":hold_reason}); continue
        try: pub = dt.datetime.fromisoformat(item["published_at"].replace("Z","+00:00")) if item.get("published_at") else None
        except Exception: pub = None
        if pub and pub < cutoff: continue
        flags = ["قیمت همسان، موجودی و مجازبودن عرضه هنوز تأیید نشده"]
        if item.get("topic_type") == "service": flags.append("ظرفیت خدمت و توافق هزینه سرنخ/پورسانت نامشخص است")
        else: flags.append("نوع دقیق، variant، وضعیت و قیمت نهایی باید تطبیق داده شود")
        discovery.append({"title":item["title"][:180],"url":item.get("url"),"source":item.get("source_id"),
                          "topic_type":item.get("topic_type"),"published_at":item.get("published_at"),
                          "discount_percent_claimed":item.get("discount_percent_claimed"),"status":"DISCOVERY_ONLY","reasons":flags})
    discovery.sort(key=lambda x:(x.get("published_at") or "",x["title"]),reverse=True)
    by_id = {p["id"]:p for p in pages}
    opps = []
    for group in config.get("opportunity_groups",[]):
        recs = [by_id[s] for s in group.get("source_ids",[]) if s in by_id]
        if recs: opps.append(build_service_opportunity(group,recs,now))
    return {"schema_version":"0.1.0","scanned_at_utc":now.isoformat(),
            "scope":"Iran | all goods and services; current source coverage is partial, not exhaustive",
            "source_summary":{"attempted":attempted,"succeeded":attempted-len(errors),"failed":len(errors),"page_records":len(pages),"feed_items":len(raw_items)},
            "opportunities":sorted(opps,key=lambda x:x["total_score"],reverse=True),
            "discovery_leads":discovery[:80],"rejected":rejected[:80],"source_errors":errors,
            "safety":{"ads_published":0,"seller_contacted":0,"payments_made":0,
                      "note":"Read-only discovery. Ads require documented supplier agreement, verified terms/capacity, permission and manual approval."}}


def markdown(report):
    lines=["# گزارش شکارچی فرصت | Opportunity Hunter","",f"- زمان UTC: {report['scanned_at_utc']}",
           f"- منابع موفق: {report['source_summary']['succeeded']} از {report['source_summary']['attempted']}",
           f"- سرنخ‌های اکتشافی: {len(report['discovery_leads'])}",f"- موارد ردشده: {len(report['rejected'])}",""]
    for o in report["opportunities"]:
        lines += [f"## {o['title']}",f"- امتیاز: {o['total_score']}/100 — {o['status']}",
                  f"- محدوده: {o['city_or_area']}",f"- تخفیف ادعایی: {o.get('claimed_discount_percent') or 'نامشخص'}٪",
                  f"- آماده انتشار: {'بله' if o['publish_ready'] else 'خیر'}","### دلایل",*[f"- {x}" for x in o["reasons"]],
                  "### گیت‌های مسدودکننده",*[f"- {x}" for x in o["blocking_gates"]],"### منابع",*[f"- {x}" for x in o["evidence_urls"]],""]
    if report["discovery_leads"]:
        lines += ["## سرنخ‌های صرفاً اکتشافی",*[f"- [{x['title']}]({x.get('url') or '#'}) — {'؛ '.join(x['reasons'])}" for x in report["discovery_leads"][:25]],""]
    if report["rejected"]: lines += ["## موارد ردشده",*[f"- {x['title']}: {x['reason']}" for x in report["rejected"][:20]],""]
    if report["source_errors"]: lines += ["## منابع ناموفق",*[f"- {x['id']}: {x['error']}" for x in report["source_errors"]],""]
    lines += ["---","تعداد آگهی، تعداد نظر یا درصد تخفیف به‌تنهایی اثبات تقاضا/فروش نیست. این گزارش مجوز انتشار نیست."]
    return "\n".join(lines)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",default=str(ROOT/"config"/"sources.json"))
    ap.add_argument("--output-dir",default=str(ROOT/"output"))
    args=ap.parse_args()
    config=json.loads(Path(args.config).read_text(encoding="utf-8"))
    report=run(config); out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    (out/"latest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"latest.md").write_text(markdown(report),encoding="utf-8")
    print(f"OPPORTUNITY_HUNTER attempted={report['source_summary']['attempted']} succeeded={report['source_summary']['succeeded']} opportunities={len(report['opportunities'])} leads={len(report['discovery_leads'])} rejected={len(report['rejected'])}")
    for o in report["opportunities"]: print(f"OPPORTUNITY score={o['total_score']} status={o['status']} publish_ready={o['publish_ready']} title={o['title']}")
    for e in report["source_errors"]: print(f"SOURCE_ERROR {e['id']}: {e['error']}")
    return 0 if report["source_summary"]["succeeded"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
