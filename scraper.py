"""Asynchronous Facebook Marketplace scraper."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, NotRequired, TypedDict
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

import config


FACEBOOK_BASE_URL = "https://www.facebook.com"
MODERN_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.0.0 Safari/537.36"
)
ITEM_PATH_PATTERN = re.compile(r"/marketplace/item/(\d+)")
PRICE_PATTERN = re.compile(
    r"(?i)(?:NZD\s*|NZ\s*\$\s*|A\s*\$\s*|\$\s*)"
    r"(\d[\d,]*(?:\.\d{1,2})?)"
)
SPACE_PATTERN = re.compile(r"\s+")
GENERIC_TITLE_FRAGMENTS = (
    "facebook",
    "marketplace listing",
    "no photo description",
    "image may contain",
    "log in",
    "sign up",
    "sponsored",
)
LOCATION_SUFFIX_PATTERN = re.compile(
    r"(?i)\s+in\s+[^,]+,\s*New Zealand\s*$"
)
LOCATION_ONLY_PATTERN = re.compile(
    r"(?i)^(?:in\s+)?[^,]+,\s*New Zealand$"
)
MILEAGE_ONLY_PATTERN = re.compile(r"(?i)^\d+(?:[.,]\d+)?\s*[k]?\s*km$")
PAGE_TITLE_SUFFIX_PATTERN = re.compile(
    r"(?i)\s*\|\s*Facebook Marketplace\s*\|\s*Facebook\s*$"
)
UNAVAILABLE_PATTERN = re.compile(
    r"(?i)\b("
    r"marked as sold|listing sold|item sold|vehicle sold|has been sold|"
    r"no longer available|this item is no longer available|"
    r"this content isn't available|this listing isn't available|"
    r"this item isn't available|content is not available|"
    r"listing is not available|item is not available"
    r")\b"
)
DETAIL_TEXT_STOP_MARKERS = (
    "Today's picks",
    "More from seller",
    "More from Marketplace",
    "Related Pages",
    "Sponsored",
)
FINANCE_ONLY_PATTERN = re.compile(
    r"(?i)(?:\$\s*\d[\d,]*(?:\.\d{1,2})?\s*(?:per|/)\s*(?:week|wk)|"
    r"\b(?:per week|weekly payments?|from\s+\$\s*\d[\d,]*\s*/?\s*(?:week|wk))\b)"
)
EXCLUDED_CATEGORY_FRAGMENTS = (
    "powersport",
    "motorcycle",
    "motorbike",
    "scooter",
    "rvs & campers",
    "rvs and campers",
    "rv & camper",
    "commercial truck",
    "bus",
    "coach",
    "trailer",
    "boat",
    "bicycle",
    "bike",
    "parts",
    "wheels",
    "tyres",
    "tires",
)
ALLOWED_CATEGORY_FRAGMENTS = (
    "cars & trucks",
    "cars and trucks",
)
EXCLUDED_TITLE_PATTERN = re.compile(
    r"(?i)\b("
    r"go[\s-]?kart|kart|mini[\s-]?bike|minibike|motorbike|motorcycle|"
    r"scooter|trailer|boat|jet\s*ski|quad\s*bike|atv|utv|"
    r"bus|coach|school\s*bus|tour\s*bus|mini[\s-]?bus|"
    r"motorhome|camper(?:van)?|caravan|rv|commercial\s*truck|"
    r"box\s*truck|flat[\s-]?deck|tipper|tractor\s*unit|lorry|"
    r"isuzu\s+gala|mitsubishi\s+rosa|toyota\s+coaster|"
    r"tyres?|tires?|wheels?|rims?|mags?|parts?|wrecking|dismantling|"
    r"canopy|bumper|gearbox|engine\s+(?:mount|part|parts)|transmission|"
    r"headlight|tail\s*light|seat\s*covers?"
    r")\b"
)
DETAIL_PAGE_WAIT_MS = 3_000
DETAIL_PAGE_TIMEOUT_MS = 45_000
DETAIL_CONCURRENCY = 3
SCAN_STATE_FILE = Path(__file__).with_name("work") / "scan_state.json"


class Listing(TypedDict):
    title: str
    price: float
    url: str
    category: NotRequired[str]
    verified: NotRequired[bool]
    available: NotRequired[bool]
    in_scope: NotRequired[bool]
    rejection_reason: NotRequired[str]
    availabilityStatus: NotRequired[str]
    availabilityConfidence: NotRequired[str]
    filterReason: NotRequired[str]
    sourceSearchUrl: NotRequired[str]


class ListingCandidate(TypedDict):
    title: str
    price: float
    url: str
    sourceSearchUrl: NotRequired[str]


class DetailVerification(TypedDict):
    title: str
    category: str
    available: bool
    in_scope: bool
    verified: bool
    rejection_reason: str
    availability_status: str
    availability_confidence: str


def _clean_text(value: str) -> str:
    """Collapse whitespace and remove surrounding separators."""
    return SPACE_PATTERN.sub(" ", value).strip(" \t\r\n-|")


def _clean_title(value: str) -> str:
    """Normalize a detail-page or search-card title."""
    title = _clean_text(PAGE_TITLE_SUFFIX_PATTERN.sub("", value))
    if " | Facebook Marketplace | Facebook" in title:
        title = title.split(" | Facebook Marketplace | Facebook", 1)[0]
    title = re.sub(r"(?i)^marketplace listing(?: for sale)?:\s*", "", title)
    title = LOCATION_SUFFIX_PATTERN.sub("", title).strip(" ,-|")
    return _clean_text(title)


def _canonical_item_url(href: str) -> str | None:
    """Convert a Marketplace item href into an absolute canonical URL."""
    absolute_url = urljoin(FACEBOOK_BASE_URL, href)
    match = ITEM_PATH_PATTERN.search(urlparse(absolute_url).path)
    if match is None:
        return None
    return f"{FACEBOOK_BASE_URL}/marketplace/item/{match.group(1)}/"


def _extract_price(text: str) -> float | None:
    """Extract a currency amount as a float, including free listings."""
    match = PRICE_PATTERN.search(text)
    if match is not None:
        return float(match.group(1).replace(",", ""))
    if re.search(r"(?i)\bfree\b", text):
        return 0.0
    return None


def _find_listing_container(anchor: Tag) -> Tag:
    """Find the nearest enclosing element that contains a readable price."""
    current = anchor
    for _ in range(5):
        current_text = _clean_text(current.get_text(" ", strip=True))
        if _extract_price(current_text) is not None:
            return current
        if not isinstance(current.parent, Tag):
            break
        current = current.parent
    return anchor


def _is_title_candidate(text: str) -> bool:
    """Return whether text looks like a listing title rather than metadata."""
    if not text or len(text) < 2 or len(text) > 240:
        return False
    lowered = text.casefold()
    if lowered == "untitled marketplace vehicle":
        return False
    if any(fragment in lowered for fragment in GENERIC_TITLE_FRAGMENTS):
        return False
    if _extract_price(text) is not None:
        return False
    if LOCATION_ONLY_PATTERN.fullmatch(text) or MILEAGE_ONLY_PATTERN.fullmatch(text):
        return False
    if re.fullmatch(r"(?i)(?:just listed|\d+\s*(?:m|h|d|w))", text):
        return False
    return True


def _title_has_vehicle_exclusion(title: str) -> bool:
    """Return whether the text clearly points outside passenger-car inventory."""
    return EXCLUDED_TITLE_PATTERN.search(title) is not None


def is_strict_car_listing(title: str, category: str) -> bool:
    """Accept only passenger-car listings with a verified Marketplace category."""
    cleaned_title = _clean_title(title)
    cleaned_category = _clean_text(category)
    if not cleaned_title or not cleaned_category:
        return False
    if _is_excluded_category(cleaned_category):
        return False
    if not _is_allowed_category(cleaned_category):
        return False
    return not _title_has_vehicle_exclusion(cleaned_title)


def _is_finance_only_listing(price: float, title: str, description: str) -> bool:
    """Detect finance advertisements masquerading as low sticker-price listings."""
    haystack = f"{title} {description}"
    return price < 1_000 and FINANCE_ONLY_PATTERN.search(haystack) is not None


def _primary_detail_text(body_text: str) -> str:
    """Remove recommendation sections that can contaminate listing checks."""
    primary_text = body_text
    for marker in DETAIL_TEXT_STOP_MARKERS:
        marker_index = primary_text.find(marker)
        if marker_index != -1:
            primary_text = primary_text[:marker_index]
    return primary_text


def _has_unavailable_signal(page_title: str, description: str, body_text: str) -> bool:
    """Detect sold/unavailable state without reading unrelated recommendations."""
    haystack = f"{page_title} {description} {_primary_detail_text(body_text)}"
    if UNAVAILABLE_PATTERN.search(haystack):
        return True
    return re.search(r"(?im)^\s*sold\s*$", haystack) is not None


def _parse_category_from_page_title(page_title: str) -> str:
    """Extract Facebook Marketplace category from the browser page title."""
    cleaned_title = PAGE_TITLE_SUFFIX_PATTERN.sub("", _clean_text(page_title))
    parts = [part.strip() for part in re.split(r"\s+[–-]\s+", cleaned_title)]
    if len(parts) >= 3:
        return _clean_text(parts[-2])
    return ""


def _is_allowed_category(category: str) -> bool:
    """Return whether a Marketplace category belongs to cars and trucks."""
    lowered = category.casefold()
    if any(fragment in lowered for fragment in EXCLUDED_CATEGORY_FRAGMENTS):
        return False
    return any(fragment in lowered for fragment in ALLOWED_CATEGORY_FRAGMENTS)


def _is_excluded_category(category: str) -> bool:
    """Return whether a category clearly belongs outside road vehicles."""
    lowered = category.casefold()
    return any(fragment in lowered for fragment in EXCLUDED_CATEGORY_FRAGMENTS)


def _best_detail_title(
    h1_values: list[str],
    open_graph_titles: list[str],
    page_title: str,
    fallback_title: str,
) -> str:
    """Choose the strongest real listing title from detail-page metadata."""
    candidates = [*h1_values, *open_graph_titles]
    cleaned_page_title = PAGE_TITLE_SUFFIX_PATTERN.sub("", _clean_text(page_title))
    if cleaned_page_title:
        candidates.append(re.split(r"\s+[–-]\s+", cleaned_page_title)[0])
    candidates.append(fallback_title)

    for candidate in candidates:
        title = _clean_title(candidate)
        if _is_title_candidate(title):
            return title
    return ""


def _extract_title(anchor: Tag, container: Tag) -> str | None:
    """Extract the strongest available title candidate from a listing card."""
    candidates: list[str] = []

    for attribute_name in ("aria-label", "title"):
        attribute_value = anchor.get(attribute_name)
        if isinstance(attribute_value, str):
            price_match = PRICE_PATTERN.search(attribute_value)
            if price_match is not None:
                candidates.append(attribute_value[: price_match.start()].rstrip(" ,"))
            candidates.append(attribute_value)

    for image in anchor.find_all("img"):
        alt_text = image.get("alt")
        if isinstance(alt_text, str):
            candidates.append(alt_text)

    candidates.extend(anchor.stripped_strings)
    if container is not anchor:
        candidates.extend(container.stripped_strings)

    for raw_candidate in candidates:
        candidate = _clean_title(str(raw_candidate))
        if _is_title_candidate(candidate):
            return candidate
    return "Untitled Marketplace vehicle"


def parse_listings(html: str) -> list[ListingCandidate]:
    """Parse Marketplace listing links from rendered HTML."""
    soup = BeautifulSoup(html, "html.parser")
    listings: list[ListingCandidate] = []
    seen_urls: set[str] = set()
    parsing_failures = 0

    for anchor in soup.select('a[href*="/marketplace/item/"]'):
        try:
            href = anchor.get("href")
            if not isinstance(href, str):
                continue

            item_url = _canonical_item_url(href)
            if item_url is None or item_url in seen_urls:
                continue

            container = _find_listing_container(anchor)
            container_text = _clean_text(container.get_text(" ", strip=True))
            price = _extract_price(container_text)
            title = _extract_title(anchor, container)
            if price is None or title is None:
                continue

            listings.append({"title": title, "price": price, "url": item_url})
            seen_urls.add(item_url)
        except Exception as exc:
            parsing_failures += 1
            print(f"[WARN] Skipped one malformed listing: {exc}", flush=True)

    if parsing_failures:
        print(
            f"[WARN] Completed parsing with {parsing_failures} malformed "
            "listing(s) skipped.",
            flush=True,
        )
    return listings


def _all_target_urls() -> list[str]:
    """Return unique search URLs from config while keeping TARGET_URL first."""
    configured_urls = getattr(config, "TARGET_URLS", (config.TARGET_URL,))
    urls = [str(url).strip() for url in configured_urls if str(url).strip()]
    if config.TARGET_URL not in urls:
        urls.insert(0, config.TARGET_URL)
    return list(dict.fromkeys(urls))


def _always_scan_urls() -> list[str]:
    """Return search URLs that should be checked on every scan."""
    configured_urls = getattr(config, "ALWAYS_SCAN_URLS", (config.TARGET_URL,))
    urls = [str(url).strip() for url in configured_urls if str(url).strip()]
    if config.TARGET_URL not in urls:
        urls.insert(0, config.TARGET_URL)
    return list(dict.fromkeys(urls))


def _read_scan_offset(total_urls: int) -> int:
    """Read the rotating search offset used to spread coverage across scans."""
    if total_urls <= 0:
        return 0

    try:
        payload = json.loads(SCAN_STATE_FILE.read_text(encoding="utf-8"))
        offset = int(payload.get("next_offset", 0))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        offset = 0

    return offset % total_urls


def _write_scan_offset(next_offset: int) -> None:
    """Persist the next search offset; failures should not break scanning."""
    try:
        SCAN_STATE_FILE.parent.mkdir(exist_ok=True)
        SCAN_STATE_FILE.write_text(
            json.dumps({"next_offset": next_offset}, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"[WARN] Could not persist scan rotation state: {exc}", flush=True)


def _target_urls_for_scan() -> list[str]:
    """Return this scan's rotating batch of Marketplace search URLs."""
    urls = _all_target_urls()
    if not urls:
        return [config.TARGET_URL]

    max_urls = max(
        1,
        min(len(urls), int(getattr(config, "MAX_SEARCH_URLS_PER_SCAN", len(urls)))),
    )
    always_urls = [url for url in _always_scan_urls() if url in urls]
    if len(always_urls) >= max_urls:
        return always_urls[:max_urls]

    rotating_pool = [url for url in urls if url not in set(always_urls)]
    if not rotating_pool:
        return always_urls

    rotating_batch_size = min(len(rotating_pool), max_urls - len(always_urls))
    offset = _read_scan_offset(len(rotating_pool))
    rotating_selected = [
        rotating_pool[(offset + index) % len(rotating_pool)]
        for index in range(rotating_batch_size)
    ]
    _write_scan_offset((offset + rotating_batch_size) % len(rotating_pool))
    return [*always_urls, *rotating_selected]


