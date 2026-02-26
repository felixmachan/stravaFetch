# PacePilot

PacePilot is a full-stack AI coach for Strava (Run/Ride/Swim) built with Django + DRF + Celery + Postgres + Redis and React + Vite.

## Quick start
1. Create Strava API app and set callback URL to `http://localhost:8000/api/auth/strava/callback`.
2. Copy `.env.example` to `.env` and fill keys.
3. Start stack: `docker-compose up --build`.
4. Open web on http://localhost:5173 and login with `admin@local` / `admin`.
5. Click Connect Strava.

## What works
- Polling sync via Celery Beat (`STRAVA_POLL_INTERVAL_MINUTES`).
- Strava OAuth connect/callback + token refresh.
- Activity ingestion (idempotent upsert by `strava_activity_id`).
- AI coach note generation with strict JSON validation + deterministic fallback.
- Dashboard, activities list, activity detail, basic map/chart.
- Integrations endpoints for Email + Telegram and test send.
- Webhook endpoints exist at `/api/strava/webhook` (GET verify, POST receive).

## Webhook (optional)
For local webhook testing expose backend using ngrok/cloudflared and register in Strava developer settings to `/api/strava/webhook` with `STRAVA_VERIFY_TOKEN`.

## Commands
- Migrations: `docker-compose run --rm backend python manage.py migrate`
- Create superuser: `docker-compose run --rm backend python manage.py createsuperuser`
- Tests: `docker-compose run --rm backend python manage.py test`

## Notes
- Tokens are stored server-side only.
- CSRF/session auth enabled, CORS restricted to localhost:5173.
- Demo mode: you can POST sample activity JSON through API directly if Strava is not connected.
