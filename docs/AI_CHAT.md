# NexSport — AI Sports Coach & GitHub Open-Source Models Integration

NexSport features an AI Sports Assistant powered by **GitHub Models**, enabling players to chat with state-of-the-art open-source LLMs directly from the app.

---

## 1. Supported Open-Source Models

Through the GitHub Models Inference API, NexSport provides access to top open-weights models:

| Model ID | Model Name | Provider | Strength |
| :--- | :--- | :--- | :--- |
| `meta/llama-3.1-70b-instruct` | **Meta Llama 3.1 70B** | Meta | *(Default / Recommended)* High-depth tactical advice, match preparation, rules, and workout programming. |
| `meta/llama-3.1-8b-instruct` | **Meta Llama 3.1 8B** | Meta | Fast, lightweight responses for rapid on-the-field Q&A. |
| `mistralai/mistral-large-2407` | **Mistral Large 2** | Mistral AI | Exceptional reasoning, spatial positioning, and team formations. |
| `mistralai/mistral-small` | **Mistral Small** | Mistral AI | Snappy, low-latency conversational coach. |
| `microsoft/phi-3.5-mini-instruct` | **Microsoft Phi-3.5 Mini** | Microsoft | State-of-the-art small language model (SLM) with sharp factual accuracy. |
| `deepseek/deepseek-r1` | **DeepSeek R1** | DeepSeek | Analytical step-by-step reasoning for competitive match tactics. |

---

## 2. Architecture

```
┌─────────────────────────────────┐
│     NexSport Frontend           │
│  - chat.html (Full Chat Page)   │
│  - chat-widget.js (FAB Widget)  │
│  - chat.js (Client Controller)  │
└───────────────┬─────────────────┘
                │ HTTP (JSON)
                ▼
┌─────────────────────────────────┐
│     NexSport Flask API          │
│  - GET  /api/chat/models        │
│  - POST /api/chat               │
│  - chat_service.py              │
└───────────────┬─────────────────┘
                │ Bearer GITHUB_TOKEN
                ▼
┌─────────────────────────────────────────────────┐
│     GitHub Models Inference API                 │
│  - https://models.github.ai/inference           │
│    /chat/completions                            │
│  (Fallback: models.inference.ai.azure.com)      │
└─────────────────────────────────────────────────┘
```

---

## 3. Configuration & Authentication

GitHub Models supports free model prototyping using standard **GitHub Personal Access Tokens (PAT)**.

### Option A: Server-Side Configuration (Recommended)
1. Go to [GitHub Settings → Developer Settings → Personal Access Tokens](https://github.com/settings/tokens) (Tokens classic or Fine-grained).
2. Generate a token. **No extra scopes or permissions are required** for public model inference.
3. Add it to your `.env` file:
   ```bash
   GITHUB_TOKEN=ghp_yourPersonalAccessTokenHere
   ```
4. Restart Flask (`python run.py`). All users will immediately chat with live GitHub models.

### Option B: User-Provided Token (Client Settings Modal)
- Players can click the **⚙️ Settings** button on the `chat.html` header.
- Paste their personal GitHub token. It is stored securely in the browser's `localStorage` and passed to the backend via the `X-GitHub-Token` header.
- This allows each user to use their own personal GitHub Models rate limit quota.

### Option C: Built-in Offline Preview Mode (Zero Setup)
- If neither the server nor the client has configured a token, NexSport automatically activates **Preview Mode**.
- The coach answers queries about:
  - 10-minute dynamic warmups and injury prevention
  - 5v5/7v7 Football formations (1-2-1 diamond)
  - Cricket pitch dimensions & bowling tactics
  - Pickup basketball fundamentals & spacing
  - Explanation of NexSport Elo updates and greedy zig-zag team splitting
- Includes helpful guidance on adding a token to unlock live open-source LLMs.

---

## 4. API Specification

### `GET /api/chat/models`
Returns the catalogue of available open-source models and current token status.

**Response (200 OK):**
```json
{
  "models": [
    {
      "id": "meta/llama-3.1-70b-instruct",
      "name": "Meta Llama 3.1 70B",
      "provider": "Meta",
      "badge": "Recommended",
      "icon": "🦙",
      "description": "Powerful open-weights model with exceptional depth...",
      "recommended": true
    }
  ],
  "default_model": "meta/llama-3.1-70b-instruct",
  "has_server_token": true
}
```

---

### `POST /api/chat`
Sends a conversation history to the selected GitHub model.

**Request Headers (Optional):**
- `X-GitHub-Token`: Overrides the server token with a user-supplied GitHub PAT.

**Request Body:**
```json
{
  "messages": [
    { "role": "user", "content": "How do we defend against a fast counter-attacking team in 5v5 football?" }
  ],
  "model": "meta/llama-3.1-70b-instruct",
  "temperature": 0.7,
  "max_tokens": 1024
}
```

**Response (200 OK):**
```json
{
  "reply": "### ⚽ Counter-Attack Defense Strategies...",
  "model": "meta/llama-3.1-70b-instruct",
  "model_name": "Meta Llama 3.1 70B",
  "provider": "GitHub Models (Meta)",
  "usage": {
    "prompt_tokens": 32,
    "completion_tokens": 210,
    "total_tokens": 242
  },
  "is_fallback": false
}
```

---

## 5. Automated Tests

Run the chat test suite with:
```powershell
.\.venv\Scripts\python.exe -m unittest tests/test_chat.py
```
Or run all 104+ unit tests:
```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```