async def _collect_candidates_from_search_url(
    context: Any,
    search_url: str,
) -> list[ListingCandidate]:
    """Render and scroll one Marketplace search URL, returning card candidates."""
    retries = max(1, int(getattr(config, "SEARCH_PAGE_RETRIES", 1)))
    retry_backoff_ms = max(0, int(getattr(config, "SEARCH_RETRY_BACKOFF_MS", 0)))

    for attempt in range(1, retries + 1):
        page = await context.new_page()
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(4_000)

            scroll_steps = max(0, int(getattr(config, "SEARCH_SCROLL_STEPS", 0)))
            scroll_pause_ms = max(
                250,
                int(getattr(config, "SEARCH_SCROLL_PAUSE_MS", 1_000)),
            )
            for _ in range(scroll_steps):
                await page.evaluate("window.scrollBy(0, Math.floor(window.innerHeight * 0.9))")
                await page.wait_for_timeout(scroll_pause_ms)

            html = await page.content()
            candidates = parse_listings(html)
            for candidate in candidates:
                candidate["sourceSearchUrl"] = search_url
            print(
                f"[LOG] Search URL yielded {len(candidates)} candidate(s): {search_url}",
                flush=True,
            )
            return candidates
        except PlaywrightTimeoutError as exc:
            print(
                f"[WARN] Search page timed out "
                f"{search_url} (attempt {attempt}/{retries}): {exc}",
                flush=True,
            )
        except Exception as exc:
            print(
                f"[WARN] Search page failed "
                f"{search_url} (attempt {attempt}/{retries}): {exc}",
                flush=True,
            )
        finally:
            await page.close()

        if attempt < retries and retry_backoff_ms:
            await asyncio.sleep(retry_backoff_ms / 1000)

    return []


