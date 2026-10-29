"""Route-level authorization and team-persistence tests."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app import create_app
from backend.services.auth_service import AuthError


class Response:
    def __init__(self, data):
        self.data = data


class TableQuery:
    def __init__(self, admin, table_name):
        self.admin = admin
        self.table_name = table_name

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def single(self):
        self.single_row = True
        return self

    def upsert(self, row, on_conflict=None):
        self.admin.upserts.append((self.table_name, row, on_conflict))
        return self

    def execute(self):
        if getattr(self, "single_row", False):
            return Response(self.admin.tables[self.table_name])
        return Response(self.admin.tables.get(self.table_name, []))


class FakeAdmin:
    def __init__(self, tables=None):
        self.tables = tables or {}
        self.upserts = []
        self.rpc_calls = []

    def table(self, name):
        return TableQuery(self, name)

    def rpc(self, name, arguments):
        self.rpc_calls.append((name, arguments))
        return self

    def execute(self):
        return Response({"ok": True})


def make_app():
    return create_app()


class TestRuntimeConfiguration(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.client = self.app.test_client()

    def test_local_homepage_and_asset_are_served(self):
        homepage = self.client.get("/")
        stylesheet = self.client.get("/css/styles.css")
        try:
            self.assertEqual(homepage.status_code, 200)
            self.assertIn(b"NexSport", homepage.data)
            self.assertEqual(stylesheet.status_code, 200)
        finally:
            homepage.close()
            stylesheet.close()

    def test_config_is_public_and_creates_supabase_client(self):
        with (
            patch("backend.routes.health.config.SUPABASE_URL", "https://project.supabase.co"),
            patch("backend.routes.health.config.SUPABASE_ANON_KEY", "public-anon-key"),
            patch("backend.routes.health.config.SUPABASE_SERVICE_ROLE_KEY", "secret-role-key"),
        ):
            response = self.client.get("/api/config.js")

        self.assertEqual(response.status_code, 200)
        script = response.get_data(as_text=True)
        self.assertIn("https://project.supabase.co", script)
        self.assertIn("public-anon-key", script)
        self.assertIn("supabase.createClient", script)
        self.assertNotIn("secret-role-key", script)

    def test_missing_public_configuration_has_actionable_error(self):
        with (
            patch("backend.routes.health.config.SUPABASE_URL", ""),
            patch("backend.routes.health.config.SUPABASE_ANON_KEY", ""),
        ):
            response = self.client.get("/api/config.js")

        self.assertEqual(response.status_code, 500)
        self.assertIn("SUPABASE_URL", response.get_data(as_text=True))
        self.assertIn("SUPABASE_ANON_KEY", response.get_data(as_text=True))


class TestTeamMigrationPolicy(unittest.TestCase):
    def test_migration_removes_self_team_assignment_and_adds_rpc(self):
        migration = (
            Path(__file__).parents[1]
            / "supabase/migrations/007_team_assignment_authorization.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("create or replace function public.assign_lobby_teams", migration)
        self.assertIn("grant execute on function public.assign_lobby_teams", migration)
        self.assertNotIn("or user_id = auth.uid()", migration)


class TestStatisticsAuthorization(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.client = self.app.test_client()
        self.admin = FakeAdmin()

    def context(self, team_side="team_a", status="completed"):
        return {
            "lobby": {"id": "lobby-1", "host_id": "host", "status": status},
            "participants": [
                {"user_id": "player", "team_side": team_side},
                {"user_id": "other", "team_side": "team_b"},
            ],
        }

    def post(self, context, team_side="team_a"):
        with (
            patch("backend.routes.results.verify_request_user", return_value={"sub": "player"}),
            patch("backend.routes.results._admin", return_value=self.admin),
            patch("backend.routes.results._load_match_admin", return_value=context),
        ):
            return self.client.post(
                "/api/matches/match-1/statistics",
                json={"team_side": team_side, "goals": 2, "assists": 1},
            )

    def test_missing_authentication_is_rejected(self):
        with patch(
            "backend.routes.results.verify_request_user",
            side_effect=AuthError("Missing Authorization header"),
        ):
            response = self.client.post(
                "/api/matches/match-1/statistics",
                json={"team_side": "team_a"},
            )
        self.assertEqual(response.status_code, 401)

    def test_non_participant_is_rejected(self):
        context = self.context()
        context["participants"] = [{"user_id": "other", "team_side": "team_b"}]
        response = self.post(context)
        self.assertEqual(response.status_code, 403)

    def test_incomplete_match_is_rejected(self):
        response = self.post(self.context(status="in_progress"))
        self.assertEqual(response.status_code, 409)

    def test_inconsistent_team_is_rejected(self):
        response = self.post(self.context(team_side="team_a"), team_side="team_b")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.admin.upserts, [])

    def test_authorized_statistics_match_authoritative_team(self):
        response = self.post(self.context(team_side="team_a"))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.admin.upserts[0][1]["team_side"], "team_a")


class TestAssessmentAndVerificationAuthorization(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.client = self.app.test_client()

    def test_assessment_status_requires_authentication(self):
        with patch(
            "backend.routes.questionnaire.verify_request_user",
            side_effect=AuthError("Missing Authorization header"),
        ):
            response = self.client.get("/api/questionnaire/me")
        self.assertEqual(response.status_code, 401)

    def test_verification_status_and_submission_require_authentication(self):
        with patch(
            "backend.routes.verification.verify_request_user",
            side_effect=AuthError("Missing Authorization header"),
        ):
            status = self.client.get("/api/verification/me")
            submission = self.client.post(
                "/api/verification/submit",
                data={"method": "images"},
                content_type="multipart/form-data",
            )
        self.assertEqual(status.status_code, 401)
        self.assertEqual(submission.status_code, 401)

    def test_verification_rejects_missing_or_invalid_evidence_paths(self):
        with patch(
            "backend.routes.verification.verify_request_user",
            return_value={"sub": "player"},
        ):
            missing = self.client.post(
                "/api/verification/submit",
                json={"method": "images", "evidence_paths": []},
            )
            other_users_file = self.client.post(
                "/api/verification/submit",
                json={
                    "method": "images",
                    "evidence_paths": ["another-user/123e4567-e89b-12d3-a456-426614174000.jpg"],
                },
            )
            invalid_type = self.client.post(
                "/api/verification/submit",
                json={
                    "method": "images",
                    "evidence_paths": ["player/123e4567-e89b-12d3-a456-426614174000.exe"],
                },
            )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(other_users_file.status_code, 400)
        self.assertEqual(invalid_type.status_code, 400)

    def test_verification_migration_keeps_evidence_private(self):
        migration = (
            Path(__file__).parents[1]
            / "supabase/migrations/008_skill_verification.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("'skill-evidence',", migration)
        self.assertIn("false,", migration)
        self.assertIn("verification_submissions_select_own", migration)
        self.assertIn("storage.foldername(name)", migration)


class TestTeamAuthorizationAndPersistence(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.client = self.app.test_client()

    def test_team_view_rejects_non_participant(self):
        admin = FakeAdmin(
            {
                "lobbies": {"id": "lobby-1", "host_id": "host"},
                "lobby_participants": [
                    {"user_id": "player", "team_side": "team_a", "profiles": {}}
                ],
            }
        )
        with (
            patch("backend.routes.teams.verify_request_user", return_value={"sub": "outsider"}),
            patch("backend.routes.teams._admin", return_value=admin),
        ):
            response = self.client.get("/api/lobbies/lobby-1/teams")
        self.assertEqual(response.status_code, 403)

    def test_team_view_allows_participant(self):
        admin = FakeAdmin(
            {
                "lobbies": {"id": "lobby-1", "host_id": "host"},
                "lobby_participants": [
                    {"user_id": "player", "team_side": "team_a", "profiles": {}}
                ],
            }
        )
        with (
            patch("backend.routes.teams.verify_request_user", return_value={"sub": "player"}),
            patch("backend.routes.teams._admin", return_value=admin),
        ):
            response = self.client.get("/api/lobbies/lobby-1/teams")
        self.assertEqual(response.status_code, 200)

    def test_team_generation_uses_one_atomic_rpc(self):
        admin = FakeAdmin(
            {
                "lobbies": {
                    "id": "lobby-1",
                    "host_id": "host",
                    "status": "full",
                    "sport_id": "sport-1",
                    "team_size": 2,
                    "min_players": 4,
                    "max_players": 4,
                },
                "lobby_participants": [
                    {"user_id": "a"}, {"user_id": "b"},
                    {"user_id": "c"}, {"user_id": "d"},
                ],
                "player_ratings": [
                    {"user_id": "a", "current_rating": 1000},
                    {"user_id": "b", "current_rating": 1000},
                    {"user_id": "c", "current_rating": 1000},
                    {"user_id": "d", "current_rating": 1000},
                ],
            }
        )
        result = {
            "team_a": [{"user_id": "a", "rating": 1000}, {"user_id": "b", "rating": 1000}],
            "team_b": [{"user_id": "c", "rating": 1000}, {"user_id": "d", "rating": 1000}],
        }
        with (
            patch("backend.routes.teams.verify_request_user", return_value={"sub": "host"}),
            patch("backend.routes.teams._admin", return_value=admin),
            patch("backend.routes.teams.improved_zigzag_split", return_value=result),
        ):
            response = self.client.post("/api/lobbies/lobby-1/teams")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(admin.rpc_calls), 1)
        rpc_name, arguments = admin.rpc_calls[0]
        self.assertEqual(rpc_name, "assign_lobby_teams")
        self.assertEqual(arguments["p_host_id"], "host")
        self.assertEqual(len(arguments["p_assignments"]), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
