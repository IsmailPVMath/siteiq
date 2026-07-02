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
                dc_kwp=14000,
                annual_mwh=19000,
                site_area_ha=50,
                mean_slope_pct=4,
            )
        )
        self.assertTrue(result.success)
        self.assertGreaterEqual(result.capex_lo_eur, 7_000_000)
        self.assertLessEqual(result.capex_hi_eur, 14_000_000)
        self.assertIsNotNone(result.payback_lo_yr)
        self.assertIsNotNone(result.lcoe_lo_eur_mwh)
        self.assertIn(result.tariff_mode, ("GOVT_AUCTION", "PPA", "CUSTOM"))

    def test_spain_strong_band(self) -> None:
        result = run_revenue_analysis(
            RevenueIQRequest(
                country="Spain",
                mount_type="Single-Axis Tracker",
                dc_kwp=35000,
                annual_mwh=70000,
                site_area_ha=100,
            )
        )
        self.assertTrue(result.success)
        self.assertEqual(result.tariff_mode, "PPA")
        self.assertGreater(result.irr_hi_pct or 0, 8)

    def test_us_itc(self) -> None:
        result = run_revenue_analysis(
            RevenueIQRequest(
                country="United States",
                mount_type="Single-Axis Tracker",
                dc_kwp=30000,
                annual_mwh=57000,
            )
        )
        self.assertTrue(result.success)
        self.assertGreater(result.itc_credit_eur, 0)
        self.assertLess(result.effective_capex_hi_eur, result.capex_hi_eur)

    def test_missing_inputs(self) -> None:
        result = run_revenue_analysis(RevenueIQRequest())
        self.assertFalse(result.success)
        self.assertTrue(len(result.errors) >= 2)


if __name__ == "__main__":
    unittest.main()