async def collect_search_candidates(context: Any) -> list[ListingCandidate]:
    """Collect and dedupe candidates across this scan's broader search batch."""
    candidates_by_url: dict[str, ListingCandidate] = {}
    search_urls = _target_urls_for_scan()
    print(
        f"[LOG] Scanning {len(search_urls)} Marketplace search URL(s) this cycle.",
        flush=True,
    )

    for search_url in search_urls:
        for candidate in await _collect_candidates_from_search_url(context, search_url):
            candidates_by_url.setdefault(candidate["url"], candidate)

    print(
        f"[LOG] Search batch produced {len(candidates_by_url)} unique candidate(s).",
        flush=True,
    )
    return list(candidates_by_url.values())


def verify_listing_detail(
    candidate: ListingCandidate,
    detail_data: dict[str, Any],
) -> DetailVerification:
    """Classify a listing using metadata from its Marketplace detail page."""
    page_title = str(detail_data.get("pageTitle") or "")
    body_text = str(detail_data.get("bodyText") or "")
    h1_values = [
        _clean_text(str(value))
        for value in detail_data.get("h1") or []
        if _clean_text(str(value))
    ]
    open_graph_titles = [
        _clean_text(str(value))
        for value in detail_data.get("openGraphTitle") or []
        if _clean_text(str(value))
    ]
    descriptions = [
        _clean_text(str(value))
        for value in detail_data.get("descriptions") or []
        if _clean_text(str(value))
    ]
    description = " ".join(descriptions)

    category = _parse_category_from_page_title(page_title)
    title = _best_detail_title(
        h1_values,
        open_graph_titles,
        page_title,
        candidate["title"],
    )

    if not title:
        return {
            "title": "",
            "category": category,
            "available": True,
            "in_scope": False,
            "verified": False,
            "rejection_reason": "missing_detail_title",
            "availability_status": "NEEDS_REVIEW",
            "availability_confidence": "LOW",
        }

    if _has_unavailable_signal(page_title, description, body_text):
        return {
            "title": title,
            "category": category,
            "available": False,
            "in_scope": True,
            "verified": True,
            "rejection_reason": "sold_or_unavailable",
            "availability_status": "POSSIBLY_SOLD",
            "availability_confidence": "MEDIUM",
        }

    if not category:
        return {
            "title": title,
            "category": "",
            "available": True,
            "in_scope": False,
            "verified": False,
            "rejection_reason": "missing_category",
            "availability_status": "NEEDS_REVIEW",
            "availability_confidence": "LOW",
        }

    if not is_strict_car_listing(title, category):
        reason = (
            "excluded_category"
            if _is_excluded_category(category) or not _is_allowed_category(category)
            else "excluded_vehicle_type"
        )
        return {
            "title": title,
            "category": category,
            "available": True,
            "in_scope": False,
            "verified": True,
            "rejection_reason": reason,
            "availability_status": "ACTIVE",
            "availability_confidence": "HIGH",
        }

    if _is_finance_only_listing(candidate["price"], title, description):
        return {
            "title": title,
            "category": category,
            "available": True,
            "in_scope": False,
            "verified": True,
            "rejection_reason": "finance_only",
            "availability_status": "ACTIVE",
            "availability_confidence": "HIGH",
        }

    return {
        "title": title,
        "category": category,
        "available": True,
        "in_scope": True,
        "verified": True,
        "rejection_reason": "",
        "availability_status": "ACTIVE",
        "availability_confidence": "HIGH",
    }


