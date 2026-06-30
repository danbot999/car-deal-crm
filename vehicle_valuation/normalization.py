"""Conservative NZ vehicle-field extraction and canonicalization."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from hashlib import sha1
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SPACE_RE = re.compile(r"\s+")
YEAR_RE = re.compile(r"\b(19[7-9]\d|20[0-3]\d)\b")
PRICE_RE = re.compile(
    r"(?i)(?:NZD\s*)?\$\s*([1-9]\d{0,2}(?:[,.]\d{3})*(?:\.\d{1,2})?|[1-9]\d{3,6})"
)
KM_RE = re.compile(
    r"(?i)\b(?:(\d{1,3}(?:[,.]\d{3})+|\d{4,7}|\d{1,3}(?:\.\d+)?)\s*"
    r"(?:km|kms|kilometres?)|(\d{1,3}(?:\.\d+)?)\s*k)\b"
)
FINANCE_RE = re.compile(
    r"(?i)(?:per\s*(?:week|wk)|weekly|p/w|\$\s*\d+(?:\.\d+)?\s*/\s*wk|finance\s+from)"
)
CASH_LABEL_RE = re.compile(
    r"(?i)\b(?:asking\s+price|cash\s+price|buy\s+now|drive\s*away|or\s+near\s+offer|ono|fixed\s+price)\b"
)
POA_RE = re.compile(r"(?i)\b(?:POA|price\s+on\s+application|enquire\s+for\s+price)\b")
EXCLUDED_RE = re.compile(
    r"(?i)\b(?:wreck(?:ed|ing)?|dismantl(?:e|ing)|parts?\s+only|lease\s+payment|current\s+bid)\b"
)

MAKE_ALIASES = {
    "vw": "Volkswagen",
    "volkswagon": "Volkswagen",
    "mercedes benz": "Mercedes-Benz",
    "mercedes": "Mercedes-Benz",
    "beemer": "BMW",
    "bimmer": "BMW",
    "nisaan": "Nissan",
    "nissian": "Nissan",
    "toyata": "Toyota",
    "mazada": "Mazda",
    "mazada": "Mazda",
    "mitshibushi": "Mitsubishi",
    "mitsibishi": "Mitsubishi",
    "hyndai": "Hyundai",
}
KNOWN_MAKES = [
    "Alfa Romeo", "Audi", "BMW", "BYD", "Chevrolet", "Chrysler", "Citroen", "Daihatsu",
    "Dodge", "Fiat", "Ford", "Great Wall", "Haval", "Holden", "Honda", "Hyundai", "Infiniti",
    "Isuzu", "Jaguar", "Jeep", "Kia", "Land Rover", "Lexus", "Mazda", "Mercedes-Benz", "Mini",
    "Mitsubishi", "Nissan", "Opel", "Peugeot", "Porsche", "Renault", "Saab", "Skoda", "Subaru",
    "Suzuki", "Tesla", "Toyota", "Vauxhall", "Volkswagen", "Volvo",
]
REGIONS = {
    "auckland": "Auckland", "northland": "Northland", "waikato": "Waikato",
    "bay of plenty": "Bay of Plenty", "gisborne": "Gisborne", "hawke s bay": "Hawke's Bay",
    "taranaki": "Taranaki", "manawatu": "Manawatu-Whanganui",
    "whanganui": "Manawatu-Whanganui", "wellington": "Wellington",
    "nelson": "Nelson-Tasman", "tasman": "Nelson-Tasman", "marlborough": "Marlborough",
    "west coast": "West Coast", "canterbury": "Canterbury", "christchurch": "Canterbury",
    "otago": "Otago", "dunedin": "Otago", "southland": "Southland",
}

# Longer aliases are tested first. Canonical models deliberately exclude trim text.
MODEL_CATALOG: dict[str, dict[str, str]] = {
    "Subaru": {"legacy": "Legacy", "outback": "Outback", "impreza": "Impreza", "imprezza": "Impreza", "forester": "Forester", "exiga": "Exiga", "levorg": "Levorg", "brz": "BRZ", "xv": "XV"},
    "Suzuki": {"grand vitara": "Grand Vitara", "swift": "Swift", "alto": "Alto", "splash": "Splash", "sx4": "SX4", "jimny": "Jimny", "vitara": "Vitara", "kizashi": "Kizashi"},
    "Mazda": {"mazda 6": "Atenza", "mazda6": "Atenza", "atenza": "Atenza", "mazda 3": "Axela", "mazda3": "Axela", "axela": "Axela", "mazda 2": "Demio", "mazda2": "Demio", "demio": "Demio", "cx 5": "CX-5", "cx5": "CX-5", "premacy": "Premacy", "verisa": "Verisa", "biante": "Biante", "rx 8": "RX-8", "mpv": "MPV"},
    "Toyota": {"land cruiser": "Land Cruiser", "mark x": "Mark X", "corolla fielder": "Corolla Fielder", "corolla": "Corolla", "aqua": "Aqua", "prius": "Prius", "camry": "Camry", "auris": "Auris", "vitz": "Vitz", "yaris": "Yaris", "estima": "Estima", "alphard": "Alphard", "wish": "Wish", "rav4": "RAV4", "highlander": "Highlander", "hiace": "Hiace", "hilux": "Hilux", "blade": "Blade", "vanguard": "Vanguard", "runx": "RunX", "allex": "Allex", "allion": "Allion", "belta": "Belta"},
    "Nissan": {"bluebird sylphy": "Bluebird Sylphy", "bluebird": "Bluebird", "tiida latio": "Tiida Latio", "x trail": "X-Trail", "xtrail": "X-Trail", "tiida": "Tiida", "note": "Note", "march": "March", "serena": "Serena", "skyline": "Skyline", "fuga": "Fuga", "teana": "Teana", "dualis": "Dualis", "qashqai": "Qashqai", "leaf": "Leaf", "navara": "Navara", "laurel": "Laurel"},
    "Honda": {"crossroad": "Crossroad", "crossroda": "Crossroad", "civic": "Civic", "accord": "Accord", "fit": "Fit", "jazz": "Fit", "odyssey": "Odyssey", "stream": "Stream", "cr v": "CR-V", "crv": "CR-V", "insight": "Insight", "freed": "Freed", "stepwagon": "Stepwagon"},
    "Mitsubishi": {"l200": "L200", "sigma": "Sigma", "outlander": "Outlander", "lancer": "Lancer", "colt": "Colt", "asx": "ASX", "pajero": "Pajero", "triton": "Triton", "delica": "Delica", "mirage": "Mirage"},
    "Volkswagen": {"passat": "Passat", "touareg": "Touareg", "tiguan": "Tiguan", "polo": "Polo", "golf": "Golf", "jetta": "Jetta", "amarok": "Amarok"},
    "Holden": {"commodore": "Commodore", "captiva": "Captiva", "cruze": "Cruze", "astra": "Astra", "barina": "Barina", "colorado": "Colorado"},
    "Ford": {"falcon": "Falcon", "territory": "Territory", "focus": "Focus", "mondeo": "Mondeo", "ranger": "Ranger", "fiesta": "Fiesta", "escape": "Escape", "kuga": "Kuga"},
    "BMW": {"series 1": "1 Series", "1 series": "1 Series", "series 3": "3 Series", "3 series": "3 Series", "series 5": "5 Series", "5 series": "5 Series", "series 7": "7 Series", "7 series": "7 Series", "x1": "X1", "x3": "X3", "x5": "X5", "x6": "X6", "z4": "Z4"},
    "Mercedes-Benz": {"c class": "C-Class", "e class": "E-Class", "a class": "A-Class", "b class": "B-Class", "s class": "S-Class", "ml class": "M-Class", "m class": "M-Class", "cla": "CLA", "glc": "GLC", "gle": "GLE"},
    "Audi": {"a1": "A1", "a3": "A3", "a4": "A4", "a5": "A5", "a6": "A6", "a7": "A7", "a8": "A8", "q2": "Q2", "q3": "Q3", "q5": "Q5", "q7": "Q7", "q8": "Q8", "tt": "TT"},
    "Lexus": {"is250": "IS 250", "is 250": "IS 250", "gs300": "GS 300", "gs 300": "GS 300", "rx350": "RX 350", "rx 350": "RX 350", "ct200h": "CT 200h", "ct 200h": "CT 200h", "ls460": "LS 460", "ls 460": "LS 460"},
    "Hyundai": {"santa fe": "Santa Fe", "i30": "i30", "i45": "i45", "elantra": "Elantra", "sonata": "Sonata", "tucson": "Tucson", "accent": "Accent", "getz": "Getz", "veloster": "Veloster"},
    "Kia": {"sportage": "Sportage", "sorento": "Sorento", "cerato": "Cerato", "rio": "Rio", "optima": "Optima", "carnival": "Carnival", "soul": "Soul"},
    "Peugeot": {"107": "107", "206": "206", "207": "207", "208": "208", "307": "307", "308": "308", "407": "407", "508": "508", "3008": "3008", "5008": "5008"},
    "Volvo": {"v40": "V40", "v50": "V50", "v60": "V60", "v70": "V70", "s40": "S40", "s60": "S60", "s80": "S80", "xc60": "XC60", "xc70": "XC70", "xc90": "XC90"},
    "Daihatsu": {"sirion": "Sirion", "terios": "Terios", "materia": "Materia", "mira": "Mira", "move": "Move"},
    "Isuzu": {"d max": "D-Max", "dmax": "D-Max", "mu x": "MU-X", "mux": "MU-X", "bighorn": "Bighorn"},
    "Land Rover": {"range rover sport": "Range Rover Sport", "range rover": "Range Rover", "discovery": "Discovery", "freelander": "Freelander", "defender": "Defender"},
    "Mini": {"countryman": "Countryman", "clubman": "Clubman", "cooper": "Cooper", "one": "One"},
    "Jaguar": {"x type": "X-Type", "s type": "S-Type", "xf": "XF", "xj": "XJ", "xe": "XE", "f pace": "F-Pace"},
    "Jeep": {"grand cherokee": "Grand Cherokee", "cherokee": "Cherokee", "wrangler": "Wrangler", "compass": "Compass", "patriot": "Patriot"},
    "Porsche": {"cayenne": "Cayenne", "macan": "Macan", "panamera": "Panamera", "boxster": "Boxster", "cayman": "Cayman", "911": "911"},
    "Skoda": {"superb": "Superb", "octavia": "Octavia", "fabia": "Fabia", "rapid": "Rapid", "yeti": "Yeti", "kodiaq": "Kodiaq", "kamiq": "Kamiq", "karroq": "Karoq"},
}

SHORTHAND_MODELS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\bswift\b", re.I), "Suzuki", "Swift"),
    (re.compile(r"\bmpv\b", re.I), "Mazda", "MPV"),
    (re.compile(r"\b(?:3[1-3]\d|m3)[dix]{0,2}\b", re.I), "BMW", "3 Series"),
    (re.compile(r"\b(?:5[1-5]\d|m5)[dix]{0,2}\b", re.I), "BMW", "5 Series"),
    (re.compile(r"\bvs\s+commodore\b|\bcommodore\b", re.I), "Holden", "Commodore"),
]

TRIM_RE = re.compile(
    r"(?i)\b(?:black\s+edition|limited|sport|sports|turbo|gt|gts|sti|wrx|gx|glx|lx|rs|"
    r"type\s+r|m[-\s]*sport|highline|comfortline|trendline|4wd|awd|manual|automatic|diesel|petrol|hybrid)\b"
)
PERFORMANCE_RE = re.compile(
    r"(?i)\b(?:mazdaspeed|mps|wrx|sti|type\s*r|gti|gtd|r32|rs3|rs4|rs5|rs6|"
    r"amg|evo(?:lution)?|srt|svt|nismo|m[1-8]|turbo\s+sport)\b"
)
HYBRID_RE = re.compile(r"(?i)\b(?:hybrid|phev|plug[ -]?in)\b")
ELECTRIC_RE = re.compile(r"(?i)\b(?:electric|bev|ev)\b")
DIESEL_RE = re.compile(r"(?i)\b(?:diesel|tdi|crdi|cdi|d4d)\b")
ENGINE_CC_RE = re.compile(r"(?i)\b(\d{3,4})\s*cc\b")
ENGINE_LITRE_RE = re.compile(r"(?i)\b([1-6](?:\.\d)?)\s*(?:l|litre|liter)\b")
BMW_BADGE_RE = re.compile(
    r"(?i)\b(m[1-8]|[1-8][1-8]\d\s*(?:l\s*)?(?:d|i|e|xi|xd|ci|is))\b"
)

MODEL_YEAR_BOUNDS: dict[tuple[str, str], tuple[int, int | None]] = {
    ("mazda", "axela"): (2003, None),
    ("mazda", "atenza"): (2002, None),
    ("nissan", "leaf"): (2010, None),
    ("toyota", "aqua"): (2011, None),
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
    if token in MAKE_ALIASES:
        return MAKE_ALIASES[token]
    for make in KNOWN_MAKES:
        if normalize_token(make) == token:
            return make
    return None


def detect_make(text: str) -> tuple[str | None, tuple[int, int] | None]:
    lowered = normalize_token(text) or ""
    candidates = [*KNOWN_MAKES, *MAKE_ALIASES]
    for candidate in sorted(candidates, key=len, reverse=True):
        token = normalize_token(candidate) or ""
        match = re.search(rf"\b{re.escape(token)}\b", lowered)
        if match:
            return normalize_make(candidate), match.span()
    for pattern, make, _model in SHORTHAND_MODELS:
        match = pattern.search(text)
        if match:
            return make, match.span()
    return None, None


def catalog_model(text: str, make: str | None) -> str | None:
    normalized = normalize_token(text) or ""
    if make:
        for alias, canonical in sorted(MODEL_CATALOG.get(make, {}).items(), key=lambda item: len(item[0]), reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", normalized):
                return canonical
    for pattern, inferred_make, model in SHORTHAND_MODELS:
        if (not make or make == inferred_make) and pattern.search(text):
            return model
    if make == "BMW":
        match = BMW_BADGE_RE.search(text)
        if match:
            badge = normalize_bmw_badge(match.group(1))
            if badge.startswith("m") and len(badge) == 2 and badge[1].isdigit():
                return f"{badge[1]} Series"
            return f"{badge[0]} Series"
    if make == "Mercedes-Benz":
        match = re.search(r"\b([abcegms])\s*[- ]?(\d{2,3})\b", normalized, re.I)
        if match:
            return f"{match.group(1).upper()}-Class"
    return None


def normalize_bmw_badge(value: str | None) -> str:
    badge = re.sub(r"[^a-zA-Z0-9]+", "", clean_text(value)).lower()
    long_wheelbase = re.fullmatch(r"([1-8][1-8]\d)l([die])", badge)
    if long_wheelbase:
        return f"{long_wheelbase.group(1)}{long_wheelbase.group(2)}"
    return badge


def detect_bmw_badge(text: str) -> str | None:
    match = BMW_BADGE_RE.search(text)
    return normalize_bmw_badge(match.group(1)) if match else None


def model_year_is_plausible(vehicle: NormalizedVehicle) -> bool:
    if vehicle.year is None:
        return False
    key = (normalize_token(vehicle.make) or "", normalize_token(vehicle.model) or "")
    bounds = MODEL_YEAR_BOUNDS.get(key)
    if not bounds:
        return 1970 <= vehicle.year <= datetime_now_year() + 1
    minimum, maximum = bounds
    return vehicle.year >= minimum and (maximum is None or vehicle.year <= maximum)


def datetime_now_year() -> int:
    # Kept local to avoid making model normalization dependent on system locale.
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).year


def price_family(value: NormalizedVehicle | Any) -> str:
    make = normalize_token(getattr(value, "make", None)) or ""
    model = normalize_token(getattr(value, "model", None)) or ""
    variant = clean_text(getattr(value, "variant", None))
    title = clean_text(getattr(value, "title", None))
    fuel = normalize_token(getattr(value, "fuel_type", None)) or ""
    combined = clean_text(f"{title} {variant} {fuel}")
    if make == "bmw" and model.endswith("series"):
        badge = detect_bmw_badge(combined)
        if badge:
            return f"BMW_BADGE:{badge}"
    if PERFORMANCE_RE.search(combined):
        return "PERFORMANCE"
    if ELECTRIC_RE.search(combined) or fuel == "electric":
        return "ELECTRIC"
    if HYBRID_RE.search(combined) or fuel == "hybrid":
        return "HYBRID"
    if DIESEL_RE.search(combined) or fuel == "diesel":
        return "DIESEL"
    return "STANDARD"


def engine_capacity_band(value: NormalizedVehicle | Any) -> int | None:
    combined = clean_text(
        f"{getattr(value, 'title', '')} {getattr(value, 'variant', '')}"
    )
    cc_match = ENGINE_CC_RE.search(combined)
    if cc_match:
        cc = int(cc_match.group(1))
    else:
        litre_match = ENGINE_LITRE_RE.search(combined)
        if not litre_match:
            return None
        cc = round(float(litre_match.group(1)) * 1000)
    if not 600 <= cc <= 8000:
        return None
    return round(cc / 250) * 250


def normalize_model(value: str | None, make: str | None = None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    known = catalog_model(text, make)
    if known:
        return known
    text = YEAR_RE.sub(" ", text)
    if make:
        text = re.sub(rf"(?i)\b{re.escape(make)}\b", " ", text)
    text = re.split(r"\s*[|$]\s*|\s+-\s+", text, maxsplit=1)[0]
    text = re.split(
        r"(?i)\b(?:auto(?:matic)?|manual|petrol|diesel|hybrid|electric|hatch(?:back)?|sedan|wagon|"
        r"suv|ute|van|km|kms|odometer|for\s+sale|auckland|wof|rego|edition|price|low|high|tidy|cheap|special)\b",
        text,
        maxsplit=1,
    )[0]
    text = re.sub(r"[^A-Za-z0-9.+-]+", " ", text).strip(" -")
    text = " ".join(text.split()[:3])
    if not text or (make and normalize_token(text) == normalize_token(make)):
        return None
    return text[:120].title()


def detect_variant(title: str, model: str | None, supplied: str | None = None) -> str | None:
    if clean_text(supplied):
        return clean_text(supplied)[:220]
    if model and (normalize_token(model) or "").endswith("series"):
        badge = detect_bmw_badge(title)
        if badge:
            return badge
    parenthetical = re.search(r"\(([^)]{2,60})\)", title)
    if parenthetical and not YEAR_RE.fullmatch(parenthetical.group(1).strip()):
        return clean_text(parenthetical.group(1))
    if model:
        model_match = re.search(re.escape(model), title, re.I)
        tail = title[model_match.end():] if model_match else title
        matches = [clean_text(match.group(0)) for match in TRIM_RE.finditer(tail)]
        if matches:
            return " ".join(dict.fromkeys(matches))[:220]
    return None


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
        return round(amount * 100) if 500 <= amount <= 10_000_000 else None
    text = clean_text(value)
    if not text or POA_RE.search(text):
        return None
    plain = text.replace(",", "")
    if re.fullmatch(r"\d{3,8}(?:\.\d{1,2})?", plain):
        amount = float(plain)
        return round(amount * 100) if 500 <= amount <= 10_000_000 else None
    amounts: list[float] = []
    for raw in PRICE_RE.findall(text):
        try:
            amount = float(raw.replace(",", ""))
        except ValueError:
            continue
        if 500 <= amount <= 10_000_000:
            amounts.append(amount)
    if not amounts:
        return None
    if FINANCE_RE.search(text) and not CASH_LABEL_RE.search(text) and len(amounts) == 1:
        return None
    return round(max(amounts) * 100)


def normalize_transmission(value: str | None) -> str | None:
    text = normalize_token(value)
    if not text:
        return None
    if re.search(r"\bcvt\b", text):
        return "CVT"
    if re.search(r"\bmanual\b|\b[56]\s*speed\s*manual\b", text):
        return "MANUAL"
    if re.search(r"\bautomatic\b|\bauto\b", text):
        return "AUTOMATIC"
    return None


def normalize_fuel(value: str | None) -> str | None:
    text = normalize_token(value)
    if not text:
        return None
    if re.search(r"\bplug in hybrid\b|\bphev\b", text):
        return "PHEV"
    if re.search(r"\bhybrid\b", text):
        return "HYBRID"
    if re.search(r"\b(?:fully electric|electric vehicle|battery electric|bev|ev)\b", text):
        return "ELECTRIC"
    if re.search(r"\bdiesel\b", text):
        return "DIESEL"
    if re.search(r"\bpetrol\b|\bgasoline\b", text):
        return "PETROL"
    if re.search(r"\blpg\b", text):
        return "LPG"
    return None


def normalize_body(value: str | None) -> str | None:
    text = normalize_token(value)
    if not text:
        return None
    mapping = {
        "people mover": "PEOPLE_MOVER", "station wagon": "WAGON", "hatchback": "HATCHBACK",
        "hatch": "HATCHBACK", "wagon": "WAGON", "sedan": "SEDAN", "suv": "SUV",
        "ute": "UTE", "pickup": "UTE", "van": "VAN", "coupe": "COUPE",
        "convertible": "CONVERTIBLE",
    }
    for needle, result in mapping.items():
        if re.search(rf"\b{re.escape(needle)}\b", text):
            return result
    return None


def normalize_region(value: str | None) -> str | None:
    text = normalize_token(value)
    if not text:
        return None
    for needle, region in REGIONS.items():
        if re.search(rf"\b{re.escape(needle)}\b", text):
            return region
    return None


def vehicle_from_text(title: str, extra_text: str = "", supplied: dict[str, Any] | None = None) -> NormalizedVehicle:
    supplied = supplied or {}
    clean_title = clean_text(title)
    combined = clean_text(f"{clean_title} {extra_text}")
    title_year = YEAR_RE.search(clean_title)
    supplied_year = supplied.get("year") if isinstance(supplied.get("year"), int) else None
    labelled_year = re.search(r"(?i)\b(?:model\s+year|year|first\s+registered)\s*[:=-]?\s*(19[7-9]\d|20[0-3]\d)\b", extra_text)
    year = int(title_year.group(1)) if title_year else supplied_year or (int(labelled_year.group(1)) if labelled_year else None)

    title_make, _span = detect_make(clean_title)
    make = title_make or normalize_make(supplied.get("make"))
    model = catalog_model(clean_title, make)
    if not model:
        model = normalize_model(supplied.get("model"), make)
    if not make or not model:
        for pattern, inferred_make, inferred_model in SHORTHAND_MODELS:
            if pattern.search(clean_title):
                make = make or inferred_make
                model = model or inferred_model
                break
    if not model and make:
        make_match = re.search(rf"(?i)\b{re.escape(make)}\b", clean_title)
        tail = clean_title[make_match.end():] if make_match else clean_title
        model = normalize_model(tail, make)

    explicit_fuel = supplied.get("fuel_type") or supplied.get("fuelType")
    fuel_type = normalize_fuel(explicit_fuel) if explicit_fuel else normalize_fuel(combined)
    explicit_region = supplied.get("region")
    region = normalize_region(explicit_region) if explicit_region else normalize_region(combined)
    supplied_kms = supplied.get("kms")
    kms = supplied_kms if isinstance(supplied_kms, int) and 100 <= supplied_kms <= 2_000_000 else parse_kms(combined)
    variant_source = combined if make == "BMW" and model and (normalize_token(model) or "").endswith("series") else clean_title
    variant = detect_variant(variant_source, model, supplied.get("variant"))
    return NormalizedVehicle(
        title=clean_title,
        year=year,
        make=make,
        model=model,
        variant=variant,
        kms=kms,
        transmission=normalize_transmission(supplied.get("transmission") or combined),
        fuel_type=fuel_type,
        body_type=normalize_body(supplied.get("body_type") or supplied.get("bodyType") or combined),
        region=region,
    )


def identity_key(vehicle: NormalizedVehicle) -> str | None:
    make = normalize_token(vehicle.make)
    model = normalize_token(vehicle.model)
    if not make or not model:
        return None
    year = str(vehicle.year) if vehicle.year else "unknown"
    family = normalize_token(price_family(vehicle)) or "standard"
    if family.startswith("bmw badge "):
        family = family.removeprefix("bmw badge ")
    engine = engine_capacity_band(vehicle)
    parts = [year, make, model, family]
    if engine:
        parts.append(str(engine))
    return "|".join(parts)


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
    if EXCLUDED_RE.search(cleaned):
        return False, "excluded_listing_type"
    if FINANCE_RE.search(cleaned) and not CASH_LABEL_RE.search(cleaned):
        return False, "finance_or_payment_price"
    if re.search(r"(?i)\b(?:auction|reserve)\b", cleaned) and not re.search(r"(?i)\bbuy\s+now\b", cleaned):
        return False, "auction_without_buy_now"
    return True, None
