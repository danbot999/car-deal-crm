from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.crm_watchdog import process_health
from scripts.valuation_quality_audit import safe_run, source_count


class ValuationAuditTests(unittest.TestCase):
    def test_source_count_ignores_empty_sources(self) -> None:
        self.assertEqual(source_count('{"trademe": 4, "dealer": 2, "empty": 0}'), 2)

    def test_only_current_multi_source_exact_run_is_safe(self) -> None:
        base = {
            "status": "VALUED",
            "algorithm_version": "3.0.0",
            "valuation_method": "EXACT",
            "market_value_cents": 500_000,
            "comparable_count": 5,
            "source_breakdown_json": '{"trademe": 3, "dealer": 2}',
        }
        self.assertTrue(safe_run(base))
        self.assertFalse(safe_run({**base, "algorithm_version": "2.0.0"}))
        self.assertFalse(safe_run({**base, "comparable_count": 4}))
        self.assertFalse(safe_run({**base, "source_breakdown_json": '{"trademe": 5}'}))
        self.assertFalse(safe_run({**base, "market_value_cents": None}))

    @patch("scripts.crm_watchdog.heartbeat_age_seconds", return_value=30.0)
    @patch("scripts.crm_watchdog.read_heartbeat")
    def test_fresh_degraded_heartbeat_is_not_healthy(self, read_heartbeat, _age) -> None:
        read_heartbeat.return_value = {"status": "degraded", "error": "source unavailable"}
        health = process_health("marketplace-monitor", 1_200)
        self.assertTrue(health["responsive"])
        self.assertFalse(health["healthy"])


if __name__ == "__main__":
    unittest.main()