def _listing_from_verification(
    candidate: ListingCandidate,
    verification: DetailVerification,
) -> Listing | None:
    """Return only verified, active passenger cars for the n8n payload."""
    is_strict_active_car = (
        verification["verified"]
        and verification["available"]
        and verification["in_scope"]
        and verification["availability_status"] == "ACTIVE"
        and is_strict_car_listing(
            verification["title"],
            verification["category"],
        )
    )
    if not is_strict_active_car:
        reason = verification["rejection_reason"] or verification["availability_status"]
        print(f"[LOG] Rejected listing {candidate['url']}: {reason}", flush=True)
        return None

    return {
        "title": verification["title"] or candidate["title"],
        "price": candidate["price"],
        "url": candidate["url"],
        "category": verification["category"],
        "verified": verification["verified"],
        "available": verification["available"],
        "in_scope": verification["in_scope"],
        "rejection_reason": verification["rejection_reason"],
        "availabilityStatus": verification["availability_status"],
        "availabilityConfidence": verification["availability_confidence"],
        "filterReason": verification["rejection_reason"],
        "sourceSearchUrl": candidate.get("sourceSearchUrl", ""),
    }


async def _fetch_detail_data(context: Any, candidate: ListingCandidate) -> Listing | None:
    """Open a listing detail page and return a verified listing if it qualifies."""
    page = await context.new_page()
    try:
        await page.goto(
            candidate["url"],
            wait_until="domcontentloaded",
            timeout=DETAIL_PAGE_TIMEOUT_MS,
        )
        await page.wait_for_timeout(DETAIL_PAGE_WAIT_MS)
        detail_data = await page.evaluate(
            """() => {
                const textValues = (selector) =>
                    Array.from(document.querySelectorAll(selector))
                        .map((element) => element.textContent || "")
                        .map((text) => text.trim())
                        .filter(Boolean)
                        .slice(0, 10);
                const attrValues = (selector, attributeName) =>
                    Array.from(document.querySelectorAll(selector))
                        .map((element) => element.getAttribute(attributeName) || "")
                        .map((text) => text.trim())
                        .filter(Boolean)
                        .slice(0, 10);
                return {
                    pageTitle: document.title || "",
                    h1: textValues("h1"),
                    openGraphTitle: attrValues('meta[property="og:title"]', "content"),
                    descriptions: attrValues(
                        'meta[name="description"], meta[property="og:description"]',
                        "content",
                    ),
                    bodyText: (document.body?.innerText || "").slice(0, 5000),
                };
            }"""
        )
    except PlaywrightTimeoutError as exc:
        print(f"[WARN] Detail page timed out for {candidate['url']}: {exc}", flush=True)
        return None
    except Exception as exc:
        print(f"[WARN] Detail page failed for {candidate['url']}: {exc}", flush=True)
        return None
    finally:
        await page.close()

    verification = verify_listing_detail(candidate, detail_data)
    return _listing_from_verification(candidate, verification)


