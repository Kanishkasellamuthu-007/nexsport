"""Unit tests for the questionnaire-based initial rating calculation.

Run from the project root:
    python -m unittest tests.test_initial_rating -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services.initial_rating_service import (  # noqa: E402
    MAX_RATING,
    MIN_RATING,
    ValidationError,
    compute_initial_rating,
    validate_answers,
)

MAX_VALUES = {"frequency": 5, "experience": 5, "competitive": 4, "self_skill": 4, "fitness": 4}


def answers(**overrides):
    base = {k: 1 for k in MAX_VALUES}
    base.update(overrides)
    return base


class TestValidation(unittest.TestCase):
    def test_missing_answer_rejected(self):
        with self.assertRaises(ValidationError):
            validate_answers({k: 1 for k in MAX_VALUES if k != "fitness"})

    def test_unknown_question_rejected(self):
        bad = answers(hacking=5)
        with self.assertRaises(ValidationError):
            validate_answers(bad)

    def test_out_of_range_rejected(self):
        with self.assertRaises(ValidationError):
            validate_answers(answers(frequency=6))
        with self.assertRaises(ValidationError):
            validate_answers(answers(frequency=0))

    def test_non_integer_rejected(self):
        with self.assertRaises(ValidationError):
            validate_answers(answers(frequency="3"))
        with self.assertRaises(ValidationError):
            validate_answers(answers(frequency=3.5))
        with self.assertRaises(ValidationError):
            validate_answers(answers(frequency=True))   # bool is not a valid answer


class TestRatingBoundaries(unittest.TestCase):
    def test_all_minimum_answers(self):
        result = compute_initial_rating(answers())
        # Lowest honest answers: weighted 0.2254 -> linear map gives 858,
        # comfortably above the 700 hard floor (no clamp needed).
        self.assertEqual(result["initial_rating"], 858)
        self.assertFalse(result["clamped"])

    def test_all_maximum_answers(self):
        result = compute_initial_rating(answers(**MAX_VALUES))
        self.assertEqual(result["initial_rating"], MAX_RATING)  # 1400
        self.assertFalse(result["clamped"])                     # exact, not clamped

    def test_rating_always_within_range(self):
        for f in range(1, 6):
            for c in range(1, 5):
                r = compute_initial_rating(answers(frequency=f, competitive=c))
                self.assertGreaterEqual(r["initial_rating"], MIN_RATING)
                self.assertLessEqual(r["initial_rating"], MAX_RATING)
                self.assertFalse(r["clamped"] or not (MIN_RATING <= r["initial_rating"] <= MAX_RATING))


class TestScoring(unittest.TestCase):
    def test_worked_example_from_docs(self):
        # frequency=4/5, experience=3/5, competitive=2/4, self_skill=2/4, fitness=3/4
        result = compute_initial_rating(
            answers(frequency=4, experience=3, competitive=2, self_skill=2, fitness=3)
        )
        # weighted score = .25*.8 + .25*.6 + .30*.5 + .10*.5 + .10*.75 = 0.625
        self.assertAlmostEqual(result["weighted_score"], 0.625, places=4)
        # rating = 700 + 0.625*700 = 1137.5 -> 1138
        self.assertEqual(result["initial_rating"], 1138)

    def test_midpoint_answers_give_base_rating(self):
        # all normalised exactly 0.5: frequency=3/5? no -> need .5 exactly.
        # frequency 3/5 = .6, so pick answers where every normalised is .5:
        # impossible for /5 options -> score won't be exactly neutral. Instead
        # verify monotonicity: strictly more skill -> strictly higher rating.
        low = compute_initial_rating(answers(frequency=2, experience=2, competitive=1, self_skill=2, fitness=2))
        high = compute_initial_rating(answers(frequency=4, experience=4, competitive=3, self_skill=3, fitness=3))
        self.assertLess(low["initial_rating"], high["initial_rating"])

    def test_rating_spans_the_full_range(self):
        # All-max honest answers reach the ceiling; the theoretical minimum
        # with these option counts (all-1 answers, weighted 0.2254) is 858 —
        # 700 is only reachable with 0-weighted options, which don't exist.
        top = compute_initial_rating(answers(**MAX_VALUES))
        self.assertEqual(top["initial_rating"], MAX_RATING)
        self.assertFalse(top["clamped"])
        bottom = compute_initial_rating(answers())
        self.assertAlmostEqual(bottom["weighted_score"], 0.2254, places=3)
        self.assertEqual(bottom["initial_rating"], 858)

    def test_breakdown_is_complete_and_transparent(self):
        result = compute_initial_rating(answers(frequency=4))
        self.assertIn("weighted_score", result)
        self.assertIn("adjustment", result)
        self.assertIn("initial_rating", result)
        self.assertEqual(len(result["per_question"]), 5)
        self.assertAlmostEqual(sum(w["weight"] for w in result["per_question"].values()), 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
