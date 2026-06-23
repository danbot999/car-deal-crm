"""Generic JSON-LD and listing-card portal extraction."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import quote_plus, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup, Tag

from ..config import SOURCE_RESULT_LIMIT, SOURCE_TIMEOUT_SECONDS, USER_AGENT
from ..normalization import (
    NormalizedVehicle,
    canonical_url,
    clean_text,
    is_full_cash_vehicle,
    normalize_body,
    normalize_fuel,
    normalize_region,
    normalize_transmission,
    parse_kms,
    parse_price_cents,
    source_listing_id,
    vehicle_from_text,
)
from .base import RawListing, SearchResult


BLOCKED_RE = re.compile(r"(?i)(captcha|verify\s+you\s+are\s+human|access\s+denied|unusual\s+traffic|temporarily\s+blocked)")


@dataclass(frozen=True)
class PortalConfig:
    source_id: str
    name: str
    base_url: str
    search_builder: Callable[[NormalizedVehicle], str]
    detail_pattern: re.Pattern[str]
    seller_type: str = "DEALER"
    crawl_delay_seconds: int = 2


def query_text(target: NormalizedVehicle) -> str:
    return " ".join(str(value) for value in (target.year, target.make, target.model, target.variant) if value)


def slug(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def iter_json_objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from iter_json_objects(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from iter_json_objects(nested)


def type_names(value: Any) -> set[str]:
    raw = value.get("@type") if isinstance(value, dict) else None
    values = raw if isinstance(raw, list) else [raw]
    return {str(item).lower() for item in values if item}


def jsonld_price(item: dict[str, Any]) -> int | None:
    offers = item.get("offers") or item.get("Offer")
    candidates = offers if isinstance(offers, list) else [offers]
    for offer in candidates:
        if not isinstance(offer, dict):
            continue
        price = offer.get("price") or offer.get("lowPrice")
        parsed = parse_price_cents(price)
        if parsed:
            return parsed
    return parse_price_cents(item.get("price"))


def jsonld_url(item: dict[str, Any], page_url: str) -> str | None:
    raw = item.get("url") or item.get("@id")
    if isinstance(raw, str) and raw.strip():
        return canonical_url(urljoin(page_url, raw))
    offers = item.get("offers")
    if isinstance(offers, dict) and isinstance(offers.get("url"), str):
        return canonical_url(urljoin(page_url, offers["url"]))
    return None


def listing_from_jsonld(source_id: str, item: dict[str, Any], page_url: str, seller_type: str) -> RawListing | None:
    names = type_names(item)
    if not names.intersection({"vehicle", "car", "product", "individualproduct"}) and not (item.get("vehicleModelDate") or item.get("mileageFromOdometer")):
        return None
    title = clean_text(item.get("name") or item.get("headline"))
    url = jsonld_url(item, page_url)
    price = jsonld_price(item)
    if not title or not url:
        return None
    allowed, _reason = is_full_cash_vehicle(f"{title} {json.dumps(item, default=str)}", price)
    if not allowed or price is None:
        return None
    odometer = item.get("mileageFromOdometer")
    if isinstance(odometer, dict):
        odometer = odometer.get("value")
    supplied = {
        "year": item.get("vehicleModelDate") or item.get("modelDate") or item.get("productionDate"),
        "make": (item.get("brand") or {}).get("name") if isinstance(item.get("brand"), dict) else item.get("brand"),
        "model": item.get("model") or item.get("vehicleModel"),
        "variant": item.get("vehicleConfiguration") or item.get("vehicleTrim"),
        "kms": parse_kms(odometer) if odometer is not None else None,
        "transmission": item.get("vehicleTransmission"),
        "fuelType": item.get("fuelType"),
        "bodyType": item.get("bodyType"),
    }
    vehicle = vehicle_from_text(title, json.dumps(item, default=str), supplied)
    seller = item.get("seller") or item.get("manufacturer")
    if isinstance(seller, dict):
        seller = seller.get("name")
    image = item.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url") or image.get("contentUrl")
    return RawListing(
        source_id=source_id, source_listing_id=source_listing_id(url), url=url,
        title=title, asking_price_cents=price, year=vehicle.year, make=vehicle.make,
        model=vehicle.model, variant=vehicle.variant, kms=vehicle.kms,
        transmission=vehicle.transmission, fuel_type=vehicle.fuel_type,
        body_type=vehicle.body_type, region=normalize_region(str(item.get("areaServed") or item.get("address") or "")),
        seller_name=clean_text(seller) or None, seller_type=seller_type,
        stock_number=clean_text(item.get("sku") or item.get("productID")) or None,
        vin=clean_text(item.get("vehicleIdentificationNumber")) or None,
        image_url=str(image) if isinstance(image, str) else None, raw_facts=item,
    )


def card_text(anchor: Tag) -> str:
    node: Tag | None = anchor
    best = clean_text(anchor.get_text(" ", strip=True))
    for _ in range(4):
        node = node.parent if isinstance(node.parent, Tag) else None
        if node is None:
            break
        text = clean_text(node.get_text(" ", strip=True))
        if len(text) > len(best) and len(text) <= 2500:
            best = text
        if parse_price_cents(text) and re.search(r"\b(?:19|20)\d{2}\b", text):
            return text
    return best


class ConfiguredPortalAdapter:
    def __init__(self, config: PortalConfig) -> None:
        self.config = config
        self.source_id = config.source_id
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-NZ,en;q=0.9"})

    def fetch(self, url: str) -> str:
        response = self.session.get(url, timeout=SOURCE_TIMEOUT_SECONDS, allow_redirects=True)
        response.raise_for_status()
        text = response.text
        if BLOCKED_RE.search(text[:50_000]):
            raise RuntimeError("Source returned a login, CAPTCHA, or blocking page.")
        return text

    def parse(self, html: str, page_url: str, target: NormalizedVehicle) -> tuple[list[RawListing], int]:
        soup = BeautifulSoup(html, "html.parser")
        found: dict[str, RawListing] = {}
        rejected = 0
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                payload = json.loads(script.string or script.get_text())
            except (ValueError, TypeError):
                continue
            for obj in iter_json_objects(payload):
                listing = listing_from_jsonld(self.source_id, obj, page_url, self.config.seller_type)
                if listing:
                    found[listing.url] = listing
        for anchor in soup.find_all("a", href=True):
            url = canonical_url(urljoin(page_url, str(anchor.get("href"))))
            if not self.config.detail_pattern.search(urlsplit(url).path):
                continue
            text = card_text(anchor)
            price = parse_price_cents(text)
            allowed, _reason = is_full_cash_vehicle(text, price)
            if not allowed or price is None:
                rejected += 1
                continue
            vehicle = vehicle_from_text(text, supplied={})
            if target.make and vehicle.make and target.make.lower() != vehicle.make.lower():
                continue
            if target.model and vehicle.model and target.model.lower() not in vehicle.model.lower() and vehicle.model.lower() not in target.model.lower():
                continue
            title = clean_text(anchor.get("title") or anchor.get_text(" ", strip=True)) or text[:250]
            found.setdefault(
                url,
                RawListing(
                    source_id=self.source_id, source_listing_id=source_listing_id(url), url=url,
                    title=title, asking_price_cents=price, year=vehicle.year, make=vehicle.make,
                    model=vehicle.model, variant=vehicle.variant, kms=vehicle.kms,
                    transmission=vehicle.transmission, fuel_type=vehicle.fuel_type,
                    body_type=vehicle.body_type, region=vehicle.region,
                    seller_type=self.config.seller_type, raw_facts={"cardText": text[:2000]},
                ),
            )
            if len(found) >= SOURCE_RESULT_LIMIT:
                break
        return list(found.values())[:SOURCE_RESULT_LIMIT], rejected

    def search(self, target: NormalizedVehicle, deadline: float) -> SearchResult:
        result = SearchResult(source_id=self.source_id)
        if time.monotonic() >= deadline:
            result.status = "SKIPPED"
            result.error = "Live-search deadline reached."
            return result
        url = self.config.search_builder(target)
        try:
            html = self.fetch(url)
            result.pages_scanned = 1
            result.listings, result.rejected = self.parse(html, url, target)
            result.status = "SUCCESS"
        except Exception as error:
            result.status = "FAILED"
            result.error = clean_text(error)[:1000]
        return result


def quoted_query_builder(base: str, parameter: str) -> Callable[[NormalizedVehicle], str]:
    def build(target: NormalizedVehicle) -> str:
        separator = "&" if "?" in base else "?"
        return f"{base}{separator}{parameter}={quote_plus(query_text(target))}"
    return build
