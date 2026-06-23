"""Facebook target enrichment using page text, local OCR, then OpenAI fallback."""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import requests
from PIL import Image
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from rapidocr_onnxruntime import RapidOCR

from .config import USER_AGENT, openai_settings
from .normalization import NormalizedVehicle, clean_text, parse_kms, vehicle_from_text


@dataclass
class EnrichmentResult:
    vehicle: NormalizedVehicle
    description: str
    image_urls: list[str]
    evidence: dict[str, Any]
    confidence: str


def collect_facebook_page(url: str) -> tuple[str, list[str]]:
    body_text = ""
    image_urls: list[str] = []
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
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(4_000)
            data = page.evaluate(
                """() => ({
                  title: document.title || "",
                  body: (document.body?.innerText || "").slice(0, 16000),
                  meta: Array.from(document.querySelectorAll('meta[name="description"],meta[property="og:description"]')).map(x => x.getAttribute('content') || ''),
                  images: Array.from(document.querySelectorAll('img')).map(x => x.currentSrc || x.src || '').filter(x => /^https?:/.test(x)).slice(0, 80)
                })"""
            )
            body_text = clean_text(" ".join([str(data.get("title") or ""), *(data.get("meta") or []), str(data.get("body") or "")]))
            image_urls = list(dict.fromkeys(str(value) for value in data.get("images") or [] if value))
            context.close()
            browser.close()
    except (PlaywrightTimeoutError, Exception):
        return body_text, image_urls
    return body_text, image_urls


def ocr_image_text(image_urls: list[str], max_images: int = 10) -> tuple[str, list[dict[str, Any]]]:
    if not image_urls:
        return "", []
    engine = RapidOCR()
    evidence: list[dict[str, Any]] = []
    collected: list[str] = []
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    for url in image_urls[:max_images]:
        try:
            response = session.get(url, timeout=15)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content)).convert("RGB")
            result, _elapsed = engine(np.array(image))
            if not result:
                continue
            lines = []
            for row in result:
                text = clean_text(row[1])
                confidence = float(row[2])
                if text and confidence >= 0.45:
                    lines.append(text)
                    collected.append(text)
            if lines:
                evidence.append({"imageUrl": url, "text": lines[:30]})
        except Exception:
            continue
    return clean_text(" ".join(collected)), evidence


def extract_openai_json(payload: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(payload.get("output_text"), str):
        try:
            return json.loads(payload["output_text"])
        except ValueError:
            pass
    for output in payload.get("output") or []:
        for content in output.get("content") or []:
            text = content.get("text")
            if isinstance(text, str):
                try:
                    return json.loads(text)
                except ValueError:
                    continue
    return None


def ai_vehicle_extract(title: str, text: str, image_urls: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    api_key, model = openai_settings()
    if not api_key:
        return None, "OPENAI_API_KEY is not configured"
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "year": {"type": ["integer", "null"]},
            "make": {"type": ["string", "null"]},
            "model": {"type": ["string", "null"]},
            "variant": {"type": ["string", "null"]},
            "kms": {"type": ["integer", "null"]},
            "transmission": {"type": ["string", "null"]},
            "fuelType": {"type": ["string", "null"]},
            "bodyType": {"type": ["string", "null"]},
            "region": {"type": ["string", "null"]},
            "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
            "evidence": {"type": "string"},
        },
        "required": ["year", "make", "model", "variant", "kms", "transmission", "fuelType", "bodyType", "region", "confidence", "evidence"],
    }
    content: list[dict[str, Any]] = [{
        "type": "input_text",
        "text": (
            "Extract the factual vehicle identity from this NZ Facebook Marketplace listing. "
            "Use null when unsupported; do not invent a price or specification.\n"
            f"Title: {title}\nListing/OCR text: {text[:12000]}"
        ),
    }]
    for image_url in image_urls[:4]:
        content.append({"type": "input_image", "image_url": image_url, "detail": "low"})
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "input": [{"role": "user", "content": content}],
                "text": {"format": {"type": "json_schema", "name": "vehicle_identity", "strict": True, "schema": schema}},
            },
            timeout=90,
        )
        response.raise_for_status()
        return extract_openai_json(response.json()), None
    except Exception as error:
        return None, clean_text(error)[:500]


def merge_vehicle(base: NormalizedVehicle, ai: dict[str, Any] | None) -> NormalizedVehicle:
    if not ai:
        return base
    supplied = {
        "year": base.year or ai.get("year"), "make": base.make or ai.get("make"),
        "model": base.model or ai.get("model"), "variant": base.variant or ai.get("variant"),
        "kms": base.kms or ai.get("kms"), "transmission": base.transmission or ai.get("transmission"),
        "fuelType": base.fuel_type or ai.get("fuelType"), "bodyType": base.body_type or ai.get("bodyType"),
        "region": base.region or ai.get("region"),
    }
    return vehicle_from_text(base.title, supplied=supplied)


def enrich_target(title: str, url: str, supplied: dict[str, Any]) -> EnrichmentResult:
    page_text, image_urls = collect_facebook_page(url)
    base = vehicle_from_text(title, page_text, supplied)
    evidence: dict[str, Any] = {"pageTextAvailable": bool(page_text), "imagesFound": len(image_urls)}
    ocr_text = ""
    if not base.kms:
        ocr_text, ocr_evidence = ocr_image_text(image_urls)
        evidence["ocr"] = ocr_evidence
        ocr_kms = parse_kms(ocr_text)
        if ocr_kms:
            supplied = {**supplied, "kms": ocr_kms}
            base = vehicle_from_text(title, f"{page_text} {ocr_text}", supplied)
    missing = [name for name, value in (("year", base.year), ("make", base.make), ("model", base.model), ("kms", base.kms), ("variant", base.variant)) if not value]
    ai_result = None
    if missing:
        ai_result, ai_error = ai_vehicle_extract(title, f"{page_text} {ocr_text}", image_urls)
        evidence["ai"] = {"result": ai_result, "error": ai_error}
        base = merge_vehicle(base, ai_result)
    complete = sum(value is not None for value in (base.year, base.make, base.model, base.kms, base.variant))
    confidence = "HIGH" if complete >= 5 else "MEDIUM" if complete >= 3 else "LOW"
    return EnrichmentResult(base, page_text, image_urls, evidence, confidence)
