"""NexSport AI Chat Service — Integration with GitHub Models open-source LLMs.

Supports open-weights models provided via GitHub Models Inference API:
- Meta Llama 3.1 (70B / 8B)
- Mistral AI (Large 2 / Small)
- Microsoft Phi (Phi-3.5 Mini / Phi-4)
- DeepSeek (R1)

Authentication:
  Uses a GitHub Personal Access Token (PAT) from GITHUB_TOKEN environment variable,
  or optionally provided by the client in the request.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from backend.config import config

logger = logging.getLogger(__name__)

# List of open-source models available on GitHub Models
AVAILABLE_MODELS: list[dict[str, Any]] = [
    {
        "id": "meta/llama-3.1-70b-instruct",
        "alt_id": "Meta-Llama-3.1-70B-Instruct",
        "name": "Meta Llama 3.1 70B",
        "family": "Llama",
        "provider": "Meta",
        "badge": "Recommended",
        "icon": "🦙",
        "description": "Powerful open-weights model with exceptional depth in sports strategy, coaching, and fitness routines.",
        "recommended": True,
    },
    {
        "id": "meta/llama-3.1-8b-instruct",
        "alt_id": "Meta-Llama-3.1-8B-Instruct",
        "name": "Meta Llama 3.1 8B",
        "family": "Llama",
        "provider": "Meta",
        "badge": "Fast",
        "icon": "⚡",
        "description": "Lightweight, ultra-responsive open model ideal for quick rule lookups and instant answers.",
        "recommended": False,
    },
    {
        "id": "mistralai/mistral-large-2407",
        "alt_id": "Mistral-large-2407",
        "name": "Mistral Large 2",
        "family": "Mistral",
        "provider": "Mistral AI",
        "badge": "Tactical",
        "icon": "🌪️",
        "description": "High-accuracy open model renowned for sharp reasoning, team formations, and positioning analysis.",
        "recommended": False,
    },
    {
        "id": "mistralai/mistral-small",
        "alt_id": "Mistral-small",
        "name": "Mistral Small",
        "family": "Mistral",
        "provider": "Mistral AI",
        "badge": "Snappy",
        "icon": "💨",
        "description": "Fast and lightweight Mistral model tuned for quick on-the-field advice and drills.",
        "recommended": False,
    },
    {
        "id": "microsoft/phi-3.5-mini-instruct",
        "alt_id": "Phi-3.5-mini-instruct",
        "name": "Microsoft Phi-3.5 Mini",
        "family": "Phi",
        "provider": "Microsoft",
        "badge": "Compact SLM",
        "icon": "🔬",
        "description": "State-of-the-art small language model with high efficiency, rapid inference, and strict factual recall.",
        "recommended": False,
    },
    {
        "id": "deepseek/deepseek-r1",
        "alt_id": "DeepSeek-R1",
        "name": "DeepSeek R1",
        "family": "DeepSeek",
        "provider": "DeepSeek",
        "badge": "Reasoning",
        "icon": "🧠",
        "description": "Advanced reasoning open-source model specializing in deep step-by-step game breakdowns.",
        "recommended": False,
    },
]

DEFAULT_MODEL = "meta/llama-3.1-70b-instruct"

SYSTEM_PROMPT = """You are NexSport Coach, an intelligent, athletic, and encouraging AI sports assistant embedded directly into NexSport.

About NexSport:
- NexSport is a sports matchmaking platform connecting casual players who want to play in free public spaces.
- Key features of NexSport:
  1. Nearby Lobby Discovery: Uses Haversine distance formula to find matches within a user's radius (e.g. 10km) in public grounds.
  2. Baseline Skill Questionnaire: Evaluates fitness, match frequency, and technical experience to assign an initial rating (800 - 1500, baseline 1200).
  3. Elo Rating System: Updates ratings after verified matches based on match outcome and margin of victory (K-factor = 32).
  4. Balanced Team Splitting: Uses a greedy zig-zag algorithm based on Elo ratings to ensure fair, competitive matches.
  5. Supported Sports: Football (Soccer), Basketball, Cricket, Badminton, Volleyball, Tennis, and more.

