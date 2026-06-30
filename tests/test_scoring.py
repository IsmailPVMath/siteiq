"""Tests for PVMath composite scoring (Jun 2026 weights)."""

import unittest

from pvmath_workflow.score_config import calculate_pvmath_score
from pvmath_workflow.scoring import unified_pvmath_score, yield_subscore


class ScoringWeightsTests(unittest.TestCase):
    def test_partial_weights_sum_to_100_with_equal_inputs(self) -> None:
        scores = {"regulatory": 80, "terrain": 80, "land": 80, "flood": 80, "solar": 80}
        self.assertEqual(calculate_pvmath_score(scores, include_yield=False), 80)

    def test_full_weights_include_yield(self) -> None:
        partial = calculate_pvmath_score(
            {"regulatory": 80, "terrain": 80, "land": 80, "flood": 80, "solar": 80},
            include_yield=False,
        )
        full = calculate_pvmath_score(
            {
                "regulatory": 80,
                "terrain": 80,
                "land": 80,
                "flood": 80,
                "solar": 80,
                "yield": 90,
            },
            include_yield=True,
        )
        self.assertGreater(full, partial)

    def test_regional_yield_bavaria_not_punished(self) -> None:
        de_score = yield_subscore(1375, country="Germany")
        global_score = yield_subscore(1375)  # falls back to lat/lon-less global band
        self.assertGreaterEqual(de_score, 78)
        self.assertGreater(de_score, global_score - 5)

    def test_unified_includes_viability(self) -> None:
        result = unified_pvmath_score(
            solar_score=80,
            terrain_score=75,
            flood_score=90,
            land_score=85,
            regulatory_score=85,
            yield_score=82,
            terrain_confirmed=True,
            capacity_mwp=4.0,
        )
        self.assertEqual(result["score_mode"], "full")
        self.assertIn("viability", result)
        self.assertIn("investment_risk", result["viability"])
        self.assertIn("engineering_confidence_stars", result["viability"])


if __name__ == "__main__":
    unittest.main()
