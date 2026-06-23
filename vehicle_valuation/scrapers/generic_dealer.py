"""Generic dealer inventory adapter using search pages, sitemaps and JSON-LD."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus, urljoin, urlsplit

import requests

from ..config import SOURCE_RESULT_LIMIT, SOURCE_TIMEOUT_SECONDS, USER_AGENT
from ..normalization import NormalizedVehicle, canonical_url, clean_text
from .base import SearchResult
from .directories import public_web_url
from .generic import ConfiguredPortalAdapter, PortalConfig, query_text


INVENTORY_PATH_RE = re.compile(
    r"(?i)/(?:vehicle|vehicles|stock|inventory|used-cars?|cars?-for-sale|our-cars?)/"
)


class GenericDealerAdapter:
    source_id = "generic_dealers"

    def __init__(self, sites: list[tuple[str, str | None]], max_sites: int = 12) -> None:
        self.sites = sites[:max_sites]
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-NZ,en;q=0.9"})

    def _fetch(self, url: str) -> tuple[str, str]:
        response = self.session.get(url, timeout=SOURCE_TIMEOUT_SECONDS, allow_redirects=True)
        response.raise_for_status()
        if not public_web_url(response.url):
            raise RuntimeError("Dealer URL redirected outside the public web.")
        return response.text, response.url

    def _sitemap_candidates(self, base_url: str, target: NormalizedVehicle) -> list[str]:
        sitemap_url = urljoin(base_url, "/sitemap.xml")
        try:
            xml, _ = self._fetch(sitemap_url)
            root = ET.fromstring(xml[:5_000_000])
        except (requests.RequestException, RuntimeError, ET.ParseError):
            return []
        make = (target.make or "").lower().replace(" ", "-")
        model = (target.model or "").lower().replace(" ", "-")
        candidates: list[str] = []
        for node in root.iter():
            if not node.tag.lower().endswith("loc") or not node.text:
                continue
            url = canonical_url(node.text.strip())
            lowered = url.lower()
            if make and model and make in lowered and model in lowered:
                candidates.append(url)
            elif INVENTORY_PATH_RE.search(urlsplit(url).path) and make and make in lowered:
                candidates.append(url)
            if len(candidates) >= 8:
                break
        return candidates

    def search(self, target: NormalizedVehicle, deadline: float) -> SearchResult:
        result = SearchResult(source_id=self.source_id)
        found = {}
        errors: list[str] = []
        for base_url, dealer_name in self.sites:
            if time.monotonic() >= deadline or len(found) >= SOURCE_RESULT_LIMIT:
                break
            host = urlsplit(base_url).hostname or "dealer"
            config = PortalConfig(
                source_id=self.source_id,
                name=dealer_name or host,
                base_url=base_url,
                search_builder=lambda _target: base_url,
                detail_pattern=INVENTORY_PATH_RE,
                seller_type="DEALER",
            )
            parser = ConfiguredPortalAdapter(config)
            query_url = f"{base_url.rstrip('/')}?s={quote_plus(query_text(target))}"
            page_urls = [query_url, *self._sitemap_candidates(base_url, target)]
            for page_url in list(dict.fromkeys(page_urls))[:6]:
                if time.monotonic() >= deadline:
                    break
                try:
                    html, final_url = self._fetch(page_url)
                    listings, rejected = parser.parse(html, final_url, target)
                    result.pages_scanned += 1
                    result.rejected += rejected
                    for listing in listings:
                        listing.seller_name = listing.seller_name or dealer_name or host
                        listing.raw_facts = {
                            **listing.raw_facts,
                            "discoveredDealerDomain": host,
                        }
                        found[listing.url] = listing
                except (requests.RequestException, RuntimeError) as error:
                    errors.append(f"{host}: {clean_text(error)}")
            time.sleep(0.5)
        result.listings = list(found.values())[:SOURCE_RESULT_LIMIT]
        if result.listings or (self.sites and result.pages_scanned):
            result.status = "SUCCESS"
        elif not self.sites:
            result.status = "SKIPPED"
            result.error = "No discovered dealer inventory websites are available yet."
        else:
            result.status = "FAILED"
            result.error = "; ".join(errors[:5]) or "Dealer inventory pages returned no usable data."
        return result
