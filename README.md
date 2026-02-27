# PacePilot

PacePilot is a full-stack Strava coaching app built with Django/DRF/Celery (backend) and React/Vite/Tailwind (frontend).

## Local quick start
1. Copy `.env.example` -> `.env` and set Strava keys.
2. Backend (`apps/backend`):
   - `pip install -r requirements.txt`
   - `python app.py` (runs migrations, ensures `admin@local` user, starts on `http://localhost:8000`)
3. Frontend (`apps/web`):
   - `npm install`
   - `npm run dev` (starts on `http://localhost:5173`)

## Auth model (dev-friendly JWT)
- `POST /api/auth/dev-login` (debug-only): returns access/refresh JWTs for `admin@local` (`admin`).
- `POST /api/auth/login`: username/email + password -> tokens.
- `POST /api/auth/refresh`: refresh token -> new access token.
- `GET /api/auth/me`: current user + Strava connection status.

Frontend stores JWT tokens and automatically sends `Authorization: Bearer <token>` on protected requests.
On `401`, it attempts token refresh automatically.

## Strava OAuth flow
1. In web app, go to Integrations and click **Connect Strava**.
2. Frontend calls `GET /api/auth/strava/connect` (authenticated) and receives Strava authorize URL.
3. Browser redirects to Strava consent.
4. Strava returns to `STRAVA_REDIRECT_URI` (`/api/auth/strava/callback`).
5. Backend exchanges code for tokens, stores in `StravaConnection` for the authenticated user (state-validated), then redirects to:
   - `${APP_BASE_URL}/integrations?strava=connected`

Disconnect endpoint:
- `POST /api/auth/strava/disconnect`

## Demo data
If no Strava data exists, import a sample workout:
- `POST /api/demo/import`

This creates one activity with streams + derived metrics to populate dashboard charts, map preview, and activity detail UI.

## What is implemented
- Working one-click dev login with visible logged-in state.
- Working authenticated Strava connect/callback/disconnect flow.
- Premium app shell: top bar, sidebar, theme toggle, responsive cards.
- Dashboard analytics: trend cards, training load chart, weekly sport chart, coach tone, weekly focus, ramp warning, streak, readiness placeholder, next workout.
- Activities list: search/filter UI with richer cards.
- Activity detail: map route, HR/elevation charts, splits, AI note panel + regenerate action.
- Global API error toasts and loading/empty states.

## Environment notes
Required Strava env vars:
- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REDIRECT_URI` (must match your Strava app callback)

Frontend base URL:
- `VITE_API_BASE_URL` (default `http://localhost:8000/api`)

## AI Pipeline (token-efficient)
- Model routing:
  - `gpt-5-mini`: weekly plan generation, general chat.
  - `gpt-5-nano`: per-workout coach note, weekly summary, dashboard quick encouragement.
  - Rare escalation to `gpt-5.2` only on low-confidence + severe risk flags (`injury`, `overtraining`, `sudden_load_spike`).
- Context control:
  - User-level `lookback_days` is enforced for workout selection.
  - `athlete_state` is compact and cached by `(user_id, lookback_days, last_workout_id)`.
  - Plan/chat only receive compact profile + goal + athlete_state + retrieved relevant workouts (not raw workout dumps).
- Structured outputs:
  - Non-chat features use JSON schema with validation + one repair retry.
- Cache keys:
  - Weekly summary: `(user_id, week_start, last_workout_id)`.
  - Quick encouragement: `(user_id, week_start, last_workout_id)`.
  - Weekly plan: `(user_id, week_start, input_hash)`.
- Logging:
  - Every AI call stores model and token usage in `AIInteraction`.

### Sunday plan regen locally
1. Ensure backend timezone is `Europe/Budapest` (default in settings).
2. Run Celery beat/worker as usual.
3. Trigger manually from Django shell if needed:
   - `from core.tasks import generate_weekly_plan_sunday; generate_weekly_plan_sunday.delay()`
