from __future__ import annotations

import re
import unittest
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from vehicle_valuation.dedupe import deduplicate
from vehicle_valuation.matching import match_comparable
from vehicle_valuation.models import Base, ValuationRun, utcnow
from vehicle_valuation.normalization import (
    NormalizedVehicle, is_full_cash_vehicle, parse_kms, parse_price_cents,
    vehicle_from_text,
)
from vehicle_valuation.repositories import queue_target, recover_stale_work
from vehicle_valuation.schemas import TargetRequest
from vehicle_valuation.scrapers.base import RawListing
from vehicle_valuation.scrapers.catalog import SOURCE_DEFINITIONS
from vehicle_valuation.scrapers.generic import ConfiguredPortalAdapter, PortalConfig
from vehicle_valuation.valuation import value_vehicle, verdict_for_percentage


def comparable(
    source: str,
    price: int,
    *,
    year: int = 2018,
    kms: int = 100_000,
    model: str = "Corolla GX",
    url_suffix: str = "1",
) -> RawListing:
    return RawListing(
        source_id=source,
        source_listing_id=url_suffix,
        url=f"https://{source}.example/vehicle/{url_suffix}",
        title=f"{year} Toyota {model}",
        asking_price_cents=price,
        year=year,
        make="Toyota",
        model=model,
        kms=kms,
        transmission="AUTOMATIC",
        fuel_type="PETROL",
        body_type="HATCHBACK",
        region="Auckland",
    )


class NormalizationTests(unittest.TestCase):
    def test_vehicle_identity_and_kms(self) -> None:
        vehicle = vehicle_from_text("2018 Toyota Corolla GX | $16,900", "181,000 km automatic petrol hatch")
        self.assertEqual(vehicle.year, 2018)
        self.assertEqual(vehicle.make, "Toyota")
        self.assertEqual(vehicle.model, "Corolla GX")
        self.assertEqual(vehicle.kms, 181_000)
        self.assertEqual(vehicle.transmission, "AUTOMATIC")
        self.assertEqual(vehicle.fuel_type, "PETROL")
        self.assertEqual(vehicle.body_type, "HATCHBACK")

    def test_price_and_km_formats(self) -> None:
        self.assertEqual(parse_price_cents("Cash price $18,500"), 1_850_000)
        self.assertEqual(parse_kms("odometer 181k"), 181_000)
        self.assertIsNone(parse_price_cents("From $79 per week"))

    def test_non_cash_and_damaged_exclusions(self) -> None:
        self.assertEqual(is_full_cash_vehicle("$79 per week", 7900)[0], False)
        self.assertEqual(is_full_cash_vehicle("Damaged wrecking parts only $3,000", 300_000)[0], False)
        self.assertEqual(is_full_cash_vehicle("Current bid $5,000", 500_000)[0], False)
        self.assertEqual(is_full_cash_vehicle("Fixed cash price $5,000", 500_000)[0], True)


class PortalFixtureTests(unittest.TestCase):
    def test_every_inventory_portal_parses_json_ld_fixture(self) -> None:
        html = """
        <html><script type="application/ld+json">
        {"@type":"Vehicle","name":"2018 Toyota Corolla GX","url":"/vehicle/12345",
         "vehicleModelDate":2018,"brand":{"name":"Toyota"},"model":"Corolla GX",
         "mileageFromOdometer":{"value":101000},"vehicleTransmission":"Automatic",
         "fuelType":"Petrol","bodyType":"Hatchback","offers":{"price":"18500"}}
        </script></html>
        """
        target = NormalizedVehicle(title="2018 Toyota Corolla GX", year=2018, make="Toyota", model="Corolla GX")
        inventory_sources = [item for item in SOURCE_DEFINITIONS if item["role"] == "INVENTORY" and item["id"] not in {"facebook_marketplace", "generic_dealers"}]
        self.assertGreaterEqual(len(inventory_sources), 6)
        for source in inventory_sources:
            with self.subTest(source=source["id"]):
                adapter = ConfiguredPortalAdapter(PortalConfig(
                    source_id=str(source["id"]),
                    name=str(source["name"]),
                    base_url=str(source["base_url"]),
                    search_builder=lambda _target: str(source["base_url"]),
                    detail_pattern=re.compile(r"/vehicle/\d+"),
                ))
                listings, rejected = adapter.parse(html, str(source["base_url"]), target)
                self.assertEqual(rejected, 0)
                self.assertEqual(len(listings), 1)
                self.assertEqual(listings[0].asking_price_cents, 1_850_000)


class MatchingAndValuationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = NormalizedVehicle(
            title="2018 Toyota Corolla GX", year=2018, make="Toyota", model="Corolla GX",
            variant="GX", kms=100_000, transmission="AUTOMATIC", fuel_type="PETROL",
            body_type="HATCHBACK", region="Auckland",
        )

    def test_strict_and_widened_matching(self) -> None:
        strict = comparable("one", 1_800_000)
        strict.variant = "GX"
        self.assertEqual(match_comparable(self.target, strict).tier, "STRICT")
        widened = comparable("two", 1_900_000, year=2020, kms=128_000, url_suffix="2")
        widened.variant = "GLX"
        self.assertEqual(match_comparable(self.target, widened).tier, "WIDENED")

    def test_cross_source_duplicate_counts_once(self) -> None:
        one = comparable("portal-a", 1_850_000, url_suffix="a")
        two = comparable("portal-b", 1_850_000, url_suffix="b")
        one.seller_name = two.seller_name = "Example Motors"
        self.assertEqual(len(deduplicate([one, two])), 1)

    def test_median_and_business_formulas(self) -> None:
        items = [
            comparable(f"source-{index}", price, kms=100_000 + index * 1000, url_suffix=str(index))
            for index, price in enumerate([1_700_000, 1_800_000, 1_850_000, 1_900_000, 2_000_000], 1)
        ]
        for item in items:
            item.variant = "GX"
        result = value_vehicle(self.target, 1_690_000, items)
        self.assertEqual(result.market_value_cents, 1_850_000)
        self.assertEqual(result.difference_cents, 160_000)
        self.assertEqual(result.verdict, "GOOD_DEAL")
        self.assertEqual(result.target_sell_cents, 1_480_000)
        self.assertEqual(result.max_buy_cents, 1_380_000)
        self.assertEqual(result.expected_spread_cents, -210_000)

    def test_verdict_boundaries(self) -> None:
        self.assertEqual(verdict_for_percentage(10.01)[0], "EXCELLENT_DEAL")
        self.assertEqual(verdict_for_percentage(5)[0], "GOOD_DEAL")
        self.assertEqual(verdict_for_percentage(-4.99)[0], "FAIR_MARKET_VALUE")
        self.assertEqual(verdict_for_percentage(-5)[0], "OVERPRICED")
        self.assertEqual(verdict_for_percentage(-10.01)[0], "VERY_OVERPRICED")


class QueueLifecycleTests(unittest.TestCase):
    def test_fresh_unchanged_target_is_not_requeued(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        request = TargetRequest(
            facebookUrl="https://www.facebook.com/marketplace/item/123456789/",
            title="2018 Toyota Corolla GX",
            askingPriceCents=1_690_000,
        )
        with Session(engine, expire_on_commit=False) as session:
            first = queue_target(session, request)
            first.status = "COMPLETED"
            session.add(ValuationRun(
                target_id=first.target_id,
                job_id=first.id,
                status="VALUED",
                market_value_cents=1_850_000,
                comparable_count=8,
                reason="fixture",
                created_at=utcnow(),
            ))
            session.commit()
            second = queue_target(session, request)
            self.assertEqual(first.id, second.id)

            session.query(ValuationRun).update({ValuationRun.created_at: utcnow() - timedelta(hours=25)})
            session.commit()
            third = queue_target(session, request)
            self.assertNotEqual(first.id, third.id)

    def test_stale_running_job_is_recovered(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        request = TargetRequest(
            facebookUrl="https://www.facebook.com/marketplace/item/987654321/",
            title="2012 Mazda Axela",
            askingPriceCents=450_000,
        )
        with Session(engine, expire_on_commit=False) as session:
            job = queue_target(session, request)
            job.status = "RUNNING"
            job.started_at = utcnow() - timedelta(minutes=20)
            session.commit()
            recovered = recover_stale_work(session)
            self.assertEqual(recovered["jobs"], 1)
            self.assertEqual(job.status, "RETRY")


if __name__ == "__main__":
    unittest.main()
