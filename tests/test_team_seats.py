"""Seat counting for Developer team invites."""

import unittest
from unittest.mock import patch

from pvmath_auth import team_occupied_seats, can_add_seat, team_member_count


class TeamSeatTests(unittest.TestCase):
    @patch("pvmath_auth._req.get")
    def test_team_member_count(self, mock_get):
        mock_get.return_value.json.return_value = [{"id": "a"}, {"id": "b"}]
        self.assertEqual(team_member_count("owner-uuid"), 2)

    @patch("pvmath_auth.team_member_count", return_value=3)
    def test_team_occupied_includes_owner(self, _mock):
        self.assertEqual(team_occupied_seats("owner-uuid"), 4)

    @patch("pvmath_auth.team_occupied_seats", return_value=5)
    def test_can_add_seat_false_when_full(self, _mock):
        self.assertFalse(can_add_seat("owner-uuid", "developer"))

    @patch("pvmath_auth.team_occupied_seats", return_value=4)
    def test_can_add_seat_true_with_room(self, _mock):
        self.assertTrue(can_add_seat("owner-uuid", "developer"))


if __name__ == "__main__":
    unittest.main()
