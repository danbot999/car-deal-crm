"""Exhaustive Trade Me Motors result collection with rendered-page parsing."""

from __future__ import annotations

import re
import threading
import time
from urllib.parse import parse_qs, quote_plus, urlencode, urljoin, urlsplit, urlunsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from ..config import MAX_PORTAL_PAGES, USER_AGENT
from ..matching import same_identity
from ..normalization import (
    NormalizedVehicle,
    canonical_url,
    clean_text,
    is_full_cash_vehicle,
    parse_price_cents,
    source_listing_id,
    vehicle_from_text,
)
from .base import RawListing, SearchResult


_BROWSER_SLOTS = threading.BoundedSemaphore(2)
_VISIBLE_BLOCK_RE = re.compile(
    r"(?i)(verify\s+you\s+are\s+human|access\s+denied|unusual\s+traffic|temporarily\s+blocked)"
)
_LISTING_RE = re.compile(r"/a/motors/(?:cars|used-cars)/[^?#]+/listing/\d+", re.I)
_RESULT_COUNT_RE = re.compile(r"Showing\s+[\d,]+\s+results?", re.I)


def search_query(target: NormalizedVehicle) -> str:
    make = clean_text(target.make)
    model = clean_text(target.model)
    variant = clean_text(target.variant)
    if make.lower() == "bmw" and variant and model.lower().endswith("series"):
        return " ".join(str(value) for value in (target.year, make, variant) if value)
    return " ".join(str(value) for value in (target.year, make, model, variant) if value)


def search_url(target: NormalizedVehicle) -> str:
    query = search_query(target)
    return f"https://www.trademe.co.nz/a/motors/cars/search?search_string={quote_plus(query)}"


def fixed_price(text: str) -> tuple[int | None, str | None]:
    if re.search(r"(?i)\b(?:current\s+bid|reserve\s+(?:met|not\s+met)|bids?)\b", text) and not re.search(
        r"(?i)\bbuy\s+now\b", text
    ):
        return None, "auction_without_buy_now"
    labelled = re.findall(
        r"(?i)(?:asking\s+price|cash\s+price|buy\s+now|or\s+near\s+offer|ono)\s*\$\s*([\d,]+(?:\.\d{1,2})?)",
        text,
    )
    if labelled:
        values = [parse_price_cents(value) for value in labelled]
        price = max((value for value in values if value is not None), default=None)
    else:
        price = parse_price_cents(text)
    allowed, reason = is_full_cash_vehicle(text, price)
    return (price, None) if allowed else (None, reason)


def title_from_card(text: str, anchor_text: str, target: NormalizedVehicle) -> str:
    lines = [clean_text(line) for line in re.split(r"[\r\n]+", text) if clean_text(line)]
    make = re.escape(target.make or "")
    model = re.escape(target.model or "")
    for line in lines:
        if make and model and re.search(make, line, re.I) and re.search(model, line, re.I):
            return line[:500]
    for line in lines:
        if re.search(r"\b(?:19|20)\d{2}\b", line) and not re.search(r"(?i)\$|finance|watchlist", line):
            return line[:500]
    return (clean_text(anchor_text) or (lines[0] if lines else "Trade Me vehicle"))[:500]


def parse_rendered_cards(cards: list[dict[str, str]], target: NormalizedVehicle) -> tuple[list[RawListing], int]:
    found: dict[str, RawListing] = {}
    rejected = 0
    for card in cards:
        href = card.get("href") or ""
        if not _LISTING_RE.search(urlsplit(href).path):
            continue
        listing_match = _LISTING_RE.search(urlsplit(href).path)
        if not listing_match:
            continue
        parts = urlsplit(href)
        url = canonical_url(f"{parts.scheme}://{parts.netloc}{listing_match.group(0)}")
        text = clean_text(card.get("text"))
        title = title_from_card(text, card.get("anchorText") or "", target)
        vehicle = vehicle_from_text(title, text)
        if not same_identity(target, vehicle):
            rejected += 1
            continue
        price, reason = fixed_price(text)
        if price is None:
            rejected += 1
            continue
        found[url] = RawListing(
            source_id="trademe_motors",
            source_listing_id=source_listing_id(url),
            url=url,
            title=title,
            asking_price_cents=price,
            year=vehicle.year,
            make=vehicle.make,
            model=vehicle.model,
            variant=vehicle.variant,
            kms=vehicle.kms,
            transmission=vehicle.transmission,
            fuel_type=vehicle.fuel_type,
            body_type=vehicle.body_type,
            region=vehicle.region,
            seller_type="MIXED",
            sale_type="FIXED_PRICE",
            image_url=card.get("image") or None,
            raw_facts={"cardText": text[:4000], "priceReason": reason},
        )
    return list(found.values()), rejected


