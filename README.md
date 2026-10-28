# NexSport ⚽

A sports matchmaking application that connects casual players who want to play
sports in free public spaces. NexSport finds nearby match lobbies, maintains
player skill ratings, and automatically divides players into balanced teams.

## Tech Stack

| Layer      | Technology                                      |
|------------|-------------------------------------------------|
| Frontend   | HTML5, CSS3, JavaScript, Bootstrap 5            |
| Backend    | Python, Flask REST API                          |
| Database   | Supabase PostgreSQL (later stages)              |
| Auth       | Supabase Auth — email/password + Google OAuth (later stages) |
| AI Chat    | GitHub Models (Meta Llama 3.1, Mistral, Phi-3.5, DeepSeek R1) |
| Deployment | Vercel (web + API), Capacitor (Android APK)     |

## Project Structure

```
nexsport/
├── backend/
│   ├── __init__.py          # Marks backend as a Python package
│   ├── __version__.py       # Single source of truth for app version
│   ├── app.py               # Flask app factory + error handlers (entry point)
│   ├── config.py            # Reads all settings from environment variables
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── chat.py          # POST /api/chat & GET /api/chat/models
│   │   └── health.py        # GET /api/health endpoint
│   ├── services/            # Business logic (chat_service, auth, matchmaking)
│   │   ├── chat_service.py  # GitHub Models LLM client + sports coach prompt
│   │   └── ...
│   ├── database/            # Supabase client & data access — later stages
│   └── algorithms/          # Haversine, Elo, team balancing — later stages
├── frontend/
│   ├── index.html           # Responsive homepage (Bootstrap 5)
│   ├── chat.html            # AI Coach & open-source model chat page
│   ├── css/styles.css       # Custom styles on top of Bootstrap
│   └── js/
│       ├── chat-widget.js   # Floating AI Coach launcher widget
│       ├── config.js        # Frontend runtime config (API base URL)
│       ├── pages/chat.js    # Chat controller & model switcher
│       └── main.js          # Homepage logic (API health status widget)
├── run.py                   # Local development launcher
├── requirements.txt         # Python dependencies
├── vercel.json              # Vercel deployment config (API + static frontend)
├── .env.example             # Template for environment variables
└── .gitignore
```

## Local Setup (Windows + VS Code)

### 1. Prerequisites

- **Python 3.11+** — check with `python --version`
- **Visual Studio Code** with the *Python* extension
- **Git** (optional, for version control)

### 2. Create a virtual environment

Open the project folder in VS Code, then in a PowerShell terminal:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, allow scripts for the current user once:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

VS Code: press `Ctrl+Shift+P` → *Python: Select Interpreter* → choose
`.venv`. If Python 3.11 is unavailable, use any supported Python 3.11+ runtime,
such as `python -m venv .venv`.

### 3. Configure environment variables

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set real values for `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and
`SUPABASE_SERVICE_ROLE_KEY`. The server serves only the URL and publishable
anon key from `GET /api/config.js`; never place the service-role key in
frontend source or in a browser-exposed environment variable.

### 5. Run the backend

```powershell
python run.py
```

The full app starts at `http://127.0.0.1:5000`:

- `http://127.0.0.1:5000/` serves the existing NexSport homepage.
- `http://127.0.0.1:5000/api/health` serves the health endpoint.
- Frontend pages and assets are served from `frontend/` by Flask.

Live Server on port 5500 remains optional and is useful for independent frontend
iteration. Its origin is already allowed in the default CORS configuration.

## Testing the Foundation

1. **Homepage** — open `http://127.0.0.1:5000` in your browser.
   You should see the NexSport hero, three feature cards, and an
   *API Status* section.
2. **Health check via browser** — open `http://127.0.0.1:5000/api/health`.
   Expected JSON:

   ```json
   {"app": "NexSport", "message": "NexSport API is running", "status": "ok", "version": "0.1.0"}
   ```

3. **Health check via PowerShell** (with the server running):

   ```powershell
   Invoke-RestMethod http://127.0.0.1:5000/api/health
   ```

