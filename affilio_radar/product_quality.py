"""Shared validation for publication-ready retail product titles.

Keep this deliberately conservative: reject empty/generic titles and titles that
obviously stop at a grammatical label (for example, "هندزفری بلوتوثی مدل").
"""
from __future__ import annotations

import re
import unicodedata


_INCOMPLETE_FINAL_TOKENS = {
    # Persian
    "مدل", "نوع", "سایز", "رنگ", "طرح", "کد", "شماره", "ظرفیت", "گنجایش",
    "حجم", "وزن", "طول", "عرض", "ارتفاع", "مناسب", "برای", "با", "و", "یا",
    "از", "در", "به", "قابل", "شامل", "حاوی", "دارای", "همراه", "مخصوص",
    "جهت", "تا", "روی", "بدون", "درجه", "ابعاد",
    # Common English feed fragments
    "model", "type", "size", "color", "colour", "code", "capacity", "volume",
    "weight", "length", "width", "height", "with", "and", "or", "for",
    "suitable", "including", "containing", "without",
}


def normalize_product_title(value: object) -> str:
    """Normalize retailer markup/Unicode without changing meaningful wording."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = re.sub(r"[\u200b-\u200f\ufeff]", "", text)
    text = text.replace("\u200c", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" \t\r\n-–—|:،,؛;.")


def is_publishable_product_title(value: object) -> bool:
    """Return False for missing/generic titles and clearly truncated final labels."""
    text = normalize_product_title(value)
    if len(text) < 5:
        return False

    tokens = re.findall(r"[\w]+", text, flags=re.UNICODE)
    if len(tokens) < 2:
        return False


    return tokens[-1].casefold() not in _INCOMPLETE_FINAL_TOKENS


# Keep prohibited-health policy shared by discovery, catalog retention, and
# final publication. The scanner must not fill its finite shortlist with items
# that the publisher is guaranteed to reject later.
_EXCLUDED_HEALTH_PRODUCT_RE = re.compile(
    r"(?:قرص|کپسول|دارو(?:یی)?|مکمل|ویتامین|زینک|منیزیم|"
    r"ب[\s\u200c-]*کمپلکس|بی[\s\u200c-]*کمپلکس|امگا[\s\u200c-]*3|"
    r"کلاژن|کلسیم|کلسی[\s\u200c-]*کید|آرژنین|ال[\s\u200c-]*آرژنین|"
    r"ال[\s\u200c-]*کارنیتین|کارنیتین|پروبیوتیک|کلروفیل|اسپیرولینا|"
    r"کراتین|گینر|پودر[\s\u200c]+پروتئین|پروتئین[\s\u200c]+وی|"
    r"چربی[\s\u200c-]*سوز|شربت[\s\u200c]+(?:خوراکی|ویتامین|مولتی)|"
    r"قطره[\s\u200c]+(?:خوراکی|ویتامین|آهن)|آمپول|ویال[\s\u200c]*(?:خوراکی)?|"
    r"ساشه|مسکن|آنتی[\s\u200c-]*بیوتیک|سرماخوردگی|داروخانه|"
    r"(?i:\b(?:supplement|vitamin|zinc|magnesium|collagen|creatine|probiotic|"
    r"l[- ]?carnitine|omega[- ]?3|protein powder)\b))",
    re.IGNORECASE,
)


def is_prohibited_product_title(value: object) -> bool:
    """Return True for medicines, pharmacy items, vitamins, and supplements."""
    normalized = normalize_product_title(value).lower()
    return bool(_EXCLUDED_HEALTH_PRODUCT_RE.search(normalized))

