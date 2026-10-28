"""Unit tests for the Haversine implementation, using well-known coordinate
pairs with independently verifiable distances.

Run:
    python -m unittest tests.test_geo_service -v
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services.geo_service import (  # noqa: E402
    GeoValidationError,
    bounding_box,
    filter_lobbies_by_distance,
    haversine_distance_km,
    validate_latitude,
    validate_longitude,
    validate_radius,
)


class TestHaversineKnownPairs(unittest.TestCase):
    def test_mumbai_to_delhi_about_1150_km(self):
        # Mumbai (Bandra) -> Delhi (India Gate). Published great-circle ~1150 km.
        d = haversine_distance_km(19.0760, 72.8777, 28.6129, 77.2295)
        self.assertAlmostEqual(d, 1150, delta=30)

    def test_mumbai_to_bengaluru_about_845_km(self):
        d = haversine_distance_km(19.0760, 72.8777, 12.9763, 77.5929)
        self.assertAlmostEqual(d, 845, delta=30)

    def test_zero_distance_for_identical_points(self):
        d = haversine_distance_km(19.0760, 72.8777, 19.0760, 72.8777)
        self.assertAlmostEqual(d, 0.0, places=6)

    def test_one_degree_latitude_is_about_111_km(self):
        # Along a meridian 1 deg latitude ~ 111.2 km (varies slightly).
        d = haversine_distance_km(10.0, 77.0, 11.0, 77.0)
        self.assertAlmostEqual(d, 111.2, delta=0.5)

    def test_one_degree_longitude_shrinks_with_latitude(self):
        # At the equator 1 deg lon ~ 111.3 km; at 60N it halves (~55.7 km).
        eq = haversine_distance_km(0.0, 0.0, 0.0, 1.0)
        n60 = haversine_distance_km(60.0, 0.0, 60.0, 1.0)
        self.assertAlmostEqual(eq, 111.3, delta=0.5)
        self.assertAlmostEqual(n60, 55.7, delta=0.5)
        self.assertAlmostEqual(n60, eq / 2, delta=0.5)

    def test_symmetry(self):
        a = haversine_distance_km(18.9440, 72.8235, 12.9763, 77.5929)
        b = haversine_distance_km(12.9763, 77.5929, 18.9440, 72.8235)
        self.assertAlmostEqual(a, b, places=6)


class TestValidation(unittest.TestCase):
    def test_invalid_latitude_rejected(self):
        for bad in (91, -91, "abc", None, float("nan")):
            with self.assertRaises(GeoValidationError):
                validate_latitude(bad)

    def test_invalid_longitude_rejected(self):
        for bad in (181, -181, "xyz", None):
            with self.assertRaises(GeoValidationError):
                validate_longitude(bad)

    def test_invalid_radius_rejected(self):
        for bad in (0, -5, 0.2, 101, "soon", None, float("nan")):
            with self.assertRaises(GeoValidationError):
                validate_radius(bad)

    def test_valid_values_pass(self):
        self.assertEqual(validate_latitude(-89.9), -89.9)
        self.assertEqual(validate_longitude(180), 180.0)
        self.assertEqual(validate_radius("10"), 10.0)


class TestFiltering(unittest.TestCase):
    LOBBIES = [
        {"id": "a", "latitude": 19.1197, "longitude": 72.8464},  # ~5.9 km from origin
        {"id": "b", "latitude": 19.0330, "longitude": 73.0297},  # ~16.7 km (Vashi)
        {"id": "c", "latitude": 19.0, "longitude": 72.84},       # ~9.3 km
        {"id": "bad", "latitude": "nan", "longitude": None},     # malformed
    ]

    def test_nearest_first_and_radius_respected(self):
        results = filter_lobbies_by_distance(self.LOBBIES, 19.0760, 72.8777, 15)
        ids = [lb["id"] for lb, _ in results]
        self.assertEqual(ids, ["a", "c"])   # nearest first, b (>15km) excluded
        self.assertNotIn("bad", ids)        # malformed skipped, no crash
        for _, dist in results:
            self.assertLessEqual(dist, 15)

    def test_outside_radius_excluded(self):
        # 'a' is 5.9 km away, so a 5 km radius excludes everything.
        results = filter_lobbies_by_distance(self.LOBBIES, 19.0760, 72.8777, 5)
        self.assertEqual(len(results), 0)
        # A 6 km radius catches exactly the nearest one.
        results6 = filter_lobbies_by_distance(self.LOBBIES, 19.0760, 72.8777, 6)
        self.assertEqual([lb["id"] for lb, _ in results6], ["a"])


class TestBoundingBox(unittest.TestCase):
    def test_box_contains_target_point(self):
        box = bounding_box(19.0760, 72.8777, 15)
        # Delhi is ~1150 km away -> must be OUTSIDE a 15 km box.
        outside = not (box["min_lat"] <= 28.6129 <= box["max_lat"]
                       and box["min_lon"] <= 77.2295 <= box["max_lon"])
        self.assertTrue(outside)
        # A point ~5 km north of origin must be INSIDE.
        inside_lat = 19.0760 + 5 / 111.32
        self.assertTrue(box["min_lat"] <= inside_lat <= box["max_lat"])

    def test_box_is_symmetric(self):
        box = bounding_box(10.0, 20.0, 10)
        self.assertAlmostEqual(box["max_lat"] - 10.0, 10.0 - box["min_lat"], places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
