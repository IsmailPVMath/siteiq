"""Regression tests — Folium Draw must not rerun on every vertex click."""
import unittest

from pvmath_folium_draw import (
    FOLIUM_DRAW_FORBIDDEN,
    FOLIUM_DRAW_RETURNED_OBJECTS,
    FOLIUM_PIN_RETURNED_OBJECTS,
    drawing_to_polygon_latlon,
    validate_draw_returned_objects,
)


class TestFoliumDrawContract(unittest.TestCase):
    def test_draw_objects_are_last_active_drawing_only(self):
        self.assertEqual(FOLIUM_DRAW_RETURNED_OBJECTS, ("last_active_drawing",))
        self.assertEqual(FOLIUM_DRAW_FORBIDDEN, frozenset({"all_drawings", "last_clicked"}))

    def test_pin_mode_uses_last_clicked_not_draw_forbidden(self):
        self.assertEqual(FOLIUM_PIN_RETURNED_OBJECTS, ("last_clicked",))
        self.assertNotIn("all_drawings", FOLIUM_PIN_RETURNED_OBJECTS)

    def test_validate_rejects_all_drawings(self):
        with self.assertRaises(ValueError) as ctx:
            validate_draw_returned_objects(["last_active_drawing", "all_drawings"])
        self.assertIn("all_drawings", str(ctx.exception))

    def test_validate_rejects_last_clicked_with_draw(self):
        with self.assertRaises(ValueError):
            validate_draw_returned_objects(["last_clicked", "last_active_drawing"])

    def test_validate_rejects_none(self):
        with self.assertRaises(ValueError):
            validate_draw_returned_objects(None)

    def test_validate_accepts_contract(self):
        validate_draw_returned_objects(FOLIUM_DRAW_RETURNED_OBJECTS)

    def test_drawing_to_polygon_latlon_closed_ring(self):
        drawing = {
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[10.0, 48.0], [11.0, 48.0], [11.0, 49.0], [10.0, 48.0]]],
            }
        }
        poly = drawing_to_polygon_latlon(drawing)
        self.assertEqual(len(poly), 4)
        self.assertEqual(poly[0], [48.0, 10.0])


if __name__ == "__main__":
    unittest.main()
