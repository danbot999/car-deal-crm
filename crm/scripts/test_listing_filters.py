from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from main import is_publishable_item  # noqa: E402
from scraper import is_strict_car_listing  # noqa: E402


def assert_allowed(title: str, category: str) -> None:
    if not is_strict_car_listing(title, category):
        raise AssertionError(f"expected passenger car to pass: {title!r}, {category!r}")


def assert_rejected(title: str, category: str) -> None:
    if is_strict_car_listing(title, category):
        raise AssertionError(f"expected non-car to be rejected: {title!r}, {category!r}")


def main() -> None:
    assert_allowed("2008 Toyota Corolla", "Cars & Trucks")
    assert_allowed("2012 Honda Fit", "Cars and Trucks")

    assert_rejected("2002 Isuzu gala", "RVs & Campers")
    assert_rejected("2002 Isuzu Gala", "Cars & Trucks")
    assert_rejected("Airport shuttle bus", "Cars & Trucks")
    assert_rejected("Toyota Coaster", "Cars & Trucks")
    assert_rejected("2010 campervan", "RVs & Campers")
    assert_rejected("Aeroklass canopy 2016 Isuzu D-Max", "Cars & Trucks")
    assert_rejected("2008 Toyota Corolla", "")

    valid_item = {
        "verified": True,
        "available": True,
        "in_scope": True,
        "availabilityStatus": "ACTIVE",
    }
    if not is_publishable_item(valid_item):
        raise AssertionError("verified active car should be publishable")

    for key, value in (
        ("verified", False),
        ("available", False),
        ("in_scope", False),
        ("availabilityStatus", "POSSIBLY_SOLD"),
        ("availabilityStatus", "CONFIRMED_SOLD"),
    ):
        invalid_item = {**valid_item, key: value}
        if is_publishable_item(invalid_item):
            raise AssertionError(f"invalid item passed publish filter: {key}={value!r}")

    print("[TEST] strict active passenger-car filters passed")


if __name__ == "__main__":
    main()