4. **Frontend ↔ Backend integration** — the *API Status* box on the homepage
   should change from `Checking backend…` to the configured API result, such as
   `NexSport API is running (v0.1.0)`.

5. **Authorization and configuration tests**:

   ```powershell
   python -m unittest tests.test_api_authorization -v
   python -m unittest discover -s tests -p "test_*.py" -v
   ```

## Checklist of Expected Results

- [x] `python run.py` starts Flask without errors on port 5000
- [x] `GET /api/health` returns HTTP 200 with the JSON shown above
- [x] `GET /api/nonexistent` returns HTTP 404 JSON (`{"error": "Not found"}`)
- [x] Homepage renders responsively (test by resizing the browser / DevTools device mode)
- [x] Homepage API Status box shows the green "running" message
- [x] No secrets in source code — only `.env.example` is committed

## Database (Stage 2)

The Supabase schema lives in `supabase/migrations/` — run migrations
`001` through `007` in numeric order in the Supabase **SQL Editor**. Migration
`007_team_assignment_authorization.sql` is required: it removes ordinary-user
team assignment and installs the atomic `assign_lobby_teams` RPC.
See `supabase/README.md` for the full design, table purposes, security model
and verification queries.

## Authentication (Stage 3)

Email/password + Google OAuth via Supabase Auth. Setup, provider settings,
redirect URLs and a manual test checklist are in **`docs/AUTH_SETUP.md`**.
Quick summary: set the Supabase URL + anon key in backend `.env`; Flask emits
those public values from `/api/config.js` at runtime. Keep the service-role
key only in backend `.env`. Protected pages: `dashboard.html`, `profile.html`.
Protected API endpoints: `/api/auth/me`, `/api/auth/profile`,
`/api/auth/protected-demo` (verify with `Authorization: Bearer <token>`).

## Questionnaire & Initial Rating (Stage 4)

Responsive questionnaire at `frontend/questionnaire.html` computes a
**provisional** starting rating via a transparent weighted formula
(base 1000, ±350 max adjustment, clamped to 700–1400).
Formula, worked example and testing steps: **`docs/QUESTIONNAIRE.md`**.
Unit tests: `python -m unittest tests.test_initial_rating -v`.

## Match Discovery (Stage 5)

Location-based lobby search with GPS + manual fallback:
`frontend/find-matches.html`. Haversine distance in
`backend/services/geo_service.py`; endpoint `GET /api/lobbies/nearby`.
Demo lobbies: `supabase/migrations/004_demo_lobbies.sql`.
Details + two-coordinate test: **`docs/MATCH_DISCOVERY.md`**.
Unit tests: `python -m unittest tests.test_geo_service -v`.

## Lobby Management (Stage 6)

Create/join/leave/start/cancel with atomic PostgreSQL RPCs
(`join_lobby`/`leave_lobby`, migration 005) — simultaneous joins serialize on
a row lock, so overbooking is impossible. Create at `frontend/create-lobby.html`,
detail at `frontend/lobby.html`. Endpoints under `/api/lobbies`.
Concurrency design + manual test script: **`docs/LOBBIES.md`**.
Unit tests: `python -m unittest tests.test_lobby_service -v`.

## Post-Match Ratings (Stage 7)

Elo updates (mean-team, margin-scaled K) applied atomically via RPC;
peer feedback is a separate bounded adjustment (±15, min 2 reviewers).
Formula, worked example, test flow: **`docs/RATINGS.md`**.
Unit tests: `python -m unittest tests.test_elo_service -v`.

## Team Balancing (Stage 8)

Improved Greedy Zig-Zag Split (snake draft + bounded swap improvement) in
`backend/algorithms/team_split.py`, independently tested. Host endpoint
`POST /api/lobbies/<id>/teams` generates and stores assignments when the
lobby is full. Explanation + comparison table: **`docs/TEAM_SPLIT.md`**.
Unit tests: `python -m unittest tests.test_team_split -v`.
