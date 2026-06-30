"""Tests for RevenueIQ screening engine."""

import unittest

from revenueiq.engine import RevenueIQRequest, run_revenue_analysis


class RevenueIQTests(unittest.TestCase):
    def test_germany_sat_screening(self) -> None:
        result = run_revenue_analysis(
            RevenueIQRequest(
                country="Germany",
                land_use="Standard",
                mount_type="Single-Axis Tracker",
                dc_kwp=3942.4,
                annual_mwh=4522,
                terrain_grade="challenging",
            )
        )
        self.assertTrue(result.success)
        self.assertGreater(result.annual_revenue_eur_lo, 200_000)
        self.assertGreater(result.total_capex_eur_lo, 2_000_000)
        self.assertIsNotNone(result.payback_years_lo)
        self.assertIsNotNone(result.lcoe_eur_mwh_lo)

    def test_missing_inputs(self) -> None:
        result = run_revenue_analysis(RevenueIQRequest())
        self.assertFalse(result.success)
        self.assertTrue(len(result.errors) >= 2)


if __name__ == "__main__":
    unittest.main()
