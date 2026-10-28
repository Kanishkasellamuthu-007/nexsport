"""Chat endpoints powered by GitHub Models open-source LLMs."""
from __future__ import annotations

import logging
from flask import Blueprint, jsonify, request

from backend.config import config
from backend.services.chat_service import (
    DEFAULT_MODEL,
    ChatError,
    get_available_models,
    send_chat_completion,
)

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@chat_bp.get("/models")
def list_models():
    """Return available GitHub open-source models and status."""
    return (
        jsonify(
            {
                "models": get_available_models(),
                "default_model": DEFAULT_MODEL,
                "has_server_token": bool(config.GITHUB_TOKEN and config.GITHUB_TOKEN.strip()),
            }
        ),
        200,
    )


@chat_bp.post("")
def chat_completion():
    """Send conversation messages to GitHub Models inference API.

    JSON payload:
      messages     : list of {role: str, content: str} (required)
      model        : str (optional, default meta/llama-3.1-70b-instruct)
      github_token : str (optional, overrides server token)
      temperature  : float (optional, default 0.7)
      max_tokens   : int (optional, default 1024)

    Header options:
      X-GitHub-Token: overrides server token
    """
    body = request.get_json(silent=True) or {}
    messages = body.get("messages")

    if not isinstance(messages, list) or len(messages) == 0:
        return jsonify({"error": "messages must be a non-empty list of message objects."}), 400

    # Validate message formats
    cleaned_messages = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "user")).strip().lower()
        content = str(msg.get("content", "")).strip()
        if role not in ("system", "user", "assistant"):
            role = "user"
        if content:
            cleaned_messages.append({"role": role, "content": content})

    if not cleaned_messages:
        return jsonify({"error": "No non-empty message content found."}), 400

    model = str(body.get("model", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
    custom_token = (
        request.headers.get("X-GitHub-Token")
        or body.get("github_token")
        or ""
    ).strip() or None

    try:
        temperature = float(body.get("temperature", 0.7))
        temperature = max(0.0, min(temperature, 1.0))
    except (ValueError, TypeError):
        temperature = 0.7

    try:
        max_tokens = int(body.get("max_tokens", 1024))
        max_tokens = max(50, min(max_tokens, 2048))
    except (ValueError, TypeError):
        max_tokens = 1024

    try:
        response_data = send_chat_completion(
            messages=cleaned_messages,
            model=model,
            custom_token=custom_token,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return jsonify(response_data), 200

    except ChatError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during chat completion: %s", exc)
        return jsonify({"error": "Internal server error during chat inference."}), 500

