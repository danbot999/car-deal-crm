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
    NormalizedVehicle, identity_key, is_full_cash_vehicle, parse_kms, parse_price_cents,
    vehicle_from_text,
)
from vehicle_valuation.repositories import queue_target, recover_stale_work
from vehicle_valuation.schemas import TargetRequest
from vehicle_valuation.scrapers.base import RawListing
from vehicle_valuation.scrapers.catalog import SOURCE_DEFINITIONS, build_inventory_adapters
from vehicle_valuation.scrapers.generic import BLOCKED_RE, ConfiguredPortalAdapter, PortalConfig
from vehicle_valuation.scrapers.trademe import parse_rendered_cards, search_query
from vehicle_valuation.valuation import value_vehicle, verdict_for_percentage


def comparable(
    source: str,
    price: int,
    *,
    year: int = 2018,
    kms: int = 100_000,
    model: str = "Corolla",
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
        self.assertEqual(vehicle.model, "Corolla")
        self.assertEqual(vehicle.variant, "GX")
        self.assertEqual(vehicle.kms, 181_000)
        self.assertEqual(vehicle.transmission, "AUTOMATIC")
        self.assertEqual(vehicle.fuel_type, "PETROL")
        self.assertEqual(vehicle.body_type, "HATCHBACK")

    def test_subaru_trim_is_not_part_of_canonical_model(self) -> None:
        vehicle = vehicle_from_text(
            "Subaru legacy 2006 (black edition)",
            "Electric windows. Auckland. 161,000 km.",
        )
        self.assertEqual(vehicle.year, 2006)
        self.assertEqual(vehicle.make, "Subaru")
        self.assertEqual(vehicle.model, "Legacy")
        self.assertEqual(vehicle.variant, "black edition")
        self.assertEqual(vehicle.kms, 161_000)
        self.assertIsNone(vehicle.fuel_type)
        self.assertEqual(vehicle.region, "Auckland")

    def test_shorthand_and_misspelling_aliases(self) -> None:
        self.assertEqual(vehicle_from_text("Swift 2009").make, "Suzuki")
        self.assertEqual(vehicle_from_text("MPV 2008").make, "Mazda")
        demio = vehicle_from_text("Mazada demio 2007")
        self.assertEqual((demio.make, demio.model), ("Mazda", "Demio"))
        audi = vehicle_from_text("Audi A6 2008 *low kms*")
        self.assertEqual((audi.year, audi.make, audi.model), (2008, "Audi", "A6"))
        skoda = vehicle_from_text("2009 Skoda Superb 2.0 TDI Auto")
        self.assertEqual(skoda.model, "Superb")
        self.assertEqual(vehicle_from_text("2012 BMW Series 1").model, "1 Series")
        self.assertEqual(vehicle_from_text("2000 Subaru Imprezza sun roof").model, "Impreza")
        self.assertEqual(vehicle_from_text("Nissan bluebird 2007").model, "Bluebird")
        self.assertEqual(vehicle_from_text("2008 Toyota vanguard 4wd").model, "Vanguard")
        bmw_730d = vehicle_from_text("2009 BMW 730D LUXURY")
        self.assertEqual((bmw_730d.year, bmw_730d.make, bmw_730d.model, bmw_730d.variant), (2009, "BMW", "7 Series", "730d"))
        bmw_740i = vehicle_from_text("2020 BMW 7 Series 740i M-Sport")
        self.assertEqual((bmw_740i.year, bmw_740i.make, bmw_740i.model, bmw_740i.variant), (2020, "BMW", "7 Series", "740i"))
        bmw_730ld = vehicle_from_text("2008 730LD BMW")
        self.assertEqual((bmw_730ld.year, bmw_730ld.make, bmw_730ld.model, bmw_730ld.variant), (2008, "BMW", "7 Series", "730d"))
        bmw_no_badge = vehicle_from_text("2019 BMW 7 Series M-Sport amp", "$64,990 90,000 km")
        self.assertEqual((bmw_no_badge.make, bmw_no_badge.model, bmw_no_badge.variant), ("BMW", "7 Series", "M-Sport"))
        self.assertEqual(identity_key(bmw_730d), "2009|bmw|7 series|730d")
        self.assertEqual(identity_key(bmw_740i), "2020|bmw|7 series|740i")

    def test_engine_capacity_in_description_is_not_used_as_model_year(self) -> None:
        vehicle = vehicle_from_text("Kia Sorento Limited - project", "2000 cc diesel engine")
        self.assertIsNone(vehicle.year)

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
    def test_fast_source_tier_is_filtered_without_losing_slow_sources(self) -> None:
        fast_ids = {
            adapter.source_id
            for adapter in build_inventory_adapters(
                include_source_ids={"facebook_marketplace", "trademe_motors"}
            )
        }
        slow_ids = {
            adapter.source_id
            for adapter in build_inventory_adapters(
                exclude_source_ids={"facebook_marketplace", "trademe_motors"}
            )
        }
        self.assertEqual(fast_ids, {"facebook_marketplace", "trademe_motors"})
        self.assertTrue({"onlycars", "autoport", "turners"}.issubset(slow_ids))
        self.assertFalse(fast_ids & slow_ids)

    def test_harmless_recaptcha_configuration_is_not_a_block(self) -> None:
        self.assertIsNone(BLOCKED_RE.search('{"recaptchaSiteKey":"public-config-value"}'))

    def test_trademe_cards_keep_cash_prices_and_reject_auctions_and_wrong_models(self) -> None:
        target = NormalizedVehicle(title="2006 Subaru Legacy", year=2006, make="Subaru", model="Legacy")
        cards = [
            {
                "href": "https://www.trademe.co.nz/a/motors/cars/subaru/legacy/listing/1234567890",
                "anchorText": "2006 Subaru Legacy GT",
                "text": "2006 Subaru Legacy GT\n161,000 km\nAsking price $5,500\nFinance from $79 per week",
                "image": "",
            },
            {
                "href": "https://www.trademe.co.nz/a/motors/cars/subaru/legacy/listing/1234567891",
                "anchorText": "2006 Subaru Legacy",
                "text": "2006 Subaru Legacy\nCurrent bid $3,000\nReserve not met",
                "image": "",
            },
            {
                "href": "https://www.trademe.co.nz/a/motors/cars/subaru/outback/listing/1234567892",
                "anchorText": "2006 Subaru Outback",
                "text": "2006 Subaru Outback\nAsking price $6,500",
                "image": "",
            },
        ]
        listings, rejected = parse_rendered_cards(cards, target)
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].asking_price_cents, 550_000)
        self.assertEqual(rejected, 2)

    def test_trademe_search_uses_bmw_engine_badge_not_generic_series(self) -> None:
        bmw = vehicle_from_text("2009 BMW 730D LUXURY")
        self.assertEqual(search_query(bmw), "2009 BMW 730d")
        toyota = vehicle_from_text("2018 Toyota Corolla GX")
        self.assertEqual(search_query(toyota), "2018 Toyota Corolla GX")

    def test_every_inventory_portal_parses_json_ld_fixture(self) -> None:
        html = """
        <html><script type="application/ld+json">
        {"@type":"Vehicle","name":"2018 Toyota Corolla GX","url":"/vehicle/12345",
         "vehicleModelDate":2018,"brand":{"name":"Toyota"},"model":"Corolla GX",
         "mileageFromOdometer":{"value":101000},"vehicleTransmission":"Automatic",
         "fuelType":"Petrol","bodyType":"Hatchback","offers":{"price":"18500"}}
        </script></html>
        """
        target = NormalizedVehicle(title="2018 Toyota Corolla GX", year=2018, make="Toyota", model="Corolla")
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
            title="2018 Toyota Corolla GX", year=2018, make="Toyota", model="Corolla",
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

    def test_exact_requires_a_safe_multi_source_cohort(self) -> None:
        items = [
            comparable("a", 1_500_000, kms=40_000, model="Corolla", url_suffix="a"),
            comparable("a", 1_900_000, kms=240_000, model="Corolla", url_suffix="b"),
            comparable("b", 1_700_000, kms=120_000, model="Corolla", url_suffix="c"),
            comparable("b", 1_600_000, kms=140_000, model="Corolla", url_suffix="d"),
            comparable("c", 1_800_000, kms=90_000, model="Corolla", url_suffix="e"),
        ]
        items[0].variant = "GLX"
        items[1].variant = "GX"
        result = value_vehicle(self.target, 1_400_000, items)
        self.assertEqual(result.method, "EXACT")
        self.assertEqual(result.comparable_count, 5)
        self.assertEqual(result.market_value_cents, 1_700_000)
        self.assertEqual(result.confidence, "EXACT_MEDIUM")

    def test_bmw_series_exact_requires_engine_badge(self) -> None:
        target = NormalizedVehicle(
            title="2009 BMW 730D LUXURY",
            year=2009,
            make="BMW",
            model="7 Series",
            variant="730d",
        )
        wrong_badge = RawListing(
            source_id="trademe",
            source_listing_id="740i",
            url="https://example.test/740i",
            title="2009 BMW 740i",
            asking_price_cents=999_900,
            year=2009,
            make="BMW",
            model="7 Series",
            variant="740i",
        )
        result = value_vehicle(target, 620_000, [wrong_badge])
        self.assertEqual(result.status, "AWAITING_SAFE_EVIDENCE")
        self.assertEqual(result.exact_count, 0)
        self.assertIsNone(result.market_value_cents)

        right_badge = RawListing(
            source_id="trademe",
            source_listing_id="730d",
            url="https://example.test/730d",
            title="2009 BMW 730d",
            asking_price_cents=700_000,
            year=2009,
            make="BMW",
            model="7 Series",
            variant="730d",
        )
        right_badges = [
            RawListing(
                source_id="trademe" if index < 3 else "dealer",
                source_listing_id=f"730d-{index}",
                url=f"https://example.test/730d-{index}",
                title="2009 BMW 730d",
                asking_price_cents=680_000 + index * 10_000,
                year=2009,
                make="BMW",
                model="7 Series",
                variant="730d",
            )
            for index in range(5)
        ]
        result = value_vehicle(target, 620_000, [wrong_badge, *right_badges])
        self.assertEqual(result.status, "VALUED")
        self.assertEqual(result.method, "EXACT")
        self.assertEqual(result.exact_count, 5)
        self.assertEqual(result.market_value_cents, 700_000)
        self.assertIn("730d", result.reason)

    def test_generation_and_class_fallbacks_are_not_publishable(self) -> None:
        generation = [
            comparable("g1", 1_700_000, year=2017, url_suffix="g1"),
            comparable("g2", 1_900_000, year=2019, url_suffix="g2"),
            comparable("g3", 1_850_000, year=2019, url_suffix="g3"),
        ]
        generation_result = value_vehicle(self.target, 1_500_000, generation)
        self.assertEqual(generation_result.status, "AWAITING_SAFE_EVIDENCE")
        self.assertIsNone(generation_result.market_value_cents)

        different_model = [
            comparable(f"class-{index}", 1_600_000 + index * 10_000, model="Camry", url_suffix=f"class-{index}")
            for index in range(8)
        ]
        class_result = value_vehicle(self.target, 1_500_000, different_model)
        self.assertEqual(class_result.status, "AWAITING_SAFE_EVIDENCE")
        self.assertIsNone(class_result.market_value_cents)

    def test_known_year_never_uses_far_newer_same_model_as_median(self) -> None:
        old_target = NormalizedVehicle(
            title="2008 Toyota Corolla", year=2008, make="Toyota", model="Corolla",
            kms=180_000, transmission="AUTOMATIC", fuel_type="PETROL", body_type="HATCHBACK",
        )
        far_newer = [
            comparable(f"newer-{index}", 2_400_000 + index * 10_000, year=2015, url_suffix=f"newer-{index}")
            for index in range(12)
        ]
        result = value_vehicle(old_target, 500_000, far_newer)
        self.assertEqual(result.status, "AWAITING_SAFE_EVIDENCE")
        self.assertIsNone(result.market_value_cents)
        self.assertIn("far-newer", result.reason)

    def test_incomplete_identity_waits_instead_of_using_all_inventory(self) -> None:
        vague = NormalizedVehicle(title="Car for sale", make=None, model=None, year=None)
        result = value_vehicle(vague, 500_000, [comparable("all", 2_000_000)])
        self.assertEqual(result.status, "AWAITING_SAFE_EVIDENCE")
        self.assertIsNone(result.market_value_cents)
        self.assertIn("year, make, and model", result.reason)

    def test_empty_index_keeps_expanding_instead_of_terminal_failure(self) -> None:
        result = value_vehicle(self.target, 1_500_000, [])
        self.assertEqual(result.status, "AWAITING_SAFE_EVIDENCE")
        self.assertIsNone(result.market_value_cents)

    def test_implausible_axela_year_is_quarantined(self) -> None:
        target = vehicle_from_text("2002 Mazda Axela")
        newer = [
            RawListing(
                source_id="trademe" if index < 3 else "dealer",
                source_listing_id=str(index),
                url=f"https://example.test/axela/{index}",
                title="2014 Mazda Axela",
                asking_price_cents=1_400_000,
                year=2014,
                make="Mazda",
                model="Axela",
            )
            for index in range(6)
        ]
        result = value_vehicle(target, 350_000, newer)
        self.assertEqual(result.status, "AWAITING_SAFE_EVIDENCE")
        self.assertIsNone(result.market_value_cents)
        self.assertIn("not plausible", result.reason)

    def test_standard_axela_excludes_hybrid_and_mps(self) -> None:
        target = vehicle_from_text("2013 Mazda Axela", "Petrol automatic")
        items = []
        for index in range(5):
            item = RawListing(
                source_id="trademe" if index < 3 else "dealer",
                source_listing_id=f"standard-{index}",
                url=f"https://example.test/standard/{index}",
                title="2013 Mazda Axela Petrol Automatic",
                asking_price_cents=900_000 + index * 10_000,
                year=2013,
                make="Mazda",
                model="Axela",
                fuel_type="PETROL",
            )
            items.append(item)
        items.extend([
            RawListing(source_id="trademe", source_listing_id="hybrid", url="https://example.test/hybrid", title="2013 Mazda Axela Hybrid", asking_price_cents=1_700_000, year=2013, make="Mazda", model="Axela", fuel_type="HYBRID"),
            RawListing(source_id="trademe", source_listing_id="mps", url="https://example.test/mps", title="2013 Mazda Axela MPS", asking_price_cents=2_000_000, year=2013, make="Mazda", model="Axela", fuel_type="PETROL"),
        ])
        result = value_vehicle(target, 500_000, items)
        self.assertEqual(result.status, "VALUED")
        self.assertEqual(result.comparable_count, 5)
        self.assertEqual(result.market_value_cents, 920_000)


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
                algorithm_version="3.0.0",
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
