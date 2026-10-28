"""Unit tests for the Improved Greedy Zig-Zag Split Algorithm.

Run:
    python -m unittest tests.test_team_split -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.algorithms.team_split import (  # noqa: E402
    TeamSplitError,
    improved_zigzag_split,
    zigzag_baseline,
)


def players(*ratings):
    return [
        {"user_id": f"p{i:02d}", "rating": r} for i, r in enumerate(ratings)
    ]


class TestValidation(unittest.TestCase):
    def test_empty_input_rejected(self):
        with self.assertRaises(TeamSplitError):
            improved_zigzag_split([])
        with self.assertRaises(TeamSplitError):
            zigzag_baseline([])

    def test_odd_count_rejected(self):
        with self.assertRaises(TeamSplitError):
            improved_zigzag_split(players(1000, 1001, 1002))

    def test_wrong_expected_count_rejected(self):
        with self.assertRaises(TeamSplitError):
            improved_zigzag_split(players(1000, 1010, 1020, 1030), expected_count=10)

    def test_duplicate_ids_rejected(self):
        dupes = [{"user_id": "x", "rating": 1000}, {"user_id": "x", "rating": 1000}]
        with self.assertRaises(TeamSplitError):
            improved_zigzag_split(dupes)

    def test_missing_fields_and_bad_ratings(self):
        with self.assertRaises(TeamSplitError):
            improved_zigzag_split([{"user_id": "a"}])
        with self.assertRaises(TeamSplitError):
            improved_zigzag_split([{"user_id": "a", "rating": "high"}])
        with self.assertRaises(TeamSplitError):
            improved_zigzag_split([{"user_id": "a", "rating": -5}])


class TestStructure(unittest.TestCase):
    def test_ten_players_equal_teams(self):
        result = improved_zigzag_split(players(
            1200, 1150, 1100, 1050, 1000, 980, 950, 900, 850, 800))
        self.assertEqual(len(result["team_a"]), 5)
        self.assertEqual(len(result["team_b"]), 5)
        ids = {p["user_id"] for p in result["team_a"] + result["team_b"]}
        self.assertEqual(len(ids), 10)          # no duplicates, none missing
        for p in result["team_a"] + result["team_b"]:
            self.assertIsInstance(p["rating"], int)  # ratings untouched

    def test_twenty_two_players(self):
        ratings = [1900 - i * 37 for i in range(22)]
        result = improved_zigzag_split(players(*ratings))
        self.assertEqual(result["team_size"], 11)
        self.assertEqual(len(result["team_a"]), 11)
        self.assertEqual(len(result["team_b"]), 11)
        self.assertTrue(result["rating_difference"] >= 0)

    def test_determinism(self):
        ps = players(1500, 1400, 1300, 1200, 1100, 1000)
        r1 = improved_zigzag_split(list(ps))
        r2 = improved_zigzag_split(list(ps))
        self.assertEqual(r1, r2)


class TestQuality(unittest.TestCase):
    def test_improvement_never_worse_than_baseline(self):
        cases = [
            players(2000, 1500, 1400, 900),
            players(1800, 1750, 1200, 1150, 600, 550),
            players(*[2100 - i * 111 for i in range(10)]),
            players(*[1500 + (i * 79 % 400) for i in range(22)]),
        ]
        for ps in cases:
            base = zigzag_baseline(list(ps))["rating_difference"]
            improved = improved_zigzag_split(list(ps))["rating_difference"]
            self.assertLessEqual(improved, base)

    def test_identical_ratings_perfect_balance(self):
        ps = players(*[1000] * 10)
        result = improved_zigzag_split(ps)
        self.assertEqual(result["rating_difference"], 0)
        self.assertFalse(result["improved"])  # no improvement possible

    def test_no_improvement_possible_flag(self):
        # Baseline already perfect -> improved flag False
        ps = players(1000, 1000, 1000, 1000)
        result = improved_zigzag_split(ps)
        self.assertEqual(result["rating_difference"], 0)
        self.assertFalse(result["improved"])

    def test_extreme_difference_case(self):
        # One superstar (2900) + one average vs two novices — the superstar
        # dominates one side, so the difference can't vanish, but the
        # algorithm must still minimise it with equal team sizes.
        ps = players(2900, 1000, 1000, 1000)
        result = improved_zigzag_split(ps)
        self.assertEqual(len(result["team_a"]), 2)
        self.assertEqual(len(result["team_b"]), 2)
        self.assertGreater(result["rating_difference"], 0)
        # And the improved split must be no worse than the baseline.
        base = zigzag_baseline(list(ps))["rating_difference"]
        self.assertLessEqual(result["rating_difference"], base)

    def test_report_example_docstring_case(self):
        # Case where improvement step visibly helps the baseline.
        ps = players(1900, 1800, 1000, 900)
        base = zigzag_baseline(list(ps))
        imp = improved_zigzag_split(list(ps))
        # baseline: A={1900,1000}=2900  B={1800,900}=2700  diff 200
        self.assertEqual(base["rating_difference"], 200)
        # improvement: swap to A={1900,900}=2800  B={1800,1000}=2800  diff 0
        self.assertEqual(imp["rating_difference"], 0)
        self.assertTrue(imp["improved"])


class TestTotals(unittest.TestCase):
    def test_totals_and_averages_consistent(self):
        ps = players(1200, 1150, 1100, 1050)
        r = improved_zigzag_split(ps)
        self.assertEqual(
            r["team_a_total"],
            sum(p["rating"] for p in r["team_a"]),
        )
        self.assertEqual(
            r["team_b_average"], round(r["team_b_total"] / len(r["team_b"]), 1)
        )
        self.assertEqual(
            r["rating_difference"], abs(r["team_a_total"] - r["team_b_total"])
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