async def enrich_and_filter_listings(
    context: Any,
    candidates: list[ListingCandidate],
) -> list[Listing]:
    """Verify search-card candidates against their detail pages."""
    semaphore = asyncio.Semaphore(DETAIL_CONCURRENCY)

    async def enrich(candidate: ListingCandidate) -> Listing | None:
        async with semaphore:
            return await _fetch_detail_data(context, candidate)

    enriched = await asyncio.gather(*(enrich(candidate) for candidate in candidates))
    return [listing for listing in enriched if listing is not None]


async def fetch_marketplace_listings() -> list[Listing]:
    """Render configured Marketplace searches and return verified listings."""
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent=MODERN_USER_AGENT,
                    viewport={"width": 1440, "height": 1200},
                    locale="en-NZ",
                    extra_http_headers={"Accept-Language": "en-NZ,en;q=0.9"},
                )
                try:
                    candidates = await collect_search_candidates(context)
                    listings = await enrich_and_filter_listings(context, candidates)
                finally:
                    await context.close()
            finally:
                await browser.close()
    except PlaywrightTimeoutError as exc:
        print(f"[ERROR] Facebook Marketplace navigation timed out: {exc}", flush=True)
        return []
    except Exception as exc:
        print(f"[ERROR] Marketplace scan failed safely: {exc}", flush=True)
        return []

    try:
        return listings
    except Exception as exc:
        print(f"[ERROR] Marketplace HTML could not be parsed: {exc}", flush=True)
        return []
