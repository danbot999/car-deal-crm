"""Editable configuration for the Facebook Marketplace monitor."""

from urllib.parse import quote_plus


N8N_WEBHOOK_URL: str = (
    "http://localhost:5678/webhook/e0c77d34-c1ec-410a-9b23-b9340180379b"
)
TARGET_URL: str = (
    "https://www.facebook.com/marketplace/auckland/vehicles?maxPrice=7000"
)
SCAN_INTERVAL_SECONDS: int = 300

# Broader Auckland vehicle coverage. Facebook often shows a different slice of
# Marketplace for each search term, so a single /vehicles URL misses a lot.
MAX_PRICE_NZD: int = 7000
TARGET_SEARCH_TERMS: tuple[str, ...] = (
    "car",
    "cheap car",
    "automatic car",
    "manual car",
    "hatchback",
    "sedan",
    "wagon",
    "van",
    "ute",
    "toyota",
    "nissan",
    "mazda",
    "honda",
    "suzuki",
    "subaru",
    "mitsubishi",
    "ford",
    "holden",
    "hyundai",
    "kia",
    "volkswagen",
    "bmw",
    "mercedes",
    "audi",
    "lexus",
)
TARGET_URLS: tuple[str, ...] = (
    TARGET_URL,
    *(
        "https://www.facebook.com/marketplace/auckland/vehicles"
        f"?maxPrice={MAX_PRICE_NZD}&query={quote_plus(term)}"
        for term in TARGET_SEARCH_TERMS
    ),
)

# Scan a rotating batch each cycle so the monitor sees more of the market
# without spending a whole hour on one pass or attracting avoidable blocks.
MAX_SEARCH_URLS_PER_SCAN: int = 8
SEARCH_SCROLL_STEPS: int = 4
SEARCH_SCROLL_PAUSE_MS: int = 1_200
