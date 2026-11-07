"""Canonical Persian labels and wording for OfferChin captions and actions."""

SALE_TITLE_PREFIX = "🔥 فروش ویژه"
PRODUCT_TITLE_PREFIX = "🛍️ "
CURRENT_PRICE_PREFIX = "💚 قیمت فعلی: "
DISCOUNT_PREFIX = "⚡️ "
DIGIPAY_INSTALLMENT_TEXT = "💳 با امکان خرید اقساطی (دیجی پی)"
CAPTION_SEPARATOR = "────────────"

PURCHASE_BUTTON_PREFIX = "🛍️ مشاهده و خرید از "
MEMBERSHIP_BUTTON_TEXT = "➕ عضویت در کانال آفِرچین"


def purchase_action_label(merchant: object) -> str:
    """Return the one canonical label for every product purchase action."""
    normalized = str(merchant or "دیجی‌کالا").strip() or "دیجی‌کالا"
    return f"{PURCHASE_BUTTON_PREFIX}{normalized}"
