"""Vehicle-field extraction and normalization."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from hashlib import sha1
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SPACE_RE = re.compile(r"\s+")
YEAR_RE = re.compile(r"\b(19[7-9]\d|20[0-3]\d)\b")
PRICE_RE = re.compile(r"(?i)(?:NZD\s*)?\$\s*([1-9]\d{0,2}(?:[,.]\d{3})*(?:\.\d{1,2})?|[1-9]\d{3,6})")
KM_RE = re.compile(
    r"(?i)\b(?:(\d{1,3}(?:[,.]\d{3})+|\d{4,6}|\d{1,3}(?:\.\d+)?)\s*"
    r"(?:km|kms|kilometres?)|(\d{1,3}(?:\.\d+)?)\s*k)\b"
)
FINANCE_RE = re.compile(r"(?i)(?:per\s*(?:week|wk)|weekly|p/w|deposit|finance\s+from|\$\s*\d+\s*/\s*wk)")
POA_RE = re.compile(r"(?i)\b(?:POA|price\s+on\s+application|enquire\s+for\s+price)\b")
EXCLUDED_RE = re.compile(r"(?i)\b(?:wreck(?:ed|ing)?|dismantl(?:e|ing)|parts?\s+only|deposit|per\s+week|weekly|lease\s+payment|current\s+bid)\b")

MAKE_ALIASES = {
    "vw": "Volkswagen", "volkswagon": "Volkswagen", "mercedes-benz": "Mercedes-Benz",
    "mercedes": "Mercedes-Benz", "beemer": "BMW", "bimmer": "BMW", "nisaan": "Nissan",
    "toyata": "Toyota", "mitsibishi": "Mitsubishi", "hyndai": "Hyundai",
}
KNOWN_MAKES = [
    "Alfa Romeo", "Audi", "BMW", "BYD", "Chevrolet", "Chrysler", "Citroen", "Daihatsu",
    "Dodge", "Fiat", "Ford", "Great Wall", "Haval", "Holden", "Honda", "Hyundai", "Infiniti",
    "Isuzu", "Jaguar", "Jeep", "Kia", "Land Rover", "Lexus", "Mazda", "Mercedes-Benz", "Mini",
    "Mitsubishi", "Nissan", "Opel", "Peugeot", "Porsche", "Renault", "Saab", "Skoda", "Subaru",
    "Suzuki", "Tesla", "Toyota", "Vauxhall", "Volkswagen", "Volvo",
]
REGIONS = {
    "auckland": "Auckland", "northland": "Northland", "waikato": "Waikato", "bay of plenty": "Bay of Plenty",
    "gisborne": "Gisborne", "hawke's bay": "Hawke's Bay", "hawkes bay": "Hawke's Bay",
    "taranaki": "Taranaki", "manawatu": "Manawatu-Whanganui", "whanganui": "Manawatu-Whanganui",
    "wellington": "Wellington", "nelson": "Nelson-Tasman", "tasman": "Nelson-Tasman",
    "marlborough": "Marlborough", "west coast": "West Coast", "canterbury": "Canterbury",
    "christchurch": "Canterbury", "otago": "Otago", "dunedin": "Otago", "southland": "Southland",
}


@dataclass
class NormalizedVehicle:
    title: str
    year: int | None = None
    make: str | None = None
    model: str | None = None
    variant: str | None = None
    kms: int | None = None
    transmission: str | None = None
    fuel_type: str | None = None
    body_type: str | None = None
    region: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clean_text(value: Any) -> str:
    return SPACE_RE.sub(" ", str(value or "")).strip()


def normalize_token(value: str | None) -> str | None:
    cleaned = clean_text(value).lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned).strip()
    return cleaned or None


def normalize_make(value: str | None) -> str | None:
    token = normalize_token(value)
    if not token:
        return None
    alias = MAKE_ALIASES.get(token)
    if alias:
        return alias
    for make in KNOWN_MAKES:
        if normalize_token(make) == token:
            return make
    return clean_text(value).title()


def detect_make(text: str) -> tuple[str | None, tuple[int, int] | None]:
    lowered = text.lower()
    candidates = [*KNOWN_MAKES, *MAKE_ALIASES.keys()]
    for candidate in sorted(candidates, key=len, reverse=True):
        match = re.search(rf"\b{re.escape(candidate.lower())}\b", lowered)
        if match:
            return normalize_make(candidate), match.span()
    return None, None


def normalize_model(value: str | None, make: str | None = None) -> str | None:
    token = clean_text(value)
    if not token:
        return None
    token = re.split(r"\s*[|$]\s*|\s+-\s+", token, maxsplit=1)[0]
    token = YEAR_RE.sub("", token)
    token = re.split(
        r"(?i)\b(?:auto(?:matic)?|manual|petrol|diesel|hybrid|hatch(?:back)?|sedan|wagon|"
        r"suv|ute|van|km|kms|odometer|for\s+sale|auckland|wof|rego)\b",
        token,
    )[0]
    token = re.sub(r"[^A-Za-z0-9.+-]+", " ", token).strip(" -")
    token = " ".join(token.split()[:4])
    if make and normalize_token(token) == normalize_token(make):
        return None
    return token[:120] or None


def parse_kms(value: Any) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        kms = round(float(value))
        return kms if 100 <= kms <= 2_000_000 else None
    text = clean_text(value).lower().replace(",", "")
    match = KM_RE.search(text)
    if not match:
        return None
    number = (match.group(1) or match.group(2)).replace(",", "")
    try:
        kms = round(float(number) * 1000) if match.group(2) else round(float(number))
    except ValueError:
        return None
    return kms if 100 <= kms <= 2_000_000 else None


def parse_price_cents(value: Any) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        amount = float(value)
        if 500 <= amount <= 10_000_000:
            return round(amount * 100)
    text = clean_text(value)
    if not text or POA_RE.search(text) or FINANCE_RE.search(text):
        return None
    if re.fullmatch(r"\d{3,8}(?:\.\d{1,2})?", text.replace(",", "")):
        amount = float(text.replace(",", ""))
        return round(amount * 100) if 500 <= amount <= 10_000_000 else None
    matches = PRICE_RE.findall(text)
    for raw in matches:
        normalized = raw.replace(",", "")
        try:
            amount = float(normalized)
        except ValueError:
            continue
        if 500 <= amount <= 10_000_000:
            return round(amount * 100)
    return None


def normalize_transmission(value: str | None) -> str | None:
    text = normalize_token(value)
    if not text:
        return None
    if "cvt" in text:
        return "CVT"
    if "manual" in text:
        return "MANUAL"
    if "automatic" in text or re.search(r"\bauto\b", text):
        return "AUTOMATIC"
    return None


def normalize_fuel(value: str | None) -> str | None:
    text = normalize_token(value)
    if not text:
        return None
    for needle, result in (("plug in hybrid", "PHEV"), ("hybrid", "HYBRID"), ("electric", "ELECTRIC"), ("diesel", "DIESEL"), ("petrol", "PETROL"), ("lpg", "LPG")):
        if needle in text:
            return result
    return None


def normalize_body(value: str | None) -> str | None:
    text = normalize_token(value)
    if not text:
        return None
    mapping = {"hatch": "HATCHBACK", "hatchback": "HATCHBACK", "station wagon": "WAGON", "wagon": "WAGON", "sedan": "SEDAN", "suv": "SUV", "rv suv": "SUV", "ute": "UTE", "pickup": "UTE", "van": "VAN", "coupe": "COUPE", "convertible": "CONVERTIBLE", "people mover": "PEOPLE_MOVER"}
    for needle, result in mapping.items():
        if needle in text:
            return result
    return None


def normalize_region(value: str | None) -> str | None:
    text = normalize_token(value)
    if not text:
        return None
    for needle, region in REGIONS.items():
        if needle in text:
            return region
    return clean_text(value).title()


def vehicle_from_text(title: str, extra_text: str = "", supplied: dict[str, Any] | None = None) -> NormalizedVehicle:
    supplied = supplied or {}
    combined = clean_text(f"{title} {extra_text}")
    year_match = YEAR_RE.search(combined)
    year = int(year_match.group(1)) if year_match else supplied.get("year")
    make = normalize_make(supplied.get("make"))
    span = None
    if not make:
        make, span = detect_make(combined)
    model = normalize_model(supplied.get("model"), make)
    if not model and make:
        if span is None:
            match = re.search(rf"\b{re.escape(make)}\b", combined, re.I)
            span = match.span() if match else None
        if span:
            identity_text = clean_text(title) if make.lower() in clean_text(title).lower() else combined
            identity_match = re.search(rf"\b{re.escape(make)}\b", identity_text, re.I)
            tail = identity_text[identity_match.end():] if identity_match else combined[span[1]:]
            tail = YEAR_RE.sub("", tail).strip(" -|,")
            model = normalize_model(" ".join(tail.split()[:4]), make)
    transmission = normalize_transmission(supplied.get("transmission") or combined)
    fuel_type = normalize_fuel(supplied.get("fuel_type") or supplied.get("fuelType") or combined)
    body_type = normalize_body(supplied.get("body_type") or supplied.get("bodyType") or combined)
    region = normalize_region(supplied.get("region") or combined)
    kms = supplied.get("kms") if isinstance(supplied.get("kms"), int) else parse_kms(combined)
    return NormalizedVehicle(
        title=clean_text(title), year=year, make=make, model=model,
        variant=clean_text(supplied.get("variant")) or None, kms=kms,
        transmission=transmission, fuel_type=fuel_type, body_type=body_type, region=region,
    )


def canonical_url(url: str) -> str:
    parts = urlsplit(clean_text(url))
    path = re.sub(r"/+", "/", parts.path).rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower() or "https", parts.netloc.lower(), path, "", ""))


def source_listing_id(url: str) -> str:
    path = urlsplit(url).path
    numbers = re.findall(r"\d{5,}", path)
    return numbers[-1] if numbers else sha1(canonical_url(url).encode()).hexdigest()[:24]


def is_full_cash_vehicle(text: str, price_cents: int | None) -> tuple[bool, str | None]:
    cleaned = clean_text(text)
    if price_cents is None or price_cents <= 0:
        return False, "missing_full_price"
    if FINANCE_RE.search(cleaned):
        return False, "finance_or_payment_price"
    if EXCLUDED_RE.search(cleaned):
        return False, "excluded_listing_type"
    return True, None
