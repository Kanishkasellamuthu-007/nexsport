# Stage 5 — Location-Based Match Discovery

## How discovery works (honest scope)

- Grounds/lobbies come **from our Supabase tables** — the Haversine formula
  does **not** discover grounds automatically. It only computes the
  great-circle distance between your chosen point and each stored lobby, so we
  can rank and filter them.
- Verified ground data can later be **imported** from OpenStreetMap (Overpass
  API) or another open geo source into the `grounds` table; the app is already
  shaped for that (`grounds` has name/city/lat/lng/sports).
- Initial testing uses clearly-labelled demo lobbies from
  `supabase/migrations/004_demo_lobbies.sql`.

## Implementation map

| Piece | File |
|---|---|
| Haversine + coordinate/radius validation (pure functions) | `backend/services/geo_service.py` |
| `GET /api/lobbies/nearby?lat&lon&radius_km&sport_id` (token-verified) | `backend/routes/lobbies.py` |
| GPS + manual fallback + filters + cards + empty state | `frontend/find-matches.html`, `frontend/js/pages/find-matches.js` |
| Unit tests with known coordinate pairs | `tests/test_geo_service.py` |

Formula: `a = sin²(Δφ/2) + cosφ₁·cosφ₂·sin²(Δλ/2); d = 2R·atan2(√a, √(1−a))`,
R = 6371.0088 km. The API validates lat ∈ [−90, 90], lon ∈ [−180, 180],
radius ∈ [0.5, 100] km and returns 400 otherwise. A cheap bounding-box
prefilter runs DB-side; the exact Haversine filter runs in Python.

Closed/full/upcoming-only rules: only `open/full/in_progress` public lobbies
with future times are returned, and `joinable` is true only when
`status == 'open'` **and** places remain — full/closed lobbies render with a
disabled button.

## Running

```powershell
# 1. Apply the demo data (SQL Editor, after 001–003):
#    supabase/migrations/004_demo_lobbies.sql

# 2. Tests (no database needed)
python -m unittest tests.test_geo_service -v

# 3. Start backend + Live Server, log in, open find-matches.html
```

## Testing with two known coordinate pairs

Mumbai (Bandra) `19.0760, 72.8777` and Delhi (India Gate) `28.6129, 77.2295`
are ~**1150 km** apart (Mumbai→Bengaluru is ~845 km). The unit tests assert
these with ±30 km tolerance — run them first:

```
python -m unittest tests.test_geo_service -v
```

Manual end-to-end check with the demo lobbies:

1. Log in → **Find Matches** → *Enter manually* → pick the
   predefined spot or type `19.0760 / 72.8777` (Mumbai) → **Set location**.
2. Radius 25 km, All sports → **Search**.
   Expected: "Evening Football near Marine Drive" (~8 km) and
   "FULL — Badminton Doubles Test" (~7 km) appear; the football lobby shows a
   working **Join** button, the badminton one shows **Full** with a disabled
   button. Cricket (Bengaluru) and volleyball (Chennai) must NOT appear.
3. Switch radius to 5 km → the football lobby (~8 km) disappears.
4. Set Delhi coordinates `28.6129 / 77.2295` → search → empty state
   "No matches found nearby" (nearest demo lobby is >1000 km away).
5. Filter by sport = Football at Mumbai → only the football lobby remains.
6. GPS test: click **Use my GPS location** → allow → status line shows your
   real coordinates. Then **deny** permission → a warning appears and the
   manual panel opens automatically (graceful fallback).
7. Invalid input: type latitude `95` → "Latitude must be -90..90…" warning;
   API-side: `/api/lobbies/nearby?lat=95&lon=0` → HTTP 400.
