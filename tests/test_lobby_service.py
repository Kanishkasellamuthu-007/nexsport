"""Unit tests for lobby management rules: input validation, the lobby state
machine, and join/leave/start precondition logic.

The concurrency guarantees themselves (duplicate joins, capacity overbooking)
are enforced by the PostgreSQL RPC functions (migration 005) and covered by
the SQL integration checklist in docs/LOBBIES.md — these tests cover the
Python-side rules.

Run:
    python -m unittest tests.test_lobby_service -v
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.services.lobby_service import (  # noqa: E402
    LobbyValidationError,
    can_transition,
    check_cancel_preconditions,
    check_join_preconditions,
    check_start_preconditions,
    parse_future_datetime,
    validate_lobby_input,
)

UUID = "123e4567-e89b-12d3-a456-426614174000"
FUTURE = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()


def payload(**overrides):
    base = {
        "sport_id": UUID,
        "title": "Saturday Football",
        "latitude": 19.076,
        "longitude": 72.8777,
        "scheduled_at": FUTURE,
        "team_size": 5,
        "min_players": 10,
        "max_players": 10,
    }
    base.update(overrides)
    return base


class TestCreateValidation(unittest.TestCase):
    def test_valid_payload_passes(self):
        fields = validate_lobby_input(payload())
        self.assertEqual(fields["team_size"], 5)
        self.assertEqual(fields["max_players"], 10)

    def test_past_datetime_rejected(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with self.assertRaises(LobbyValidationError):
            validate_lobby_input(payload(scheduled_at=past))

    def test_missing_datetime_rejected(self):
        with self.assertRaises(LobbyValidationError):
            validate_lobby_input(payload(scheduled_at=None))

    def test_bad_coordinates_rejected(self):
        with self.assertRaises(LobbyValidationError):
            validate_lobby_input(payload(latitude=95))
        with self.assertRaises(LobbyValidationError):
            validate_lobby_input(payload(longitude=-200))
        with self.assertRaises(LobbyValidationError):
            validate_lobby_input(payload(latitude="north"))

    def test_team_size_bounds(self):
        with self.assertRaises(LobbyValidationError):
            validate_lobby_input(payload(team_size=0))
        with self.assertRaises(LobbyValidationError):
            validate_lobby_input(payload(team_size=16))

    def test_capacity_must_fit_two_teams(self):
        # 5-a-side needs at least 10 players total
        with self.assertRaises(LobbyValidationError):
            validate_lobby_input(payload(team_size=5, max_players=9))
        ok = validate_lobby_input(payload(team_size=5, max_players=10))
        self.assertEqual(ok["max_players"], 10)

    def test_min_players_window(self):
        with self.assertRaises(LobbyValidationError):
            validate_lobby_input(payload(min_players=8))    # < 2*team_size
        with self.assertRaises(LobbyValidationError):
            validate_lobby_input(payload(min_players=11))   # > max_players

    def test_title_bounds_and_bad_sport(self):
        with self.assertRaises(LobbyValidationError):
            validate_lobby_input(payload(title="ab"))
        with self.assertRaises(LobbyValidationError):
            validate_lobby_input(payload(sport_id="not-a-uuid"))


class TestStateMachine(unittest.TestCase):
    def test_happy_path(self):
        self.assertTrue(can_transition("open", "full"))
        self.assertTrue(can_transition("full", "in_progress"))
        self.assertTrue(can_transition("in_progress", "completed"))

    def test_cannot_join_closed_or_started(self):
        # (translated into transition terms: full/cancelled lobbies reject joins)
        self.assertFalse(can_transition("cancelled", "open"))
        self.assertFalse(can_transition("completed", "open"))
        self.assertFalse(can_transition("in_progress", "open"))

    def test_terminal_states_frozen(self):
        for target in ("open", "full", "in_progress", "completed", "cancelled"):
            self.assertFalse(can_transition("completed", target))
            self.assertFalse(can_transition("cancelled", target))

    def test_cancel_allowed_from_active_states(self):
        self.assertTrue(can_transition("open", "cancelled"))
        self.assertTrue(can_transition("full", "cancelled"))
        self.assertTrue(can_transition("in_progress", "cancelled"))


class TestJoinPreconditions(unittest.TestCase):
    LOBBY = {"id": "L1", "status": "open", "max_players": 10, "min_players": 6}

    def test_join_open_with_space_ok(self):
        self.assertIsNone(check_join_preconditions(self.LOBBY, 3))

    def test_join_closed_rejected(self):
        for status in ("full", "in_progress", "completed", "cancelled"):
            with self.assertRaises(LobbyValidationError):
                check_join_preconditions({**self.LOBBY, "status": status}, 3)

    def test_join_full_rejected(self):
        with self.assertRaises(LobbyValidationError):
            check_join_preconditions(self.LOBBY, 0)


class TestHostControls(unittest.TestCase):
    def test_non_host_cannot_start_or_cancel(self):
        lobby = {"host_id": "host-1", "status": "open", "min_players": 2}
        with self.assertRaises(LobbyValidationError):
            check_start_preconditions(lobby, joined=5, user_id="other")
        with self.assertRaises(LobbyValidationError):
            check_cancel_preconditions(lobby, user_id="other")

    def test_start_below_min_players_rejected(self):
        lobby = {"host_id": "h", "status": "open", "min_players": 6}
        with self.assertRaises(LobbyValidationError):
            check_start_preconditions(lobby, joined=5, user_id="h")
        self.assertIsNone(check_start_preconditions(lobby, joined=6, user_id="h"))

    def test_start_closed_lobby_rejected(self):
        lobby = {"host_id": "h", "status": "cancelled", "min_players": 2}
        with self.assertRaises(LobbyValidationError):
            check_start_preconditions(lobby, joined=5, user_id="h")


class TestDatetimeParsing(unittest.TestCase):
    def test_future_ok(self):
        when = parse_future_datetime(FUTURE)
        self.assertIsNotNone(when.tzinfo)

    def test_garbage_rejected(self):
        with self.assertRaises(LobbyValidationError):
            parse_future_datetime("tomorrow evening")


if __name__ == "__main__":
    unittest.main(verbosity=2)
