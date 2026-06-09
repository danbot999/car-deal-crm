"""Run Trade Me Value My Car automation for CRM listings."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
import sys
import time
import tempfile
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from PIL import Image, ImageFilter, ImageOps
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from rapidocr_onnxruntime import RapidOCR


ROOT = Path(__file__).resolve().parents[2]
CRM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import MODERN_USER_AGENT  # noqa: E402


CRM_DB = CRM_ROOT / "prisma" / "dev.db"
IMAGE_ROOT = CRM_ROOT / "public"
DETAIL_IMAGE_DIR = IMAGE_ROOT / "listing-images" / "detail"
TRADE_ME_PROFILE_CONFIG = CRM_ROOT / "work" / "trademe-profile.json"
DEFAULT_TRADE_ME_CHANNEL = "msedge"
TRADE_ME_VALUE_URL = "https://www.trademe.co.nz/a/value-my-car"
SOURCE_NAME = "TRADE_ME_VALUE_MY_CAR"
DESCRIPTION_LIMIT = 12_000
MAX_DETAIL_IMAGES = 40
GALLERY_ADVANCE_STEPS = 24
IMAGE_DOWNLOAD_TIMEOUT_SECONDS = 20
OCR_BUDGET_SECONDS = 75

SPACE_PATTERN = re.compile(r"\s+")
PLATE_CUE_PATTERN = re.compile(
    r"(?i)\b(?:number\s*plate|licen[cs]e\s*plate|rego(?:istration)?|plate)"
    r"\s*(?:is|:|#|-)?\s*([A-Z0-9]{2,6}(?:[\s-][A-Z0-9]{1,3}){0,2})\b"
)
PLATE_STOPWORDS = {
    "AUTO",
    "CASH",
    "FRESH",
    "KM",
    "KMS",
    "NEW",
    "ONO",
    "REG",
    "REGO",
    "WOF",
    "WOFE",
}
KMS_PATTERNS = (
    re.compile(
        r"(?i)\b(?:odo(?:meter)?|kms?|kilomet(?:er|re)s?|mileage|travelled|done)"
        r"\D{0,20}(\d{1,3}(?:,\d{3})+|\d{4,6}|\d{2,3}(?:\.\d)?\s*k)\b"
    ),
    re.compile(
        r"(?i)\b(\d{1,3}(?:,\d{3})+|\d{4,6}|\d{2,3}(?:\.\d)?\s*k)"
        r"\s*(?:kms?|kilomet(?:er|re)s?)\b"
    ),
    re.compile(r"(?i)\b(\d{2,3}(?:\.\d)?\s*k)\b"),
)
PRICE_PATTERN = re.compile(r"\$\s*(\d[\d,]*(?:\.\d{1,2})?)")
HUMAN_VERIFICATION_PATTERN = re.compile(
    r"(?i)\b(captcha|verify you are human|unusual traffic|access denied|blocked)\b"
)
TRADE_ME_LOGIN_URL_PATTERN = re.compile(r"\(modal:login\)|/login\b", re.I)
TRADE_ME_NO_VALUATION_PATTERN = re.compile(
    r"(?i)(oops!\s*we\s*couldn'?t\s*find\s*a\s*valuation|"
    r"couldn'?t\s*find\s*a\s*valuation|isn'?t\s*enough\s*data\s*available)"
)
PLATE_CANDIDATE_PATTERN = re.compile(r"[A-Z0-9]{2,8}")
PREFERRED_NZ_PLATE_PATTERN = re.compile(r"^[A-Z]{3}\d{3}$")
OCR_MIN_SCORE = 72
FACEBOOK_ITEM_PATTERN = re.compile(r"/marketplace/item/(\d+)")


@dataclass
class ExtractionResult:
    number_plate: str | None
    number_plate_confidence: int | None
    kms: int | None
    kms_confidence: int | None
    description: str
    error: str | None = None


@dataclass
class ValuationResult:
    valuation_cents: int | None
    status: str
    error: str | None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: str) -> str:
    return SPACE_PATTERN.sub(" ", value).strip()


def console_text(value: str) -> str:
    encoding = sys.stdout.encoding or "utf-8"
    return clean_text(value).encode(encoding, errors="replace").decode(encoding)


def normalize_plate(candidate: str) -> str | None:
    normalized = re.sub(r"[^A-Z0-9]", "", candidate.upper())
    if not 2 <= len(normalized) <= 6:
        return None
    if normalized in PLATE_STOPWORDS:
        return None
    if normalized.isdigit() or normalized.isalpha():
        return None
    return normalized


def extract_number_plate(text: str) -> tuple[str | None, int | None]:
    for match in PLATE_CUE_PATTERN.finditer(text):
        candidate = normalize_plate(match.group(1))
        if candidate:
            return candidate, 90
    return None, None


def score_plate_candidate(plate: str, confidence: float) -> int:
    score = round(confidence * 100)
    if len(plate) == 6:
        score += 15
    if PREFERRED_NZ_PLATE_PATTERN.fullmatch(plate):
        score += 25
    if len(plate) < 5:
        score -= 20
    return max(0, min(99, score))


def plate_candidates_from_ocr_text(
    text: str,
    confidence: float,
) -> list[tuple[str, int]]:
    candidates: list[tuple[str, int]] = []
    compact_text = re.sub(r"[^A-Z0-9]+", " ", text.upper())
    for match in PLATE_CANDIDATE_PATTERN.finditer(compact_text):
        plate = normalize_plate(match.group(0))
        if plate:
            candidates.append((plate, score_plate_candidate(plate, confidence)))
    joined = compact_text.replace(" ", "")
    for match in PLATE_CANDIDATE_PATTERN.finditer(joined):
        plate = normalize_plate(match.group(0))
        if plate:
            candidates.append((plate, score_plate_candidate(plate, confidence - 0.05)))
    return candidates


def parse_manual_plate(value: str | None) -> str | None:
    if not value:
        return None
    return normalize_plate(value)


def parse_kms_value(value: str) -> int | None:
    cleaned = value.lower().replace(",", "").replace(" ", "")
    if cleaned.endswith("k"):
        kms = round(float(cleaned[:-1]) * 1000)
    else:
        kms = int(float(cleaned))
    if 1900 <= kms <= 2035:
        return None
    if 10_000 <= kms <= 500_000:
        return kms
    return None


def parse_manual_kms(value: str | None) -> int | None:
    if not value:
        return None
    return parse_kms_value(value)


def extract_kms(text: str) -> tuple[int | None, int | None]:
    for pattern in KMS_PATTERNS:
        for match in pattern.finditer(text):
            kms = parse_kms_value(match.group(1))
            if kms is not None:
                return kms, 90
    return None, None


def facebook_item_id(listing: sqlite3.Row) -> str:
    existing = str(listing["facebookItemId"] or "")
    if existing:
        return existing
    match = FACEBOOK_ITEM_PATTERN.search(urlparse(str(listing["facebookUrl"])).path)
    if match:
        return match.group(1)
    return hashlib.sha1(str(listing["facebookUrl"]).encode("utf-8")).hexdigest()[:16]


def local_thumbnail_path(listing: sqlite3.Row) -> Path | None:
    thumbnail_path = str(listing["thumbnailPath"] or "")
    if not thumbnail_path:
        return None
    candidate = (IMAGE_ROOT / thumbnail_path.lstrip("/")).resolve()
    if IMAGE_ROOT.resolve() not in candidate.parents:
        return None
    if not candidate.exists():
        return None
    return candidate


def is_probable_listing_image_url(url: str) -> bool:
    if not url.startswith("http"):
        return False
    lowered = url.lower()
    if "scontent" not in lowered and "fbcdn" not in lowered:
        return False
    if any(fragment in lowered for fragment in ("emoji", "static", "rsrc.php")):
        return False
    return True


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean_value = value.strip()
        if not clean_value or clean_value in seen:
            continue
        result.append(clean_value)
        seen.add(clean_value)
    return result


def cache_detail_images(listing: sqlite3.Row, image_urls: list[str]) -> list[Path]:
    DETAIL_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    item_id = facebook_item_id(listing)
    cached_paths: list[Path] = []

    for index, image_url in enumerate(
        dedupe_preserve_order(
            [url for url in image_urls if is_probable_listing_image_url(url)]
        )[:MAX_DETAIL_IMAGES],
        1,
    ):
        cache_key = hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:12]
        image_path = DETAIL_IMAGE_DIR / f"{item_id}-{index:02d}-{cache_key}.jpg"
        if image_path.exists() and image_path.stat().st_size > 0:
            cached_paths.append(image_path)
            continue

        try:
            response = requests.get(
                image_url,
                headers={"User-Agent": MODERN_USER_AGENT},
                timeout=IMAGE_DOWNLOAD_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            image_path.write_bytes(response.content)
            cached_paths.append(image_path)
        except requests.RequestException:
            continue

    return cached_paths


def listing_image_paths(
    listing: sqlite3.Row,
    detail_image_paths: list[Path] | None = None,
) -> list[Path]:
    paths: list[Path] = []
    thumbnail = local_thumbnail_path(listing)
    if thumbnail is not None:
        paths.append(thumbnail)
    paths.extend(detail_image_paths or [])

    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen or not resolved.exists():
            continue
        unique_paths.append(resolved)
        seen.add(resolved)
    return unique_paths


def crop_boxes(width: int, height: int) -> list[tuple[str, tuple[int, int, int, int]]]:
    def box(
        name: str,
        left: float,
        top: float,
        right: float,
        bottom: float,
    ) -> tuple[str, tuple[int, int, int, int]]:
        return (
            name,
            (
                max(0, round(width * left)),
                max(0, round(height * top)),
                min(width, round(width * right)),
                min(height, round(height * bottom)),
            ),
        )

    return [
        box("front-right-wide", 0.70, 0.53, 1.00, 0.83),
        box("front-right", 0.73, 0.57, 0.94, 0.78),
        box("front-right-tight", 0.75, 0.61, 0.90, 0.72),
        box("front-center", 0.30, 0.50, 0.76, 0.82),
        box("rear-left", 0.00, 0.50, 0.42, 0.82),
        box("lower-half", 0.0, 0.45, 1.0, 1.0),
    ]


def image_variants(image: Image.Image) -> list[tuple[str, Image.Image]]:
    variants: list[tuple[str, Image.Image]] = []
    for scale in (7, 5):
        resized = image.resize((image.width * scale, image.height * scale))
        gray = ImageOps.grayscale(resized)
        variants.append((f"{scale}x-color", resized))
        variants.append((f"{scale}x-gray", gray))
        variants.append(
            (
                f"{scale}x-contrast",
                ImageOps.autocontrast(gray).filter(ImageFilter.SHARPEN),
            )
        )
    return variants


def extract_plate_from_image(
    image_path: Path,
    engine: RapidOCR,
    deadline: float | None = None,
) -> tuple[str | None, int | None, str]:
    candidates: list[tuple[str, int, str, str]] = []
    evidence: list[str] = []

    with Image.open(image_path).convert("RGB") as image:
        with tempfile.TemporaryDirectory(prefix="crm-plate-ocr-") as temp_dir:
            for crop_name, crop_box in crop_boxes(image.width, image.height):
                if deadline is not None and time.monotonic() > deadline:
                    break
                crop = image.crop(crop_box)
                if crop.width < 20 or crop.height < 20:
                    continue
                for variant_name, variant in image_variants(crop):
                    if deadline is not None and time.monotonic() > deadline:
                        break
                    variant_path = Path(temp_dir) / f"{crop_name}-{variant_name}.png"
                    variant.save(variant_path)
                    result, _ = engine(str(variant_path))
                    if not result:
                        continue
                    for item in result:
                        text = str(item[1])
                        confidence = float(item[2])
                        evidence.append(
                            f"{crop_name}/{variant_name}: {text} ({confidence:.2f})"
                        )
                        for plate, score in plate_candidates_from_ocr_text(
                            text,
                            confidence,
                        ):
                            candidates.append((plate, score, crop_name, text))
                            if score >= 92:
                                evidence_text = (
                                    f"{crop_name}: {text}; "
                                    + "; ".join(evidence[:8])
                                )
                                return plate, score, evidence_text

    if not candidates:
        return None, None, "; ".join(evidence[:8])

    best_by_plate: dict[str, tuple[str, int, str, str]] = {}
    for candidate in candidates:
        plate = candidate[0]
        if plate not in best_by_plate or candidate[1] > best_by_plate[plate][1]:
            best_by_plate[plate] = candidate

    best = sorted(
        best_by_plate.values(),
        key=lambda candidate: (
            candidate[1],
            1 if PREFERRED_NZ_PLATE_PATTERN.fullmatch(candidate[0]) else 0,
            len(candidate[0]),
        ),
        reverse=True,
    )[0]

    plate, score, crop_name, raw_text = best
    evidence_text = f"{crop_name}: {raw_text}; " + "; ".join(evidence[:8])
    if score < OCR_MIN_SCORE:
        return None, score, evidence_text
    return plate, score, evidence_text


def extract_plate_from_listing_images(
    listing: sqlite3.Row,
    detail_image_paths: list[Path] | None = None,
) -> tuple[str | None, int | None, str]:
    image_paths = listing_image_paths(listing, detail_image_paths)
    if not image_paths:
        return None, None, "No cached listing images available for OCR."

    engine = RapidOCR()
    best_plate: str | None = None
    best_score: int | None = None
    evidence_parts: list[str] = []
    deadline = time.monotonic() + OCR_BUDGET_SECONDS

    for index, image_path in enumerate(image_paths[:MAX_DETAIL_IMAGES], 1):
        if time.monotonic() > deadline:
            evidence_parts.append("OCR image budget reached before all images were checked.")
            break
        try:
            plate, score, evidence = extract_plate_from_image(
                image_path,
                engine,
                deadline,
            )
            label = f"image {index}/{len(image_paths)} {image_path.name}"
            evidence_parts.append(f"{label}: {evidence}")
            if plate and score is not None and (best_score is None or score > best_score):
                best_plate = plate
                best_score = score
                if score >= 92:
                    break
        except Exception as error:
            evidence_parts.append(f"{image_path.name}: OCR failed: {error}")

    return best_plate, best_score, " | ".join(evidence_parts)[:DESCRIPTION_LIMIT]


def calculate_deal_metrics(
    valuation_cents: int,
    asking_price_cents: int,
) -> tuple[int, int, int]:
    target_sell_price_cents = round(valuation_cents * 0.80)
    max_buy_price_cents = target_sell_price_cents - 100_000
    estimated_profit_cents = target_sell_price_cents - asking_price_cents
    return target_sell_price_cents, max_buy_price_cents, estimated_profit_cents


def trade_me_profile_dir(channel: str | None) -> Path:
    suffix = channel or "chromium"
    return CRM_ROOT / "work" / f"trademe-profile-{suffix}"


def read_trade_me_profile_config() -> dict[str, str]:
    if not TRADE_ME_PROFILE_CONFIG.exists():
        return {}
    try:
        data = json.loads(TRADE_ME_PROFILE_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {key: str(value) for key, value in data.items() if value is not None}


def write_trade_me_profile_config(channel: str | None) -> None:
    profile_dir = trade_me_profile_dir(channel)
    TRADE_ME_PROFILE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    TRADE_ME_PROFILE_CONFIG.write_text(
        json.dumps(
            {
                "channel": channel or "chromium",
                "profileDir": str(profile_dir),
                "updatedAt": now_iso(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def selected_trade_me_channel(explicit_channel: str | None) -> str | None:
    if explicit_channel:
        return None if explicit_channel == "chromium" else explicit_channel
    configured_channel = read_trade_me_profile_config().get("channel")
    if configured_channel:
        return None if configured_channel == "chromium" else configured_channel
    return DEFAULT_TRADE_ME_CHANNEL


def launch_context_options(headless: bool, channel: str | None = None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "headless": headless,
        "user_agent": MODERN_USER_AGENT,
        "viewport": {"width": 1440, "height": 1200},
        "locale": "en-NZ",
        "extra_http_headers": {"Accept-Language": "en-NZ,en;q=0.9"},
    }
    if channel:
        options["channel"] = channel
    return options


def extract_valuation_cents(text: str) -> int | None:
    amounts = [
        int(round(float(match.group(1).replace(",", "")) * 100))
        for match in PRICE_PATTERN.finditer(text)
    ]
    distinct_amounts = sorted(set(amount for amount in amounts if amount >= 100_000))
    if not distinct_amounts:
        return None
    if len(distinct_amounts) >= 2:
        return round((distinct_amounts[0] + distinct_amounts[-1]) / 2)
    return distinct_amounts[0]


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(CRM_DB)
    connection.row_factory = sqlite3.Row
    return connection


def select_listings(
    listing_id: str | None,
    limit: int | None,
    refresh: bool,
) -> list[sqlite3.Row]:
    if not CRM_DB.exists():
        raise FileNotFoundError(f"CRM database not found: {CRM_DB}")

    with get_connection() as connection:
        if listing_id:
            row = connection.execute(
                'SELECT * FROM "Listing" WHERE id = ?',
                (listing_id,),
            ).fetchone()
            return [row] if row is not None else []

        where = ""
        if not refresh:
            where = """
            WHERE valuationCents IS NULL
              AND valuationStatus NOT IN ('RUNNING', 'MANUAL_REQUIRED', 'VALUED')
            """

        sql = f"""
            SELECT *
            FROM "Listing"
            {where}
            ORDER BY firstSeenAt DESC, createdAt DESC
        """
        if limit is not None:
            sql += " LIMIT ?"
            return list(connection.execute(sql, (limit,)))
        return list(connection.execute(sql))


def update_listing_fields(
    listing_id: str,
    fields: dict[str, Any],
    dry_run: bool,
) -> None:
    if dry_run or not fields:
        return

    assignments = ", ".join(f'"{key}" = ?' for key in fields)
    values = list(fields.values())
    values.append(listing_id)
    with get_connection() as connection:
        connection.execute(
            f'UPDATE "Listing" SET {assignments}, updatedAt = CURRENT_TIMESTAMP WHERE id = ?',
            values,
        )
        connection.commit()


async def collect_visible_image_urls(page: Any) -> list[str]:
    try:
        urls = await page.evaluate(
            """() => {
                const fromSrcset = (srcset) => {
                    if (!srcset) return [];
                    return srcset
                        .split(",")
                        .map((part) => part.trim().split(/\\s+/)[0])
                        .filter(Boolean);
                };
                const metaUrls = Array.from(
                    document.querySelectorAll('meta[property="og:image"], meta[name="twitter:image"]')
                )
                    .map((element) => element.getAttribute("content") || "")
                    .filter(Boolean);
                const imageUrls = Array.from(document.querySelectorAll("img")).flatMap((image) => {
                    const urls = [];
                    if (image.currentSrc) urls.push(image.currentSrc);
                    if (image.src) urls.push(image.src);
                    urls.push(...fromSrcset(image.srcset));
                    return urls;
                });
                return [...metaUrls, ...imageUrls]
                    .map((url) => String(url).trim())
                    .filter(Boolean);
            }"""
        )
        return [str(url) for url in urls or []]
    except Exception:
        return []


async def collect_gallery_image_urls(page: Any) -> list[str]:
    """Best-effort Marketplace gallery crawl without requiring login or brittle classes."""

    image_urls: list[str] = []
    try:
        click_target = await page.evaluate(
            """() => {
                const candidates = Array.from(document.querySelectorAll("img"))
                    .map((image) => {
                        const rect = image.getBoundingClientRect();
                        const src = image.currentSrc || image.src || "";
                        return {
                            src,
                            x: rect.left + rect.width / 2,
                            y: rect.top + rect.height / 2,
                            width: rect.width,
                            height: rect.height,
                            area: rect.width * rect.height,
                        };
                    })
                    .filter((item) =>
                        item.src &&
                        (item.src.includes("fbcdn") || item.src.includes("scontent")) &&
                        item.width >= 180 &&
                        item.height >= 120 &&
                        item.x >= 0 &&
                        item.y >= 0 &&
                        item.x <= window.innerWidth &&
                        item.y <= window.innerHeight
                    )
                    .sort((a, b) => b.area - a.area);
                return candidates[0] || null;
            }"""
        )
        if not click_target:
            return image_urls

        await page.mouse.click(float(click_target["x"]), float(click_target["y"]))
        await page.wait_for_timeout(1_200)
        image_urls.extend(await collect_visible_image_urls(page))

        for _ in range(GALLERY_ADVANCE_STEPS):
            await page.keyboard.press("ArrowRight")
            await page.wait_for_timeout(650)
            image_urls.extend(await collect_visible_image_urls(page))

        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
    except Exception:
        return image_urls

    return image_urls


async def fetch_facebook_description(context: Any, listing: sqlite3.Row) -> ExtractionResult:
    page = await context.new_page()
    try:
        await page.goto(
            listing["facebookUrl"],
            wait_until="domcontentloaded",
            timeout=45_000,
        )
        await page.wait_for_timeout(2_500)
        for _ in range(3):
            await page.mouse.wheel(0, 900)
            await page.wait_for_timeout(750)
        data = await page.evaluate(
            """() => {
                const attrValues = (selector, attributeName) =>
                    Array.from(document.querySelectorAll(selector))
                        .map((element) => element.getAttribute(attributeName) || "")
                        .map((text) => text.trim())
                        .filter(Boolean)
                        .slice(0, 10);
                return {
                    pageTitle: document.title || "",
                    descriptions: attrValues(
                        'meta[name="description"], meta[property="og:description"]',
                        "content",
                    ),
                    bodyText: document.body?.innerText || "",
                };
            }"""
        )
        image_urls = await collect_visible_image_urls(page)
        image_urls.extend(await collect_gallery_image_urls(page))
    except PlaywrightTimeoutError as error:
        raise RuntimeError(f"Facebook detail page timed out: {error}") from error
    except Exception as error:
        raise RuntimeError(f"Facebook detail page failed: {error}") from error
    finally:
        await page.close()

    pieces = [
        str(listing["title"] or ""),
        str(data.get("pageTitle") or ""),
        " ".join(str(value) for value in data.get("descriptions") or []),
        str(data.get("bodyText") or ""),
    ]
    description = clean_text(" ".join(pieces))[:DESCRIPTION_LIMIT]
    detail_image_paths = cache_detail_images(
        listing,
        image_urls,
    )
    return build_extraction_from_description(listing, description, detail_image_paths)


def build_extraction_from_description(
    listing: sqlite3.Row,
    description: str,
    detail_image_paths: list[Path] | None = None,
) -> ExtractionResult:
    plate, plate_confidence = extract_number_plate(description)
    kms, kms_confidence = extract_kms(description)
    ocr_evidence = ""

    if not plate:
        plate, plate_confidence, ocr_evidence = extract_plate_from_listing_images(
            listing,
            detail_image_paths,
        )
        if plate and plate_confidence is not None:
            description = clean_text(
                f"{description} OCR plate evidence: {ocr_evidence}"
            )[:DESCRIPTION_LIMIT]

    if kms is None and ocr_evidence:
        ocr_kms, ocr_kms_confidence = extract_kms(ocr_evidence)
        if ocr_kms is not None:
            kms = ocr_kms
            kms_confidence = max(65, ocr_kms_confidence or 65)

    missing_inputs: list[str] = []
    if not plate:
        missing_inputs.append("number plate from text/image OCR")
    if kms is None:
        missing_inputs.append("odometer/kms")

    return ExtractionResult(
        number_plate=plate,
        number_plate_confidence=plate_confidence,
        kms=kms,
        kms_confidence=kms_confidence,
        description=description,
        error=(
            "Could not confidently extract " + " and ".join(missing_inputs)
            if missing_inputs
            else None
        ),
    )


def build_manual_extraction(
    listing: sqlite3.Row,
    manual_plate: str,
    manual_kms: int,
) -> ExtractionResult:
    existing_description = ""
    try:
        existing_description = str(listing["listingDescription"] or "")
    except (IndexError, KeyError):
        existing_description = ""

    description = clean_text(
        existing_description
        or f"Manual Trade Me valuation inputs for {listing['title']}"
    )[:DESCRIPTION_LIMIT]

    return ExtractionResult(
        number_plate=manual_plate,
        number_plate_confidence=100,
        kms=manual_kms,
        kms_confidence=100,
        description=description,
        error=None,
    )


async def maybe_click_buying_path(page: Any) -> None:
    try:
        clicked = await page.evaluate(
            """() => {
                const labels = Array.from(document.querySelectorAll("label"));
                const label = labels.find((element) =>
                    (element.textContent || "").toLowerCase().includes("i'm buying")
                );
                if (!label) return false;
                label.click();
                return true;
            }"""
        )
        if clicked:
            await page.wait_for_timeout(300)
            return
    except Exception:
        pass

    candidates = [page.get_by_text("I'm buying", exact=True)]
    for locator in candidates:
        try:
            if await locator.count() > 0:
                await locator.first.click(timeout=2_000)
                return
        except Exception:
            continue


async def fill_trade_me_plate(page: Any, plate: str) -> None:
    plate_inputs = [
        page.locator('input[name="numberPlateInput"]'),
        page.locator(
            'input[placeholder*="number plate" i], input[placeholder*="plate" i]'
        ),
        page.get_by_label(re.compile(r"number plate", re.I)),
    ]

    for locator in plate_inputs:
        try:
            if await locator.count() > 0:
                await locator.first.fill(plate, timeout=4_000)
                return
        except Exception:
            continue
    else:
        raise RuntimeError("Could not find Trade Me number plate input")


async def fill_trade_me_odometer(page: Any, kms: int) -> None:
    kms_inputs = [
        page.locator('input[name="odometerInput"]'),
        page.locator(
            'input[placeholder*="kilometres" i], '
            'input[placeholder*="odometer" i], '
            'input[placeholder*="km" i]'
        ),
        page.get_by_label(re.compile(r"odometer|km|kilometres", re.I)),
    ]

    for locator in kms_inputs:
        try:
            if await locator.count() > 0:
                await locator.first.fill(str(kms), timeout=4_000)
                return
        except Exception:
            continue
    else:
        raise RuntimeError("Could not find Trade Me odometer input")


async def fill_trade_me_form(page: Any, plate: str, kms: int) -> None:
    await maybe_click_buying_path(page)
    await fill_trade_me_plate(page, plate)
    await fill_trade_me_odometer(page, kms)


async def click_trade_me_submit(page: Any) -> None:
    submit_candidates = [
        page.locator('button[type="submit"]'),
        page.get_by_role(
            "button",
            name=re.compile(r"value this car|value my car|get valuation", re.I),
        ),
    ]

    for locator in submit_candidates:
        try:
            if await locator.count() > 0:
                await locator.first.click(timeout=8_000)
                return
        except Exception:
            continue
    raise RuntimeError("Could not find Trade Me valuation submit button")


async def submit_trade_me_valuation(context: Any, plate: str, kms: int) -> ValuationResult:
    page = await context.new_page()
    try:
        await page.goto(TRADE_ME_VALUE_URL, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(1_500)
        await fill_trade_me_form(page, plate, kms)
        before_text = await page.locator("body").inner_text(timeout=5_000)

        await click_trade_me_submit(page)
        await page.wait_for_timeout(7_500)
        after_text = await page.locator("body").inner_text(timeout=8_000)
        current_url = page.url

        if TRADE_ME_LOGIN_URL_PATTERN.search(current_url):
            return ValuationResult(
                valuation_cents=None,
                status="FAILED",
                error=(
                    "Trade Me requires a logged-in browser session before it "
                    "will return a Value My Car result. Run npm.cmd run trademe:login "
                    "once, then retry the valuation."
                ),
            )

        if HUMAN_VERIFICATION_PATTERN.search(after_text):
            return ValuationResult(
                valuation_cents=None,
                status="FAILED",
                error="Trade Me asked for human verification or blocked the automated page.",
            )

        if TRADE_ME_NO_VALUATION_PATTERN.search(after_text):
            return ValuationResult(
                valuation_cents=None,
                status="MANUAL_REQUIRED",
                error=(
                    "Trade Me could not find a valuation for that plate/kms. "
                    "Its page says there may not be enough data for the make, model, or year."
                ),
            )

        changed_text = after_text if after_text != before_text else after_text
        valuation_cents = extract_valuation_cents(changed_text)
        if valuation_cents is None:
            return ValuationResult(
                valuation_cents=None,
                status="FAILED",
                error="Trade Me did not expose a readable valuation amount.",
            )

        return ValuationResult(
            valuation_cents=valuation_cents,
            status="VALUED",
            error=None,
        )
    except Exception as error:
        return ValuationResult(
            valuation_cents=None,
            status="FAILED",
            error=f"Trade Me valuation failed: {error}",
        )
    finally:
        await page.close()


async def process_listing(
    listing: sqlite3.Row,
    facebook_context: Any,
    trade_me_context: Any,
    dry_run: bool,
    manual_plate: str | None = None,
    manual_kms: int | None = None,
) -> dict[str, Any]:
    title = console_text(str(listing["title"]))
    print(f"[VALUE] Processing {title}", flush=True)

    update_listing_fields(
        listing["id"],
        {
            "valuationStatus": "RUNNING",
            "valuationError": None,
            "valuationCheckedAt": now_iso(),
        },
        dry_run,
    )

    if manual_plate and manual_kms is not None:
        extraction = build_manual_extraction(listing, manual_plate, manual_kms)
    else:
        try:
            extraction = await fetch_facebook_description(facebook_context, listing)
        except Exception as error:
            fallback_description = clean_text(
                f"{listing['title']} {listing['listingDescription'] or ''}"
            )
            extraction = build_extraction_from_description(
                listing,
                fallback_description,
                [],
            )
            if extraction.error:
                extraction.error = f"{extraction.error}. Facebook detail fetch also failed: {error}"

    extraction_fields = {
        "listingDescription": extraction.description,
        "numberPlate": extraction.number_plate,
        "numberPlateConfidence": extraction.number_plate_confidence,
        "kms": extraction.kms,
        "kmsConfidence": extraction.kms_confidence,
        "valuationCheckedAt": now_iso(),
    }

    if extraction.error:
        update_listing_fields(
            listing["id"],
            {
                **extraction_fields,
                "valuationStatus": "MANUAL_REQUIRED",
                "valuationError": extraction.error,
            },
            dry_run,
        )
        return {
            "id": listing["id"],
            "status": "MANUAL_REQUIRED",
            "error": extraction.error,
            "numberPlate": extraction.number_plate,
            "kms": extraction.kms,
        }

    if dry_run:
        return {
            "id": listing["id"],
            "status": "READY",
            "numberPlate": extraction.number_plate,
            "kms": extraction.kms,
            "wouldSubmitTradeMe": True,
        }

    update_listing_fields(
        listing["id"],
        {
            **extraction_fields,
            "valuationStatus": "READY",
            "valuationError": None,
        },
        dry_run,
    )

    result = await submit_trade_me_valuation(
        trade_me_context,
        extraction.number_plate or "",
        extraction.kms or 0,
    )

    if result.valuation_cents is None:
        update_listing_fields(
            listing["id"],
            {
                "valuationStatus": result.status,
                "valuationError": result.error,
                "valuationCheckedAt": now_iso(),
                "valuationSource": SOURCE_NAME,
            },
            dry_run,
        )
        return {
            "id": listing["id"],
            "status": result.status,
            "error": result.error,
            "numberPlate": extraction.number_plate,
            "kms": extraction.kms,
        }

    target_sell, max_buy, profit = calculate_deal_metrics(
        result.valuation_cents,
        int(listing["askingPriceCents"]),
    )
    update_listing_fields(
        listing["id"],
        {
            "valuationCents": result.valuation_cents,
            "targetSellPriceCents": target_sell,
            "maxBuyPriceCents": max_buy,
            "estimatedProfitCents": profit,
            "valuationStatus": "VALUED",
            "valuationError": None,
            "valuationCheckedAt": now_iso(),
            "valuationSource": SOURCE_NAME,
        },
        dry_run,
    )
    return {
        "id": listing["id"],
        "status": "VALUED",
        "valuationCents": result.valuation_cents,
        "targetSellPriceCents": target_sell,
        "maxBuyPriceCents": max_buy,
        "estimatedProfitCents": profit,
        "numberPlate": extraction.number_plate,
        "kms": extraction.kms,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listing-id", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--manual-plate", default=None)
    parser.add_argument("--manual-kms", default=None)
    parser.add_argument("--setup-trademe-login", action="store_true")
    parser.add_argument(
        "--trade-me-channel",
        choices=("msedge", "chrome", "chromium"),
        default=None,
        help="Browser channel for Trade Me login/session storage.",
    )
    return parser.parse_args()


async def setup_trade_me_login(
    playwright: Any,
    channel: str | None,
) -> dict[str, Any]:
    profile_dir = trade_me_profile_dir(channel)
    profile_dir.mkdir(parents=True, exist_ok=True)
    context = await playwright.chromium.launch_persistent_context(
        str(profile_dir),
        **launch_context_options(headless=False, channel=channel),
    )
    page = context.pages[0] if context.pages else await context.new_page()
    try:
        await page.goto(TRADE_ME_VALUE_URL, wait_until="domcontentloaded", timeout=60_000)
        print(
            "[VALUE] A Trade Me browser window is open. Log in normally, then "
            "return here and press Enter to save the session.",
            flush=True,
        )
        await asyncio.to_thread(input)
        current_url = page.url
        body_text = await page.locator("body").inner_text(timeout=8_000)
        logged_in = not TRADE_ME_LOGIN_URL_PATTERN.search(current_url)
        if "Log out" in body_text or "My Trade Me" in body_text:
            logged_in = True
        write_trade_me_profile_config(channel)
        return {
            "channel": channel or "chromium",
            "profileDir": str(profile_dir),
            "loggedInLikely": logged_in,
            "currentUrl": current_url,
        }
    finally:
        await context.close()


async def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    manual_plate = parse_manual_plate(args.manual_plate)
    manual_kms = parse_manual_kms(args.manual_kms)
    trade_me_channel = selected_trade_me_channel(args.trade_me_channel)

    if args.setup_trademe_login:
        async with async_playwright() as playwright:
            result = await setup_trade_me_login(playwright, trade_me_channel)
        return {
            "read": 0,
            "processed": 0,
            "tradeMeLogin": result,
            "elapsedSeconds": int(time.monotonic() - started),
        }

    if args.manual_plate or args.manual_kms:
        if not manual_plate:
            raise ValueError("Manual number plate is invalid or missing.")
        if manual_kms is None:
            raise ValueError("Manual odometer/kms is invalid or missing.")

    listings = select_listings(args.listing_id, args.limit, args.refresh)
    if not listings:
        return {"read": 0, "processed": 0, "results": [], "elapsedSeconds": 0}

    results: list[dict[str, Any]] = []
    async with async_playwright() as playwright:
        facebook_browser = await playwright.chromium.launch(headless=not args.headed)
        profile_dir = trade_me_profile_dir(trade_me_channel)
        profile_dir.mkdir(parents=True, exist_ok=True)
        trade_me_context = await playwright.chromium.launch_persistent_context(
            str(profile_dir),
            **launch_context_options(
                headless=not args.headed,
                channel=trade_me_channel,
            ),
        )
        try:
            facebook_context = await facebook_browser.new_context(
                user_agent=MODERN_USER_AGENT,
                viewport={"width": 1440, "height": 1200},
                locale="en-NZ",
                extra_http_headers={"Accept-Language": "en-NZ,en;q=0.9"},
            )
            try:
                for listing in listings:
                    results.append(
                        await process_listing(
                            listing,
                            facebook_context,
                            trade_me_context,
                            args.dry_run,
                            manual_plate,
                            manual_kms,
                        )
                    )
            finally:
                await facebook_context.close()
                await trade_me_context.close()
        finally:
            await facebook_browser.close()

    return {
        "read": len(listings),
        "processed": len(results),
        "dryRun": args.dry_run,
        "results": results,
        "elapsedSeconds": int(time.monotonic() - started),
    }


async def main() -> None:
    args = parse_args()
    summary = await run(args)
    print("[VALUE] Completed:", json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