def next_page_url(current_url: str, candidates: list[str], seen_urls: set[str]) -> str | None:
    for candidate in candidates:
        absolute = urljoin(current_url, candidate)
        if absolute not in seen_urls:
            return absolute
    parts = urlsplit(current_url)
    query = parse_qs(parts.query)
    current_page = int((query.get("page") or ["1"])[0])
    query["page"] = [str(current_page + 1)]
    generated = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), ""))
    return generated if generated not in seen_urls else None


class TradeMeMotorsAdapter:
    source_id = "trademe_motors"

    def search(self, target: NormalizedVehicle, deadline: float) -> SearchResult:
        result = SearchResult(source_id=self.source_id)
        if not target.make or not target.model:
            result.status = "SKIPPED"
            result.error = "Canonical make/model is required for Trade Me search."
            return result
        if time.monotonic() >= deadline:
            result.status = "SKIPPED"
            result.error = "Live-search deadline reached."
            return result

        acquired = _BROWSER_SLOTS.acquire(timeout=max(1, min(60, deadline - time.monotonic())))
        if not acquired:
            result.status = "SKIPPED"
            result.error = "Browser pool was busy until the search deadline."
            return result
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1440, "height": 1200},
                    locale="en-NZ",
                    extra_http_headers={"Accept-Language": "en-NZ,en;q=0.9"},
                )
                page = context.new_page()
                page.set_default_timeout(20_000)
                current_url: str | None = search_url(target)
                visited_pages: set[str] = set()
                found: dict[str, RawListing] = {}
                expected_results: int | None = None

                while current_url and current_url not in visited_pages and result.pages_scanned < MAX_PORTAL_PAGES:
                    if time.monotonic() >= deadline:
                        break
                    visited_pages.add(current_url)
                    try:
                        page.goto(current_url, wait_until="domcontentloaded", timeout=60_000)
                        page.wait_for_timeout(4_000)
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(1_000)
                    except PlaywrightTimeoutError:
                        result.error = "A Trade Me result page timed out after partial collection."
                        break

                    body = clean_text(page.locator("body").inner_text(timeout=10_000))
                    if _VISIBLE_BLOCK_RE.search(body[:4000]):
                        result.status = "FAILED"
                        result.error = "Trade Me displayed a human-verification or access-block page."
                        break
                    count_match = re.search(r"Showing\s+([\d,]+)\s+results?", body, re.I)
                    if count_match:
                        expected_results = int(count_match.group(1).replace(",", ""))

                    cards = page.locator('a[href*="/listing/"]').evaluate_all(
                        r"""anchors => anchors.map(anchor => {
                          let node = anchor;
                          let best = anchor.innerText || '';
                          for (let i = 0; i < 7 && node?.parentElement; i += 1) {
                            node = node.parentElement;
                            const text = node.innerText || '';
                            if (text.length > best.length && text.length < 5000) best = text;
                            if (/\$\s*[\d,]{3,}/.test(text) && /(?:19|20)\d{2}/.test(text)) break;
                          }
                          const image = node?.querySelector?.('img')?.currentSrc || node?.querySelector?.('img')?.src || '';
                          return { href: anchor.href || '', anchorText: anchor.innerText || '', text: best, image };
                        })"""
                    )
                    before_count = len(found)
                    listings, rejected = parse_rendered_cards(cards, target)
                    result.rejected += rejected
                    for listing in listings:
                        found[listing.url] = listing
                    result.pages_scanned += 1

                    next_candidates = page.locator("a").evaluate_all(
                        """anchors => anchors.filter(anchor => {
                          const label = `${anchor.innerText || ''} ${anchor.getAttribute('aria-label') || ''}`;
                          return /next/i.test(label) && anchor.href;
                        }).map(anchor => anchor.href)"""
                    )
                    if not next_candidates:
                        page_links = page.locator('a[href*="page="]').evaluate_all("anchors => anchors.map(a => a.href)")
                        next_candidates = [link for link in page_links if link not in visited_pages]
                    if expected_results is not None and len(found) >= expected_results:
                        current_url = None
                    elif not cards or (
                        result.pages_scanned > 1
                        and len(found) == before_count
                        and not next_candidates
                    ):
                        current_url = None
                    else:
                        current_url = next_page_url(current_url, next_candidates, visited_pages)

                result.listings = list(found.values())
                if result.status != "FAILED":
                    result.status = "SUCCESS"
                    if time.monotonic() >= deadline:
                        result.error = "Search deadline reached after collecting available pages."
                context.close()
                browser.close()
        except Exception as error:
            result.status = "FAILED"
            result.error = clean_text(error)[:1000]
        finally:
            _BROWSER_SLOTS.release()
        return result
