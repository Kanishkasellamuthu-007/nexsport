# NexSport — Stage 3: Authentication Setup & Testing

## 1. Supabase Dashboard settings

### a) Google provider
1. **Google Cloud Console** → create an *OAuth client ID* (Web application).
2. Authorized redirect URI:
   `https://dwvlzllnjuignfewkiag.supabase.co/auth/v1/callback`
3. Copy the **Client ID** and **Client Secret**.
4. In Supabase: **Authentication → Providers → Google** → enable, paste the
   Client ID + Secret → Save. The secret lives ONLY in Supabase — never in code.

### b) Redirect URLs (Authentication → URL Configuration)
Add these to **Redirect URLs**:
- `http://127.0.0.1:5000/oauth-callback.html` (current Flask dev server)
- `http://localhost:5000/oauth-callback.html`
- `http://127.0.0.1:5500/oauth-callback.html` (optional Live Server)
- `http://localhost:5500/oauth-callback.html` (optional Live Server)
- Your production URL, e.g. `https://your-app.vercel.app/oauth-callback.html`

Set **Site URL** to `http://127.0.0.1:5000` for the current Flask setup.

### c) Email confirmation
**Authentication → Providers → Email**: while testing locally you may disable
"Confirm email" so sign-ups get a session instantly. For production, keep it ON.

## 2. Browser configuration

Set `SUPABASE_URL` and `SUPABASE_ANON_KEY` in the backend `.env` (Dashboard →
Settings → API). Flask returns these publishable values from
`GET /api/config.js`, and the frontend creates `supabaseClient` from that script.
Do not put placeholders or configuration values into `frontend/js/supabase-client.js`.
The **service-role key** and **JWT secret** stay only in the backend `.env` and
must never appear in frontend JavaScript.

## 3. Backend env vars (`.env`)

```
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=<anon key>
SUPABASE_SERVICE_ROLE_KEY=<service_role key>   # server only!
SUPABASE_JWT_SECRET=                            # optional (legacy HS256 projects)
```

Then install requirements and run:

```powershell
python -m pip install -r requirements.txt
python run.py
```

Serve `frontend/index.html` with Live Server on port 5500. The homepage obtains
browser configuration from the Flask API, so the API must be running first.

## 4. How the auth flow works

- **Registration / email login**: browser → Supabase Auth directly
  (`supabase.auth.signUp` / `signInWithPassword`). Flask never sees passwords.
- **Google OAuth**: browser → Supabase → Google → back to `oauth-callback.html`,
  which stores the session and asks Flask to create the profile row.
- **Session handling**: supabase-js persists the session in localStorage and
  auto-refreshes tokens. All API calls send `Authorization: Bearer <token>`.
- **Backend verification** (`backend/services/auth_service.py`): Flask verifies
  the JWT signature (RS256 via Supabase's JWKS, HS256 fallback via JWT secret)
  and expiry. The user id is taken **only** from the verified token's `sub`.
- **Protected pages**: `dashboard.html` and `profile.html` call `requireAuth()`
  and redirect anonymous visitors to `index.html`.
- **Expired sessions**: any 401 from the API signs the user out locally and
  redirects to `index.html?expired=1`, which shows a notice.

## 5. Manual test checklist

| # | Test | Steps | Expected |
|---|------|-------|----------|
| 1 | Register | `/register.html` → fill name/email/password → Create Account | Green success message (email confirm ON) or redirect to dashboard (confirm OFF); row appears in `profiles` |
| 2 | Register validation | Submit empty form / mismatched passwords | Inline red field errors, no request sent |
| 3 | Login (correct) | `/index.html` → valid credentials | Redirect to `dashboard.html`, email badge shows your email |
| 4 | Login (wrong password) | invalid password | "Incorrect email or password." alert, no redirect |
| 5 | Google login | Click "Continue with Google" → choose account | Return via `oauth-callback.html` → dashboard; profile row created |
| 6 | Logout | Dashboard → Logout | Back on homepage; nav shows Login again; refresh of dashboard redirects to login |
| 7 | Protected page | Open `dashboard.html` in a logged-out (incognito) tab | Redirected to `index.html` |
| 8 | Unauthorized API | PowerShell: `Invoke-RestMethod http://127.0.0.1:5000/api/auth/me` | HTTP 401 `{"error":"Missing Authorization header"}` |
| 9 | Authorized API | Dashboard → "Verify my session with the API" | Green JSON with your email + profile |
| 10 | Expired session | Delete the access token from localStorage (`supabase.auth.getToken()` trick or wait for expiry) then call API | Redirect to login with the "session expired" notice |
| 11 | Duplicate email | Register the same email twice | "An account with this email already exists." |
