"""Unit tests for GitHub Models AI Chat service and endpoints."""
from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from backend.app import create_app
from backend.services.chat_service import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    get_available_models,
    get_model_info,
    resolve_token,
    send_chat_completion,
)


class TestChatService(unittest.TestCase):
    """Test backend/services/chat_service.py logic."""

    def test_get_available_models(self):
        models = get_available_models()
        self.assertGreaterEqual(len(models), 4)
        model_ids = [m["id"] for m in models]
        self.assertIn("meta/llama-3.1-70b-instruct", model_ids)
        self.assertIn("mistralai/mistral-large-2407", model_ids)
        self.assertIn("microsoft/phi-3.5-mini-instruct", model_ids)
        self.assertIn("deepseek/deepseek-r1", model_ids)

    def test_get_model_info(self):
        m = get_model_info("meta/llama-3.1-70b-instruct")
        self.assertIsNotNone(m)
        self.assertEqual(m["family"], "Llama")

        # Test case-insensitivity and alt_id
        m_alt = get_model_info("Meta-Llama-3.1-70B-Instruct")
        self.assertIsNotNone(m_alt)
        self.assertEqual(m_alt["id"], "meta/llama-3.1-70b-instruct")

        # Nonexistent model
        self.assertIsNone(get_model_info("unknown-model-xyz"))

    def test_resolve_token(self):
        # Custom token takes priority
        self.assertEqual(resolve_token("custom_pat_123"), "custom_pat_123")

        with patch("backend.services.chat_service.config.GITHUB_TOKEN", "server_pat_456"):
            self.assertEqual(resolve_token(None), "server_pat_456")
            self.assertEqual(resolve_token("override_pat"), "override_pat")

    def test_fallback_response_no_token(self):
        with patch("backend.services.chat_service.config.GITHUB_TOKEN", ""):
            res = send_chat_completion(
                messages=[{"role": "user", "content": "How do I warm up before football?"}],
                model=DEFAULT_MODEL,
                custom_token=None,
            )
            self.assertTrue(res["is_fallback"])
            self.assertIn("Dynamic", res["reply"])
            self.assertEqual(res["model"], DEFAULT_MODEL)

    @patch("backend.services.chat_service.httpx.Client")
    def test_github_models_success(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Use a 1-2-1 diamond formation for 5v5 soccer."}}],
            "usage": {"prompt_tokens": 15, "completion_tokens": 20, "total_tokens": 35},
        }
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        res = send_chat_completion(
            messages=[{"role": "user", "content": "What formation should we play?"}],
            model="meta/llama-3.1-70b-instruct",
            custom_token="ghp_test_token_123",
        )

        self.assertFalse(res["is_fallback"])
        self.assertIn("1-2-1 diamond", res["reply"])
        self.assertEqual(res["model"], "meta/llama-3.1-70b-instruct")
        self.assertIn("GitHub Models", res["provider"])


class TestChatRoutes(unittest.TestCase):
    """Test Flask routes for chat."""

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_get_models(self):
        resp = self.client.get("/api/chat/models")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("models", data)
        self.assertIn("default_model", data)
        self.assertIn("has_server_token", data)
        self.assertEqual(data["default_model"], DEFAULT_MODEL)

    def test_chat_invalid_payload(self):
        # Empty payload
        resp = self.client.post("/api/chat", json={})
        self.assertEqual(resp.status_code, 400)

        # Messages not a list
        resp = self.client.post("/api/chat", json={"messages": "hello"})
        self.assertEqual(resp.status_code, 400)

        # Empty messages list
        resp = self.client.post("/api/chat", json={"messages": []})
        self.assertEqual(resp.status_code, 400)

    def test_chat_fallback_flow(self):
        # When no token is configured on server or in payload
        with patch("backend.services.chat_service.config.GITHUB_TOKEN", ""):
            resp = self.client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "Explain Elo rating updates"}],
                    "model": "meta/llama-3.1-70b-instruct",
                },
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertIn("reply", data)
            self.assertTrue(data.get("is_fallback"))
            self.assertIn("Elo", data["reply"])

    @patch("backend.services.chat_service.httpx.Client")
    def test_chat_with_custom_header_token(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "DeepSeek R1 reasoning: prioritize midfield control."}}],
            "usage": {"total_tokens": 40},
        }
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        resp = self.client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "How do we win against a fast team?"}],
                "model": "deepseek/deepseek-r1",
            },
            headers={"X-GitHub-Token": "ghp_mock_token_abc"},
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data.get("is_fallback"))
        self.assertIn("DeepSeek R1", data["reply"])


if __name__ == "__main__":
    unittest.main()

