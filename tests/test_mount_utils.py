"""Tests for LayoutIQ → YieldIQ mount resolution."""

import unittest

from pvmath_workflow.mount_utils import (
    layout_row_is_tracker,
    resolve_mount_type,
    yield_config_key_from_layout_row,
    yield_mount_filter,
)


class MountUtilsTests(unittest.TestCase):
    def test_sat_row_from_config_key(self) -> None:
        row = {"config_key": "SAT_1P", "mount_type": "Single-Axis Tracker", "n_portrait": 1}
        self.assertTrue(layout_row_is_tracker(row))
        self.assertEqual(resolve_mount_type("Compare FT & SAT", row), "Single-Axis Tracker")
        self.assertEqual(yield_config_key_from_layout_row(row), "1P Tracker")
        self.assertEqual(yield_mount_filter("Compare FT & SAT", row), "sat")

    def test_compare_without_row_falls_back_fixed(self) -> None:
        self.assertEqual(resolve_mount_type("Compare FT & SAT"), "Fixed Tilt")
        self.assertEqual(yield_mount_filter("Compare FT & SAT", None), "all")


if __name__ == "__main__":
    unittest.main()
