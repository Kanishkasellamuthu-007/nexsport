"""Unit tests for the Elo rating engine and feedback adjustment.

Run:
    python -m unittest tests.test_elo_service -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services.elo_service import (  # noqa: E402
    K_BASE,
    K_MAX,
    K_PROVISIONAL,
    MAX_FEEDBACK_ADJUSTMENT,
    ResultValidationError,
    actual_score,
    compute_team_update,
    expected_score,
    feedback_adjustment,
    k_factor,
    validate_result_payload,
)


def player(uid, rating, matches=10):
    return {"user_id": uid, "rating": rating, "matches": matches}


class TestExpectedScore(unittest.TestCase):
    def test_equal_ratings_give_half(self):
        self.assertAlmostEqual(expected_score(1000, 1000), 0.5, places=9)

    def test_400_point_advantage_means_90_percent(self):
        # E = 1/(1+10^(-400/400)) = 1/(1+0.1) = 0.909...
        self.assertAlmostEqual(expected_score(1400, 1000), 10 / 11, places=6)
        self.assertAlmostEqual(expected_score(1000, 1400), 1 / 11, places=6)

    def test_symmetry(self):
        self.assertAlmostEqual(
            expected_score(1200, 1050) + expected_score(1050, 1200), 1.0, places=9
        )


class TestActualScore(unittest.TestCase):
    def test_win_draw_loss(self):
        self.assertEqual(actual_score(3, 1), 1.0)
        self.assertEqual(actual_score(2, 2), 0.5)
        self.assertEqual(actual_score(0, 4), 0.0)


class TestKFactor(unittest.TestCase):
    def test_base_for_experienced(self):
        self.assertAlmostEqual(k_factor(10, 0), K_BASE)

    def test_provisional_boost(self):
        self.assertAlmostEqual(k_factor(2, 0), K_PROVISIONAL)

    def test_margin_scaling_and_cap(self):
        self.assertAlmostEqual(k_factor(10, 3), min(K_BASE + 4 * 2, K_MAX))
        # Huge margin cannot exceed K_MAX
        self.assertLessEqual(k_factor(10, 99), K_MAX)

    def test_provisional_with_margin_caps_at_max(self):
        self.assertEqual(k_factor(1, 99), K_MAX)


class TestTeamUpdate(unittest.TestCase):
    def test_equal_teams_small_margin(self):
        team_a = [player("a1", 1000), player("a2", 1000)]
        team_b = [player("b1", 1000), player("b2", 1000)]
        updates = compute_team_update(team_a, team_b, 2, 1)

        # E=0.5, S=1, K=32 -> delta = +16
        self.assertEqual(updates["a1"]["delta"], 16)
        self.assertEqual(updates["b1"]["delta"], -16)
        self.assertEqual(updates["a1"]["new"], 1016)
        # Team coherence: both players on a side move identically.
        self.assertEqual(updates["a1"]["delta"], updates["a2"]["delta"])

    def test_upset_awards_more_points(self):
        # Underdog (1000) beats favourite (1300) 1-0: underdog GAINS a lot.
        result = compute_team_update(
            [player("a", 1000)], [player("b", 1300)], 1, 0)
        underdog_delta = result["a"]["delta"]
        fav_delta = result["b"]["delta"]
        self.assertGreater(underdog_delta, 0)
        self.assertLess(fav_delta, 0)

        # Favourite wins the return match: gains only a little.
        rematch = compute_team_update(
            [player("a", 1000)], [player("b", 1300)], 0, 1)
        self.assertLess(rematch["a"]["delta"], 0)
        self.assertGreater(rematch["b"]["delta"], 0)
        # Upset reward exceeds the favourite's modest win reward.
        self.assertGreater(underdog_delta, rematch["b"]["delta"])

        # Margin scaling: a bigger upset is rewarded even more.
        big = compute_team_update(
            [player("a", 1000)], [player("b", 1300)], 3, 0)
        self.assertGreater(big["a"]["delta"], underdog_delta)

    def test_ratings_stay_within_bounds(self):
        team_a = [player("a", 105)]       # near floor
        team_b = [player("b", 2950)]      # near ceiling
        updates = compute_team_update(team_a, team_b, 5, 0)
        self.assertGreaterEqual(updates["a"]["new"], 100)
        self.assertLessEqual(updates["b"]["new"], 3000)

    def test_empty_team_rejected(self):
        with self.assertRaises(ResultValidationError):
            compute_team_update([], [player("b", 1000)], 1, 0)

    def test_worked_example_from_docs(self):
        # Team A: two players rated 1044 (the questionnaire example).
        # Team B: two players rated 1100. A wins 3-1.
        # Experienced players (10 matches): margin 2 -> K = 32 + 4 = 36.
        team_a = [player("a1", 1044), player("a2", 1044)]
        team_b = [player("b1", 1100), player("b2", 1100)]
        updates = compute_team_update(team_a, team_b, 3, 1)

        mean_a, mean_b = 1044, 1100
        e_a = 1 / (1 + 10 ** ((mean_b - mean_a) / 400))          # 0.4201
        delta = round(36 * (1 - e_a))                             # +20.88 -> 21
        self.assertAlmostEqual(e_a, 0.4201, places=4)
        self.assertEqual(updates["a1"]["delta"], delta)           # +21
        self.assertEqual(updates["a2"]["new"], 1044 + delta)      # 1065
        self.assertEqual(updates["b1"]["delta"], -delta)          # -21


class TestFeedbackAdjustment(unittest.TestCase):
    def test_below_minimum_sample_is_zero(self):
        self.assertEqual(feedback_adjustment([]), 0.0)
        self.assertEqual(
            feedback_adjustment([{"skill_score": 5, "sportsmanship_score": 5}]), 0.0
        )

    def test_neutral_reviews_give_zero(self):
        reviews = [{"skill_score": 3, "sportsmanship_score": 3}] * 3
        self.assertEqual(feedback_adjustment(reviews), 0.0)

    def test_positive_reviews_bounded(self):
        reviews = [{"skill_score": 5, "sportsmanship_score": 5}] * 5
        # avg delta = +4 -> 5*4 = +20 -> capped at +15
        self.assertEqual(feedback_adjustment(reviews), MAX_FEEDBACK_ADJUSTMENT)

    def test_negative_reviews_bounded(self):
        reviews = [{"skill_score": 1, "sportsmanship_score": 1}] * 4
        self.assertEqual(feedback_adjustment(reviews), -MAX_FEEDBACK_ADJUSTMENT)

    def test_mixed_reviews(self):
        reviews = [
            {"skill_score": 4, "sportsmanship_score": 4},
            {"skill_score": 3, "sportsmanship_score": 3},
        ]
        # deltas: (+2, 0) avg = +1 -> +5
        self.assertEqual(feedback_adjustment(reviews), 5.0)


class TestResultValidation(unittest.TestCase):
    def test_valid_result(self):
        out = validate_result_payload({"team_a_score": 3, "team_b_score": 1})
        self.assertEqual(out["winner_side"], "team_a")

    def test_negative_scores_rejected(self):
        with self.assertRaises(ResultValidationError):
            validate_result_payload({"team_a_score": -1, "team_b_score": 2})

    def test_missing_scores_rejected(self):
        with self.assertRaises(ResultValidationError):
            validate_result_payload({"team_a_score": 1})

    def test_unrealistic_scores_rejected(self):
        with self.assertRaises(ResultValidationError):
            validate_result_payload({"team_a_score": 150, "team_b_score": 0})

    def test_draw_derives_unassigned(self):
        out = validate_result_payload({"team_a_score": 2, "team_b_score": 2})
        self.assertEqual(out["winner_side"], "unassigned")

    def test_bad_statistics_rejected(self):
        with self.assertRaises(ResultValidationError):
            validate_result_payload(
                {"team_a_score": 1, "team_b_score": 0, "statistics": [{"goals": -2}]}
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
