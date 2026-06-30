"""Configured NZ inventory and discovery source registry."""

from __future__ import annotations

import re
from urllib.parse import quote_plus

from ..normalization import NormalizedVehicle
from .facebook_history import FacebookHistoryAdapter
from .generic_dealer import GenericDealerAdapter
from .generic import ConfiguredPortalAdapter, PortalConfig, query_text, quoted_query_builder, slug
from .trademe import TradeMeMotorsAdapter


SOURCE_DEFINITIONS = [
    {"id": "facebook_marketplace", "name": "Facebook Marketplace history", "base_url": "https://www.facebook.com/marketplace/", "role": "INVENTORY", "adapter": "facebook_history", "crawl_delay": 2},
    {"id": "trademe_motors", "name": "Trade Me Motors", "base_url": "https://www.trademe.co.nz/a/motors/cars", "role": "INVENTORY", "adapter": "trademe", "crawl_delay": 3},
    {"id": "needacar", "name": "Need A Car", "base_url": "https://www.needacar.co.nz/vehicles", "role": "INVENTORY", "adapter": "needacar", "crawl_delay": 2},
    {"id": "onlycars", "name": "OnlyCars", "base_url": "https://www.onlycars.co.nz/for-sale", "role": "INVENTORY", "adapter": "onlycars", "crawl_delay": 2},
    {"id": "justcar", "name": "JustCar", "base_url": "https://www.justcar.co.nz/used-cars-for-sale", "role": "INVENTORY", "adapter": "justcar", "crawl_delay": 2},
    {"id": "turners", "name": "Turners", "base_url": "https://www.turners.co.nz/Cars/Used-Cars-for-Sale/", "role": "INVENTORY", "adapter": "turners", "crawl_delay": 2},
    {"id": "autoport", "name": "Autoport", "base_url": "https://www.autoport.nz/used-cars-for-sale", "role": "INVENTORY", "adapter": "autoport", "crawl_delay": 10},
    {"id": "generic_dealers", "name": "Discovered NZ dealer inventories", "base_url": "https://local.invalid/dealer-index", "role": "INVENTORY", "adapter": "generic_dealer", "crawl_delay": 2},
    {"id": "motortraders_register", "name": "Motor Vehicle Traders Register", "base_url": "https://www.motortraders.govt.nz/search-the-register/", "role": "DIRECTORY", "adapter": "directory", "crawl_delay": 5},
    {"id": "trademe_dealerships", "name": "Trade Me dealerships", "base_url": "https://www.trademe.co.nz/a/motors/dealerships", "role": "DIRECTORY", "adapter": "directory", "crawl_delay": 3},
    {"id": "autotrader_dealers", "name": "AutoTrader dealers", "base_url": "https://autotrader.co.nz/car-dealers", "role": "DIRECTORY", "adapter": "directory", "crawl_delay": 5},
    {"id": "needacar_dealers", "name": "Need A Car dealers", "base_url": "https://www.needacar.co.nz/dealers", "role": "DIRECTORY", "adapter": "directory", "crawl_delay": 3},
    {"id": "carjam_traders", "name": "CarJam motor traders", "base_url": "https://www.carjam.co.nz/motor-traders/", "role": "DIRECTORY", "adapter": "directory", "crawl_delay": 10},
    {"id": "nzautocar_showroom", "name": "NZ Autocar showroom", "base_url": "https://nzautocar.co.nz/category/showroom/", "role": "DISCOVERY", "adapter": "directory", "crawl_delay": 5},
]


def source_definitions() -> list[dict[str, object]]:
    return [dict(item) for item in SOURCE_DEFINITIONS]


def autoport_search(target: NormalizedVehicle) -> str:
    path = "/".join(value for value in (slug(target.make), slug(target.model)) if value)
    return f"https://www.autoport.nz/used-cars-for-sale/{path}" if path else "https://www.autoport.nz/used-cars-for-sale"


def onlycars_search(target: NormalizedVehicle) -> str:
    make = slug(target.make)
    model = slug(target.model)
    if make and model:
        return f"https://www.onlycars.co.nz/for-sale/make/{make}/model/{model}"
    return f"https://www.onlycars.co.nz/for-sale?keyword={quote_plus(query_text(target))}"


def build_inventory_adapters(
    dealer_sites: list[tuple[str, str | None]] | None = None,
    *,
    include_source_ids: set[str] | None = None,
    exclude_source_ids: set[str] | None = None,
):
    configs = [
        PortalConfig("needacar", "Need A Car", "https://www.needacar.co.nz", quoted_query_builder("https://www.needacar.co.nz/vehicles", "search"), re.compile(r"/(?:vehicle|vehicles)/[^?#]+", re.I), "DEALER", 2),
        PortalConfig("onlycars", "OnlyCars", "https://www.onlycars.co.nz", onlycars_search, re.compile(r"/for-sale/(?!type/|price/|body/|make/[^/]+/model/[^/]+/?$)[^?#]+", re.I), "DEALER", 2),
        PortalConfig("justcar", "JustCar", "https://www.justcar.co.nz", quoted_query_builder("https://www.justcar.co.nz/used-cars-for-sale", "search"), re.compile(r"/used-cars-for-sale/\d+", re.I), "DEALER", 2),
        PortalConfig("turners", "Turners", "https://www.turners.co.nz", quoted_query_builder("https://www.turners.co.nz/Cars/Used-Cars-for-Sale/", "search"), re.compile(r"/Cars/Used-Cars-for-Sale/.+/\d+", re.I), "DEALER", 2),
        PortalConfig("autoport", "Autoport", "https://www.autoport.nz", autoport_search, re.compile(r"/(?:vehicle|used-cars-for-sale)/.+(?:\d{4,}|-[a-z0-9]{6,})", re.I), "DEALER", 10),
    ]
    adapters = [
        FacebookHistoryAdapter(),
        TradeMeMotorsAdapter(),
        *(ConfiguredPortalAdapter(config) for config in configs),
        GenericDealerAdapter(dealer_sites or []),
    ]
    return [
        adapter for adapter in adapters
        if (include_source_ids is None or adapter.source_id in include_source_ids)
        and (exclude_source_ids is None or adapter.source_id not in exclude_source_ids)
    ]
