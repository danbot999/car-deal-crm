"""Editable configuration for the Facebook Marketplace monitor."""

from urllib.parse import urlencode


N8N_WEBHOOK_URL: str = (
    "http://localhost:5678/webhook/e0c77d34-c1ec-410a-9b23-b9340180379b"
)
SCAN_INTERVAL_SECONDS: int = 600

# Facebook Marketplace search settings.
MARKETPLACE_LOCATION_SLUG: str = "auckland"
MAX_PRICE_NZD: int = 7000
SORT_NEWEST_VALUE: str = "creation_time_descend"
ENABLE_NEWEST_SORT: bool = False


def _marketplace_vehicle_url(query: str | None = None) -> str:
    """Build a public Auckland vehicle search URL."""
    params: dict[str, str | int] = {
        "maxPrice": MAX_PRICE_NZD,
    }
    if ENABLE_NEWEST_SORT:
        params["sortBy"] = SORT_NEWEST_VALUE
    if query:
        params["query"] = query
    return (
        f"https://www.facebook.com/marketplace/{MARKETPLACE_LOCATION_SLUG}/vehicles"
        f"?{urlencode(params)}"
    )


TARGET_URL: str = _marketplace_vehicle_url()

# Broader Auckland vehicle coverage. Facebook often shows a different slice of
# Marketplace for each search term, so a single /vehicles URL misses a lot.
TARGET_SEARCH_TERMS: tuple[str, ...] = (
    "car",
    "cheap car",
    "fresh wof",
    "wof rego",
    "needs wof",
    "no wof",
    "must go",
    "urgent sale",
    "moving overseas",
    "as is where is",
    "automatic car",
    "manual car",
    "hatchback",
    "sedan",
    "wagon",
    "people mover",
    "toyota",
    "toyota vitz",
    "toyota corolla",
    "toyota auris",
    "toyota estima",
    "toyota wish",
    "toyota prius",
    "nissan",
    "nissan tiida",
    "nissan note",
    "nissan serena",
    "mazda",
    "mazda demio",
    "mazda axela",
    "mazda atenza",
    "honda",
    "honda fit",
    "honda civic",
    "honda accord",
    "suzuki",
    "suzuki swift",
    "subaru",
    "subaru impreza",
    "subaru legacy",
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

# These are checked every cycle so genuinely fresh general listings do not wait
# for the broader search rotation to come back around.
ALWAYS_SCAN_SEARCH_TERMS: tuple[str, ...] = (
    "car",
    "cheap car",
    "fresh wof",
    "must go",
)
ALWAYS_SCAN_URLS: tuple[str, ...] = (
    TARGET_URL,
    *(_marketplace_vehicle_url(term) for term in ALWAYS_SCAN_SEARCH_TERMS),
)
TARGET_URLS: tuple[str, ...] = (
    TARGET_URL,
    *(_marketplace_vehicle_url(term) for term in TARGET_SEARCH_TERMS),
)

# Scan a rotating batch each cycle so the monitor sees more of the market
# without spending a whole hour on one pass or attracting avoidable blocks.
MAX_SEARCH_URLS_PER_SCAN: int = 16
SEARCH_SCROLL_STEPS: int = 7
SEARCH_SCROLL_PAUSE_MS: int = 1_200
SEARCH_PAGE_RETRIES: int = 2
SEARCH_RETRY_BACKOFF_MS: int = 2_500
