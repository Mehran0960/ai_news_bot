"""Registry for OfferChin delivery destinations.

Content selection depends only on the neutral queue contract. Adding a platform
belongs to the delivery layer: register its destination here and implement its
adapter in publisher.py / the applicable media uploader; do not edit discovery
or ranking in affilio_radar.py.
"""

from __future__ import annotations

# Keep one authoritative list of destinations understood by the publisher.
# "photo" destinations receive the selected offer card; "video" destinations
# receive a vertical promo for that same selected product in the same delivery run.
PLATFORM_REGISTRY = {
    "telegram": {"media": "photo"},
    "bale": {"media": "photo"},
    "youtube": {"media": "video"},
    "aparat": {"media": "video"},
}

PLATFORM_NAMES = tuple(PLATFORM_REGISTRY)
PHOTO_PLATFORMS = tuple(
    name for name, config in PLATFORM_REGISTRY.items()
    if config["media"] == "photo"
)
VIDEO_PLATFORMS = tuple(
    name for name, config in PLATFORM_REGISTRY.items()
    if config["media"] == "video"
)


def validate_registry() -> None:
    """Fail early on accidental invalid registry entries."""
    if len(PLATFORM_NAMES) != len(set(PLATFORM_NAMES)):
        raise ValueError("duplicate OfferChin platform names")
    invalid = {
        name: config.get("media")
        for name, config in PLATFORM_REGISTRY.items()
        if config.get("media") not in {"photo", "video"}
    }
    if invalid:
        raise ValueError(f"unsupported platform media configuration: {invalid}")