Your Role as NexSport Coach:
- Provide tactical formations, defensive/offensive schemes, and positioning guidance.
- Answer sports rules, field/court dimensions, referee hand signals, and scoring regulations.
- Create dynamic warm-up drills, cool-downs, and injury prevention exercises.
- Explain NexSport features (how ratings work, how to join lobbies, how team splitting works).
- Give equipment recommendations (shoes, balls, racquets) for playing on different ground surfaces (turf, clay, concrete, grass).

Tone & Formatting:
- Enthusiastic, concise, sports-minded, and structured.
- Use bullet points, bold text, and relevant sports emojis (⚽, 🏀, 🏏, 🏸, 🏐, 🏃, ⚖️).
- If the user asks about something unrelated to sports or NexSport, answer politely but guide them back to sports and fitness.
"""


class ChatError(Exception):
    """Raised when chat operations or API inference fails."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_available_models() -> list[dict[str, Any]]:
    """Return list of supported open-source models for UI selection."""
    return AVAILABLE_MODELS


def get_model_info(model_id: str) -> dict[str, Any] | None:
    """Find model definition by ID or alternate ID."""
    clean_id = model_id.strip().lower()
    for m in AVAILABLE_MODELS:
        if m["id"].lower() == clean_id or m["alt_id"].lower() == clean_id:
            return m
    return None


def resolve_token(custom_token: str | None = None) -> str:
    """Resolve token from custom request header or server configuration."""
    if custom_token and custom_token.strip():
        return custom_token.strip()
    return (config.GITHUB_TOKEN or "").strip()


