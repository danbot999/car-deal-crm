"""Dealer website discovery from NZ directories and portal dealer pages."""

from __future__ import annotations

import ipaddress
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from ..config import SOURCE_TIMEOUT_SECONDS, USER_AGENT
from ..normalization import canonical_url, clean_text


PROFILE_RE = re.compile(r"(?i)/(?:dealer|dealership|trader|motor-trader|profile|showroom)(?:/|$)")
SKIP_HOST_RE = re.compile(
    r"(?i)(?:facebook|instagram|youtube|linkedin|twitter|x\.com|google|apple|"
    r"maps|mailto|tel|motortraders\.govt\.nz)$"
)


@dataclass(frozen=True)
class DiscoveredDealer:
    source_id: str
    dealer_name: str | None
    inventory_url: str
    domain: str


@dataclass
class DiscoveryResult:
    source_id: str
    status: str = "SUCCESS"
    sites: list[DiscoveredDealer] = field(default_factory=list)
    pages_scanned: int = 0
    error: str | None = None


def public_web_url(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.lower().strip(".")
    if host in {"localhost", "127.0.0.1", "::1"} or SKIP_HOST_RE.search(host):
        return False
    try:
        address = ipaddress.ip_address(host)
        return not (address.is_private or address.is_loopback or address.is_reserved)
    except ValueError:
        return "." in host


def page_links(html: str, page_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        url = canonical_url(urljoin(page_url, str(anchor.get("href"))))
        if public_web_url(url):
            links.append((url, clean_text(anchor.get_text(" ", strip=True))[:250]))
    return links


def discover_directory(definition: dict[str, object], deadline: float) -> DiscoveryResult:
    source_id = str(definition["id"])
    base_url = str(definition["base_url"])
    base_host = (urlsplit(base_url).hostname or "").lower()
    result = DiscoveryResult(source_id=source_id)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-NZ,en;q=0.9"})
    try:
        response = session.get(base_url, timeout=SOURCE_TIMEOUT_SECONDS, allow_redirects=True)
        response.raise_for_status()
        result.pages_scanned += 1
        links = page_links(response.text, response.url)
        profile_urls = [url for url, _label in links if (urlsplit(url).hostname or "").lower() == base_host and PROFILE_RE.search(urlsplit(url).path)]
        all_links = list(links)
        for profile_url in list(dict.fromkeys(profile_urls))[:12]:
            if time.monotonic() >= deadline:
                break
            try:
                profile = session.get(profile_url, timeout=SOURCE_TIMEOUT_SECONDS, allow_redirects=True)
                profile.raise_for_status()
                result.pages_scanned += 1
                all_links.extend(page_links(profile.text, profile.url))
                time.sleep(min(float(definition.get("crawl_delay", 2)), 1.0))
            except requests.RequestException:
                continue

        sites: dict[str, DiscoveredDealer] = {}
        for url, label in all_links:
            host = (urlsplit(url).hostname or "").lower()
            if not host or host == base_host or host.endswith(f".{base_host}"):
                continue
            root = canonical_url(f"https://{host}/")
            sites[root] = DiscoveredDealer(
                source_id=source_id,
                dealer_name=label or host.split(".")[0].replace("-", " ").title(),
                inventory_url=root,
                domain=host,
            )
        result.sites = list(sites.values())
        if not result.sites:
            result.status = "EMPTY"
            result.error = "No external dealer inventory websites were discoverable from the public page."
    except requests.RequestException as error:
        result.status = "FAILED"
        result.error = clean_text(error)[:1000]
    return result