def send_chat_completion(
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    custom_token: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """Send chat messages to GitHub Models API or smart fallback.

    Args:
        messages: List of message objects with 'role' and 'content'.
        model: Selected GitHub model ID.
        custom_token: Optional GitHub PAT provided by the caller.
        temperature: Creativity parameter (0.0 to 1.0).
        max_tokens: Maximum tokens in response.

    Returns:
        Dictionary with 'reply', 'model', 'provider', and 'usage'.
    """
    if not messages:
        raise ChatError("Message history cannot be empty.", 400)

    token = resolve_token(custom_token)
    model_info = get_model_info(model)
    target_model = model_info["id"] if model_info else model

    # If no GitHub token is present on server or client, use smart fallback
    if not token:
        logger.info("No GitHub token configured. Serving built-in NexSport Coach response.")
        return _generate_fallback_response(messages, target_model)

    # Build messages with system prompt at top
    formatted_messages: list[dict[str, str]] = []
    has_system = any(m.get("role") == "system" for m in messages)
    if not has_system:
        formatted_messages.append({"role": "system", "content": SYSTEM_PROMPT})

    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "").strip()
        if content:
            formatted_messages.append({"role": role, "content": content})

    # Primary and fallback endpoints for GitHub Models
    endpoints = [
        config.GITHUB_MODELS_URL,
        "https://models.inference.ai.azure.com/chat/completions",
    ]

    last_error_msg = ""
    for endpoint in endpoints:
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "NexSport-App/1.0",
            }
            payload = {
                "model": target_model,
                "messages": formatted_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(endpoint, json=payload, headers=headers)

            if resp.status_code == 200:
                data = resp.json()
                reply_content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return {
                    "reply": reply_content,
                    "model": target_model,
                    "model_name": model_info["name"] if model_info else target_model,
                    "provider": "GitHub Models (" + (model_info["provider"] if model_info else "Open Source") + ")",
                    "usage": usage,
                    "is_fallback": False,
                }

            if resp.status_code == 401:
                raise ChatError(
                    "Invalid or expired GitHub Personal Access Token. "
                    "Please verify your token at https://github.com/settings/tokens.",
                    401,
                )
            if resp.status_code == 429:
                raise ChatError(
                    "GitHub Models rate limit reached for your token. "
                    "Please wait a moment or try another model.",
                    429,
                )

            # Try alternate model ID representation if 404 or bad model request
            if resp.status_code in (400, 404) and model_info and "alt_id" in model_info:
                alt_payload = dict(payload)
                alt_payload["model"] = model_info["alt_id"]
                with httpx.Client(timeout=30.0) as client:
                    alt_resp = client.post(endpoint, json=alt_payload, headers=headers)
                if alt_resp.status_code == 200:
                    data = alt_resp.json()
                    return {
                        "reply": data["choices"][0]["message"]["content"],
                        "model": model_info["alt_id"],
                        "model_name": model_info["name"],
                        "provider": f"GitHub Models ({model_info['provider']})",
                        "usage": data.get("usage", {}),
                        "is_fallback": False,
                    }

            last_error_msg = f"Inference returned status {resp.status_code}: {resp.text[:200]}"
            logger.warning("Endpoint %s failed: %s", endpoint, last_error_msg)

        except (httpx.RequestError, httpx.TimeoutException) as exc:
            last_error_msg = f"Network connection error: {exc}"
            logger.warning("Failed connecting to %s: %s", endpoint, exc)
            continue

    # If all endpoints failed or timed out, gracefully return fallback with notice
    logger.error("All GitHub Models endpoints failed. Falling back. Last error: %s", last_error_msg)
    fallback = _generate_fallback_response(messages, target_model)
    fallback["notice"] = (
        "Note: Could not reach GitHub Models live endpoint. Displaying offline NexSport Coach response. "
        + (f"({last_error_msg})" if last_error_msg else "")
    )
    return fallback


def _generate_fallback_response(
    messages: list[dict[str, str]], target_model: str
) -> dict[str, Any]:
    """Provide domain-specific offline sports coaching when no API key is set."""
    last_user_message = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_message = m.get("content", "").strip().lower()
            break

    model_info = get_model_info(target_model)
    model_name = model_info["name"] if model_info else target_model

    # Match intent for rich athletic coaching
    if any(k in last_user_message for k in ("warmup", "warm up", "stretch", "injury", "cool down")):
        content = (
            "### 🏃 10-Minute Dynamic Sports Warm-up Routine\n\n"
            "A proper warm-up activates your central nervous system and lubricates joints:\n\n"
            "1. **Light Pulse Raiser (2 mins)**:\n"
            "   - Jogging at 50% pace with directional changes\n"
            "   - High knees & heel flicks (30s each)\n\n"
            "2. **Dynamic Mobility (4 mins)**:\n"
            "   - **Walking Lunges with Torso Twist**: 10 reps (stretches hip flexors & thoracic spine)\n"
            "   - **Leg Swings (Front/Back & Lateral)**: 12 reps per leg\n"
            "   - **Arm Circles & Cross-Body Swings**: 20 seconds each\n"
            "   - **Inchworms to Push-up**: 5 reps for core and shoulder stability\n\n"
            "3. **Sport-Specific Activation (4 mins)**:\n"
            "   - Lateral shuffles and decelerations\n"
            "   - 3 short progressive sprints (60%, 80%, 95%)\n\n"
            "💡 *Tip: Never perform prolonged static stretches before explosive sports—keep stretches moving!*"
        )
    elif any(k in last_user_message for k in ("football", "soccer", "tactics", "formation", "5v5")):
        content = (
            "### ⚽ 5v5 / 7v7 Football Tactical Guide\n\n"
            "In small-sided pickup games on public grounds or turf, space is compressed:\n\n"
            "- **The 1-2-1 Diamond (Recommended for 5v5)**:\n"
            "  - **1 Defender**: Anchors the back, resists diving into tackles, directs plays.\n"
            "  - **2 Wingers / Midfielders**: Provide width, track back when defending, and exploit overlap space.\n"
            "  - **1 Pivot / Forward**: Holds up the ball, links play with one-touch lay-offs.\n\n"
            "- **Defensive Principles**:\n"
            "  - Maintain compact shape; force the opponent out wide rather than through the middle.\n"
            "  - When losing possession, the nearest player presses while teammates quickly recover behind the ball.\n\n"
            "🎯 *In NexSport lobbies, use our team split feature to balance stamina and attacking power!*"
        )
    elif any(k in last_user_message for k in ("cricket", "pitch", "bowling", "batting")):
        content = (
            "### 🏏 Casual Cricket Essentials & Pitch Measurements\n\n"
            "- **Standard Pitch Dimensions**:\n"
            "  - Length: **22 yards (20.12 m)** between popping creases.\n"
            "  - Pitch Width: 10 feet (3.05 m).\n"
            "  - Bowling Crease to Popping Crease: 4 feet (1.22 m).\n\n"
            "- **Tips for Street / Box / Turf Cricket**:\n"
            "  - **Batting**: Keep weight forward on front foot; play straight in small spaces.\n  - **Bowling**: Focus on line and length (good-length spot ~5-6m from the stumps) rather than sheer pace.\n  - **Fielding**: Place a reliable sweeper on the leg-side boundary and protect the extra-cover region."
        )
    elif any(k in last_user_message for k in ("basketball", "dribble", "shooting", "defense", "pick")):
        content = (
            "### 🏀 Pickup Basketball Fundamentals & Half-Court Rules\n\n"
            "- **Key Spacing Rule**:\n"
            "  - Never crowd the ball carrier! Maintain at least 12–15 feet spacing along the perimeter.\n\n"
            "- **Offensive Motion (Give & Go / Pick & Roll)**:\n"
            "  - Set solid screens with wide base; roller must sprint directly to the rim.\n"
            "  - Cut backdoor whenever your defender overplays the passing lane.\n\n"
            "- **Defensive Stance**:\n"
            "  - Stay low on balls of feet, one arm up to contest shots, hands active in passing lanes.\n"
            "  - Box out immediately upon shot release—rebounding wins pickup games!"
        )
    elif any(k in last_user_message for k in ("elo", "rating", "algorithm", "questionnaire", "split", "teams")):
        content = (
            "### ⚖️ How NexSport Matchmaking & Ratings Work\n\n"
            "NexSport ensures fair, fun games without lopsided matchups:\n\n"
            "1. **Initial Skill Rating (800 – 1500)**:\n"
            "   - Calculated from your questionnaire answers (fitness, weekly frequency, competitive experience).\n"
            "   - Base rating is set to **1200 points**.\n\n"
            "2. **Greedy Zig-Zag Team Split**:\n"
            "   - When a lobby is full, players are sorted in descending order of skill rating.\n"
            "   - Players are distributed in zig-zag order (`A, B, B, A, A, B...`) so both teams have virtually identical average ratings.\n\n"
            "3. **Elo Rating Updates (K = 32)**:\n"
            "   - Post-match updates compare the expected outcome vs actual result and goal/point margin.\n"
            "   - Beating higher-rated opponents yields significant rating increases!"
        )
    else:
        content = (
            f"### 🏅 NexSport Coach Advice\n\n"
            f"Welcome to NexSport! Whether you're heading to a local public ground or organizing a tournament match:\n\n"
            f"- **Hydration & Warm-up**: Drink water 30 minutes before kickoff and dedicate 10 minutes to dynamic mobility.\n"
            f"- **Sportsmanship**: Play hard, respect opponents, and confirm fair team balancing before starting.\n"
            f"- **Skill Growth**: Track your progress through NexSport's post-match Elo updates.\n\n"
            f"You can ask me about:\n"
            f"- Specific sports tactics (Football, Basketball, Cricket, Badminton, Volleyball, Tennis)\n"
            f"- Field/court dimensions, official rules, and referee signals\n"
            f"- Dynamic warmups, cool-downs, and workout splits\n"
            f"- How NexSport matchmaking and team splitting work"
        )

    setup_guide = (
        "\n\n---\n"
        "> 💡 **Connect Live GitHub Open-Source Models**\n"
        "> To chat with real-time **Meta Llama 3.1**, **Mistral**, **Microsoft Phi**, or **DeepSeek** models via GitHub Models:\n"
        "> 1. Generate a free token at [GitHub Settings > Personal Access Tokens](https://github.com/settings/tokens) *(no extra scopes required)*.\n"
        "> 2. Add `GITHUB_TOKEN=ghp_...` to your project's `.env` file, or click **Settings** ⚙️ in the chat bar to paste your personal token directly in your browser."
    )

    return {
        "reply": content + setup_guide,
        "model": target_model,
        "model_name": model_name,
        "provider": "NexSport Coach (Preview Mode)",
        "usage": {"prompt_tokens": len(last_user_message), "completion_tokens": len(content)},
        "is_fallback": True,
    }

