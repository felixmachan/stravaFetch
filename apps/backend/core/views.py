import datetime as dt
import json
import os
import secrets
import threading
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth import authenticate, logout
from django.contrib.auth.models import User
from django.core import signing
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.utils import timezone
from openai import OpenAI
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import (
    AIInteraction,
    Activity,
    ActivityStream,
    AthleteProfile,
    CoachNote,
    DerivedMetrics,
    NotificationSettings,
    StravaConnection,
    TelegramConnection,
    TrainingPlan,
)
from .serializers import ActivitySerializer, IntegrationSerializer, PlanSerializer, ProfileSerializer
from .services.ai_coach import (
    build_context_snapshot,
    generate_coach_tone,
    generate_onboarding_summary,
    generate_weekly_plan,
    refresh_week_plan_status,
    run_ai_and_log,
)
from .services.ai import answer_general_chat, generate_quick_encouragement, generate_weekly_summary
from .services.strava import refresh_if_needed, sync_athlete_profile_from_connection, sync_athlete_profile_from_strava
from .tasks import (
    generate_activity_reaction_task,
    generate_coach_tone_task,
    generate_weekly_plan_task,
    send_test_email_task,
    send_test_telegram_task,
    sync_now_for_user,
    sync_streams_for_activity,
)


def _run_background(task):
    t = threading.Thread(target=task, daemon=True)
    t.start()


def _token_pair(user: User) -> dict:
    access_signer = signing.TimestampSigner(salt="pacepilot-access")
    refresh_signer = signing.TimestampSigner(salt="pacepilot-refresh")
    return {"access": access_signer.sign(str(user.id)), "refresh": refresh_signer.sign(str(user.id))}


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }


def _strava_redirect_uri() -> str:
    explicit = os.getenv("STRAVA_REDIRECT_URI")
    if explicit:
        return explicit
    return f"{settings.API_BASE_URL.rstrip('/')}/api/auth/strava/callback"


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _strava_signup_prefill_from_access_token(access_token: str) -> dict:
    athlete = {}
    zones = []
    try:
        athlete_resp = requests.get(
            "https://www.strava.com/api/v3/athlete",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        if athlete_resp.ok:
            athlete = athlete_resp.json() or {}
    except Exception:
        athlete = {}

    try:
        zones_resp = requests.get(
            "https://www.strava.com/api/v3/athlete/zones",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        if zones_resp.ok:
            hr = (zones_resp.json() or {}).get("heart_rate", {}) or {}
            for item in hr.get("zones", [])[:5]:
                zones.append(
                    {
                        "min": int(item.get("min", 0) or 0),
                        "max": int(item.get("max", -1) if item.get("max") is not None else -1),
                    }
                )
    except Exception:
        zones = []

    first = (athlete.get("firstname") or "").strip()
    last = (athlete.get("lastname") or "").strip()
    display_name = " ".join([part for part in [first, last] if part]).strip()
    username = (athlete.get("username") or "").strip()
    suggested_username = (username or f"{first}{last}".lower() or f"athlete{athlete.get('id', '')}").replace(" ", "").lower()
    preferred = "Run"
    for bikes_key, swim_key in (("bikes", "swim"),):
        if athlete.get(bikes_key):
            preferred = "Ride"
        if athlete.get("clubs"):
            break
    return {
        "display_name": display_name,
        "username_suggestion": suggested_username[:150],
        "primary_sport": preferred,
        "weight_kg": athlete.get("weight"),
        "city": athlete.get("city"),
        "state": athlete.get("state"),
        "country": athlete.get("country"),
        "sex": athlete.get("sex"),
        "profile_medium": athlete.get("profile_medium"),
        "profile": athlete.get("profile"),
        "strava_athlete_id": athlete.get("id"),
        "hr_zones": zones,
    }


def _goal_int(payload: dict, key: str):
    value = payload.get(key)
    if value in ("", None):
        return 0
    return int(value)


def _profile_from_payload(user: User, payload: dict):
    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    fields = [
        "display_name",
        "primary_sport",
        "age",
        "height_cm",
        "weight_kg",
        "current_race_pace",
        "goal_race_pace",
        "goal_event_name",
        "goal_event_date",
        "goals",
        "weekly_target_hours",
    ]
    updates = {}
    for key in fields:
        if key in payload:
            updates[key] = payload.get(key)
    if updates:
        for key, value in updates.items():
            setattr(profile, key, value)
        profile.save(update_fields=list(updates.keys()))

    schedule = profile.schedule or {}
    goal_type = payload.get("goal_type")
    if goal_type:
        goal_distance = payload.get("goal_distance_km")
        goal_target_time = payload.get("goal_target_time_min")
        schedule["goal"] = {
            "type": goal_type,
            "target_distance_km": goal_distance,
            "target_time_min": goal_target_time,
            "race_distance_km": goal_distance if goal_type == "race" else None,
            "has_time_goal": bool(goal_target_time) if goal_type == "race" else None,
            "event_name": payload.get("goal_event_name") or profile.goal_event_name,
            "event_date": payload.get("goal_event_date") or (str(profile.goal_event_date) if profile.goal_event_date else None),
            "annual_km_goal": payload.get("annual_km_goal"),
            "weekly_activity_goal_total": _goal_int(payload, "weekly_activity_goal_total"),
            "weekly_activity_goal_run": _goal_int(payload, "weekly_activity_goal_run"),
            "weekly_activity_goal_swim": _goal_int(payload, "weekly_activity_goal_swim"),
            "weekly_activity_goal_ride": _goal_int(payload, "weekly_activity_goal_ride"),
            "notes": payload.get("goals") or profile.goals or "",
        }
    if payload.get("birth_date"):
        schedule["birth_date"] = payload.get("birth_date")
    if "training_days" in payload:
        days = payload.get("training_days") or []
        if isinstance(days, list):
            allowed = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
            schedule["training_days"] = [str(d).strip().lower()[:3] for d in days if str(d).strip().lower()[:3] in allowed]
    if payload.get("ai_memory_days") is not None:
        ai = schedule.get("ai_settings", {})
        ai["memory_days"] = int(payload.get("ai_memory_days") or 30)
        ai["lookback_days"] = int(payload.get("ai_lookback_days") or ai.get("lookback_days") or ai["memory_days"])
        ai["feature_flags"] = ai.get("feature_flags") or {
            "weekly_plan": True,
            "coach_says": True,
            "weekly_summary": True,
            "general_chat": True,
            "quick_encouragement": True,
        }
        schedule["ai_settings"] = ai
    profile.schedule = schedule
    profile.save(update_fields=["schedule"])
    return profile


def _goal_payload(profile: AthleteProfile):
    schedule = profile.schedule or {}
    goal = schedule.get("goal") or {}
    return {
        "type": goal.get("type") or "race",
        "target_distance_km": goal.get("target_distance_km"),
        "target_time_min": goal.get("target_time_min"),
        "race_distance_km": goal.get("race_distance_km"),
        "has_time_goal": bool(goal.get("has_time_goal")),
        "event_name": goal.get("event_name") or profile.goal_event_name,
        "event_date": goal.get("event_date") or (str(profile.goal_event_date) if profile.goal_event_date else None),
        "annual_km_goal": goal.get("annual_km_goal"),
        "weekly_activity_goal_total": int(goal.get("weekly_activity_goal_total") or 0),
        "weekly_activity_goal_run": int(goal.get("weekly_activity_goal_run") or 0),
        "weekly_activity_goal_swim": int(goal.get("weekly_activity_goal_swim") or 0),
        "weekly_activity_goal_ride": int(goal.get("weekly_activity_goal_ride") or 0),
        "notes": goal.get("notes") or profile.goals or "",
    }


def _training_days_for_user(user: User):
    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    schedule = profile.schedule or {}
    raw = schedule.get("training_days") or []
    allowed = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    out = []
    for day in raw:
        key = str(day).strip().lower()[:3]
        if key in allowed and key not in out:
            out.append(key)
    return out


def _weekday_key(date_obj: dt.date) -> str:
    return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][date_obj.weekday()]


def _hr_distribution_percent(heartrate: list, hr_zones: list):
    if not heartrate:
        return {}
    buckets = {"z1": 0, "z2": 0, "z3": 0, "z4": 0, "z5": 0}
    for hr in heartrate:
        assigned = False
        for idx, zone in enumerate((hr_zones or [])[:5]):
            zmin = zone.get("min", -10_000)
            zmax = zone.get("max")
            if zmax in (None, -1):
                zmax = 10_000
            if hr >= zmin and hr <= zmax:
                buckets[f"z{idx + 1}"] += 1
                assigned = True
                break
        if not assigned:
            buckets["z5"] += 1
    total = max(1, len(heartrate))
    return {k: round((v / total) * 100, 1) for k, v in buckets.items()}


def _recompute_hr_metrics_for_user(user: User):
    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    zones = profile.hr_zones if isinstance(profile.hr_zones, list) else []
    if not zones:
        return 0
    count = 0
    metrics_qs = DerivedMetrics.objects.filter(activity__user=user).select_related("activity")
    for metric in metrics_qs:
        stream = ActivityStream.objects.filter(activity=metric.activity).values("raw_streams").first()
        heartrate = ((stream or {}).get("raw_streams") or {}).get("heartrate", [])
        if heartrate:
            metric.hr_zone_distribution = _hr_distribution_percent(heartrate, zones)
            metric.save(update_fields=["hr_zone_distribution"])
            count += 1
    return count


def _recent_activity_summary(user: User, days: int = 30):
    start = timezone.now() - dt.timedelta(days=days)
    items = (
        Activity.objects.filter(user=user, start_date__gte=start, is_deleted=False)
        .order_by("-start_date")[:20]
    )
    if not items:
        return "No recent activities."
    lines = []
    for a in items:
        lines.append(
            f"{a.type} {round((a.distance_m or 0)/1000,2)}km {int((a.moving_time_s or 0)/60)}min hr={int(a.avg_hr) if a.avg_hr else 'n/a'}"
        )
    return "; ".join(lines)


def _ask_ai_short(system_prompt: str, user_prompt: str, max_chars: int = 160):
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return "Good direction. Keep load progression steady and focus on quality execution.", "no_api_key"
    try:
        client = OpenAI(api_key=key)
        resp = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = (resp.output_text or "").strip()
        if len(text) > max_chars:
            text = text[: max_chars - 1].rstrip() + "..."
        return (text or "Solid baseline. Keep consistency and progress gradually."), "openai"
    except Exception:
        return "AI temporarily unavailable. Keep easy days easy and maintain consistency this week.", "provider_error"


def _telegram_bot_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _telegram_api(method: str, params=None, timeout: int = 20):
    token = _telegram_bot_token()
    if not token:
        return None, "missing_bot_token"
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/{method}", params=params or {}, timeout=timeout)
        if not resp.ok:
            return None, f"http_{resp.status_code}"
        data = resp.json()
        if not data.get("ok"):
            return None, data.get("description", "telegram_api_error")
        return data.get("result"), None
    except Exception:
        return None, "network_error"


@api_view(["GET"])
@permission_classes([AllowAny])
def health(_):
    return Response({"status": "ok"})


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get("username") or request.data.get("email")
    password = request.data.get("password")
    if username and "@" in username:
        email_user = User.objects.filter(email__iexact=username).first()
        if email_user:
            username = email_user.username
    user = authenticate(username=username, password=password)
    if not user:
        return Response({"detail": "Invalid username/email or password"}, status=400)
    return Response({"tokens": _token_pair(user), "user": _user_payload(user)})


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    username = (request.data.get("username") or "").strip()
    email = (request.data.get("email") or "").strip().lower()
    password = request.data.get("password") or ""
    if not username:
        return Response({"detail": "Username is required"}, status=400)
    if not email:
        return Response({"detail": "Email is required"}, status=400)
    if len(password) < 6:
        return Response({"detail": "Password must be at least 6 characters"}, status=400)
    if User.objects.filter(username__iexact=username).exists():
        return Response({"detail": "Username already taken"}, status=400)
    if User.objects.filter(email__iexact=email).exists():
        return Response({"detail": "Email already taken"}, status=400)
    goal_type = str(request.data.get("goal_type") or "").strip().lower()
    if goal_type == "race":
        if not request.data.get("goal_event_name") or not request.data.get("goal_event_date"):
            return Response({"detail": "Race goal requires event name and event date."}, status=400)
        if not request.data.get("goal_distance_km"):
            return Response({"detail": "Race goal requires race distance (km)."}, status=400)
    user = User.objects.create_user(username=username, email=email, password=password)
    profile = _profile_from_payload(user, request.data)
    schedule = profile.schedule or {}
    schedule["onboarding"] = {
        "sync_in_progress": False,
        "full_sync_complete": False,
        "last_full_sync_at": None,
    }
    profile.schedule = schedule
    profile.save(update_fields=["schedule"])
    signup_token = (request.data.get("strava_signup_token") or "").strip()
    if not signup_token:
        user.delete()
        return Response({"detail": "Strava signup is required. Connect Strava first."}, status=400)
    if signup_token:
        try:
            signup_payload = signing.loads(signup_token, salt="strava-signup-token", max_age=30 * 60)
            expires_at_epoch = int(signup_payload.get("expires_at") or 0)
            expires_dt = dt.datetime.fromtimestamp(expires_at_epoch, tz=dt.timezone.utc) if expires_at_epoch else (timezone.now() + dt.timedelta(hours=5))
            athlete_id = int(signup_payload.get("athlete_id"))
            StravaConnection.objects.filter(athlete_id=athlete_id).exclude(user=user).delete()
            StravaConnection.objects.update_or_create(
                user=user,
                defaults={
                    "athlete_id": athlete_id,
                    "access_token": signup_payload.get("access_token"),
                    "refresh_token": signup_payload.get("refresh_token"),
                    "expires_at": expires_dt,
                    "scopes": signup_payload.get("scopes") or [],
                },
            )
            try:
                sync_athlete_profile_from_strava(user, signup_payload.get("access_token"), force=True)
            except Exception:
                pass
            inline_sync = os.getenv("STRAVA_SYNC_INLINE_ON_CONNECT", "0") == "1"
            if inline_sync:
                try:
                    sync_now_for_user(user.id)
                except Exception:
                    pass
            else:
                sync_now_for_user.delay(user.id)
        except Exception:
            pass
    _run_background(lambda: generate_onboarding_summary(user, bootstrap_last_n=10))
    _run_background(lambda: generate_weekly_plan(user, force=True, bootstrap_last_n=10))
    _run_background(lambda: generate_weekly_summary(user))
    _run_background(lambda: generate_quick_encouragement(user))
    return Response({"tokens": _token_pair(user), "user": _user_payload(user)}, status=201)


@api_view(["GET"])
def onboarding_status_view(request):
    user = request.user
    strava = StravaConnection.objects.filter(user=user).first()
    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    onboarding = (profile.schedule or {}).get("onboarding") or {}
    has_strava = bool(strava)
    full_sync_complete = bool(onboarding.get("full_sync_complete"))
    sync_in_progress = bool(onboarding.get("sync_in_progress"))

    next_week_start = (timezone.localdate() - dt.timedelta(days=timezone.localdate().weekday())) + dt.timedelta(days=7)
    next_week_end = next_week_start + dt.timedelta(days=6)
    next_plan = TrainingPlan.objects.filter(user=user, status="active", start_date=next_week_start, end_date=next_week_end).first()
    has_next_week_plan = bool(next_plan)

    has_onboarding = AIInteraction.objects.filter(user=user, mode="onboarding", status="success").exists()

    recent_activity_ids = list(
        Activity.objects.filter(user=user, is_deleted=False).order_by("-start_date").values_list("id", flat=True)[:10]
    )
    recent_count = len(recent_activity_ids)
    ai_reaction_count = (
        CoachNote.objects.filter(activity_id__in=recent_activity_ids).values("activity_id").distinct().count()
        if recent_activity_ids
        else 0
    )
    recent_ai_complete = recent_count == ai_reaction_count
    reaction_progress = int(round((ai_reaction_count / max(1, recent_count)) * 100)) if recent_count else 100

    current_week = timezone.localdate().weekday()
    day_to_idx = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    training_days = [str(d).strip().lower() for d in ((profile.schedule or {}).get("training_days") or [])]
    remaining_plan_sessions = len([d for d in training_days if day_to_idx.get(d, -1) >= current_week])

    current_week_key = (timezone.localdate() - dt.timedelta(days=timezone.localdate().weekday())).isoformat()
    has_weekly_summary = AIInteraction.objects.filter(user=user, mode="weekly_summary", status="success").exists()
    has_quick_encouragement = AIInteraction.objects.filter(user=user, mode="quick_encouragement", status="success").exists()

    ai_total = recent_count + 2 + remaining_plan_sessions
    ai_completed = ai_reaction_count + (1 if has_weekly_summary else 0) + (1 if has_quick_encouragement else 0)
    ai_progress = int(round((ai_completed / max(1, ai_total)) * 100)) if ai_total else 100

    progress = 8
    message = "Creating account"
    details = ["Setting up your athlete profile"]

    if has_strava:
        progress = 20
        message = "Connected Strava"
        details = ["Secure account linked with Strava"]
    if has_strava and not full_sync_complete:
        progress = 45
        message = "Syncing all Strava activities"
        details = ["Loading your full activity history"]
    if full_sync_complete:
        progress = 62
        message = "All Strava data loaded"
    if plan_generated_by_ai:
        progress = 78
        message = "Weekly AI plan generated"
    if ai_reaction_count:
        progress = max(progress, min(94, 78 + int(round(reaction_progress * 0.16))))
        message = f"AI notes generated for {ai_reaction_count}/{recent_count} recent workouts"
    if recent_ai_complete:
        progress = max(progress, 94)
        message = "AI notes created for latest 10 workouts"
    if has_onboarding:
        progress = max(progress, 99)
        message = "Finalizing dashboard context"

    ready = bool(has_strava and full_sync_complete and plan_generated_by_ai and recent_ai_complete and has_onboarding)
    if ready:
        progress = 100
        message = "Onboarding complete"
        details = ["Redirecting to your prepared dashboard"]

    return Response(
        {
            "ready": ready,
            "progress": progress,
            "message": message,
            "details": details,
            "has_strava": has_strava,
            "full_sync_complete": full_sync_complete,
            "sync_in_progress": sync_in_progress,
            "next_week_plan_ready": has_next_week_plan,
            "recent_ai_complete": recent_ai_complete,
            "recent_activity_count": recent_count,
            "recent_ai_note_count": ai_reaction_count,
            "reaction_progress": reaction_progress,
            "has_onboarding": has_onboarding,
            "has_weekly_summary": has_weekly_summary,
            "has_quick_encouragement": has_quick_encouragement,
            "remaining_plan_sessions": remaining_plan_sessions,
            "ai_total": ai_total,
            "ai_completed": ai_completed,
            "ai_progress": ai_progress,
            "weekly_summary_cache_key": current_week_key,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def dev_login_view(_request):
    if not settings.DEBUG:
        return Response({"detail": "Not found"}, status=404)
    user, _ = User.objects.get_or_create(
        username="admin@local",
        defaults={"email": "admin@local", "is_staff": True, "is_superuser": True},
    )
    user.set_password("admin")
    user.is_staff = True
    user.is_superuser = True
    user.email = "admin@local"
    user.save(update_fields=["password", "is_staff", "is_superuser", "email"])
    return Response({"tokens": _token_pair(user), "user": _user_payload(user)})


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_view(request):
    token = request.data.get("refresh")
    if not token:
        return Response({"detail": "Refresh token required"}, status=400)
    signer = signing.TimestampSigner(salt="pacepilot-refresh")
    max_age = int(os.getenv("REFRESH_TOKEN_TTL_SECONDS", str(14 * 24 * 3600)))
    try:
        raw = signer.unsign(token, max_age=max_age)
        user = User.objects.get(id=int(raw), is_active=True)
    except Exception:
        return Response({"detail": "Invalid or expired refresh token"}, status=401)
    access = signing.TimestampSigner(salt="pacepilot-access").sign(str(user.id))
    return Response({"access": access})


@api_view(["POST"])
def logout_view(_request):
    logout(_request)
    return Response({"ok": True})


@api_view(["DELETE", "POST"])
def delete_account_view(request):
    user = request.user
    username = user.username
    user.delete()
    return Response({"ok": True, "deleted_username": username})


@api_view(["GET"])
def me_view(request):
    strava = StravaConnection.objects.filter(user=request.user).first()
    return Response(
        {
            "user": _user_payload(request.user),
            "strava_connected": bool(strava),
            "strava_athlete_id": strava.athlete_id if strava else None,
        }
    )


@api_view(["GET"])
def strava_connect(request):
    state = signing.dumps({"uid": request.user.id, "nonce": secrets.token_urlsafe(8)}, salt="strava-oauth-state")
    params = urlencode(
        {
            "client_id": os.getenv("STRAVA_CLIENT_ID", ""),
            "response_type": "code",
            "redirect_uri": _strava_redirect_uri(),
            "approval_prompt": "force",
            "scope": "read,read_all,activity:read_all,profile:read_all",
            "state": state,
        }
    )
    return Response({"url": f"https://www.strava.com/oauth/authorize?{params}"})


@api_view(["GET"])
@permission_classes([AllowAny])
def strava_signup_connect(_request):
    state = signing.dumps({"flow": "signup", "nonce": secrets.token_urlsafe(8)}, salt="strava-oauth-state")
    params = urlencode(
        {
            "client_id": os.getenv("STRAVA_CLIENT_ID", ""),
            "response_type": "code",
            "redirect_uri": _strava_redirect_uri(),
            "approval_prompt": "force",
            "scope": "read,read_all,activity:read_all,profile:read_all",
            "state": state,
        }
    )
    return Response({"url": f"https://www.strava.com/oauth/authorize?{params}"})


@api_view(["GET"])
@permission_classes([AllowAny])
def strava_signup_prefill(request):
    token = (request.GET.get("token") or "").strip()
    if not token:
        return Response({"detail": "Missing token"}, status=400)
    try:
        payload = signing.loads(token, salt="strava-signup-token", max_age=30 * 60)
    except Exception:
        return Response({"detail": "Invalid or expired token"}, status=400)
    return Response(
        {
            "prefill": payload.get("prefill") or {},
            "strava_signup_token": token,
            "scopes": payload.get("scopes") or [],
        }
    )


@api_view(["POST"])
def strava_disconnect(request):
    deleted, _ = StravaConnection.objects.filter(user=request.user).delete()
    return Response({"ok": bool(deleted)})


@api_view(["POST"])
def strava_sync_profile(request):
    conn = StravaConnection.objects.filter(user=request.user).first()
    if not conn:
        return Response({"detail": "Connect Strava first"}, status=400)
    scopes = {str(s).strip() for s in (conn.scopes or []) if str(s).strip()}
    if "profile:read_all" not in scopes and "read_all" not in scopes:
        return Response(
            {
                "ok": False,
                "hr_zones_count": 0,
                "hr_zones": [],
                "hr_zones_status": "missing_scope_profile_read_all",
                "scopes": sorted(scopes),
                "detail": "Reconnect Strava and grant profile:read_all/read_all scope.",
            },
            status=400,
        )
    profile = sync_athlete_profile_from_connection(request.user, conn, force=True)
    recalculated = _recompute_hr_metrics_for_user(request.user)
    status = (profile.schedule or {}).get("hr_zones_status", "unknown")
    payload = {
        "ok": status == "ok",
        "hr_zones_count": len(profile.hr_zones or []),
        "hr_zones": profile.hr_zones or [],
        "hr_zones_status": status,
        "recalculated_hr_metrics": recalculated,
        "scopes": sorted(scopes),
    }
    if status != "ok":
        return Response(payload, status=400)
    return Response(payload)


@api_view(["GET"])
@permission_classes([AllowAny])
def strava_callback(request):
    front = f"{settings.APP_BASE_URL.rstrip('/')}/settings"
    state_payload = None
    if request.GET.get("error"):
        state = request.GET.get("state")
        try:
            state_payload = signing.loads(state, salt="strava-oauth-state", max_age=600) if state else None
        except Exception:
            state_payload = None
        if (state_payload or {}).get("flow") == "signup":
            return HttpResponseRedirect(f"{settings.APP_BASE_URL.rstrip('/')}/login?mode=register&strava=error&reason=access_denied")
        return HttpResponseRedirect(f"{front}?strava=error&reason=access_denied")
    code = request.GET.get("code")
    state = request.GET.get("state")
    if not code or not state:
        return HttpResponseRedirect(f"{front}?strava=error&reason=missing_params")
    try:
        state_payload = signing.loads(state, salt="strava-oauth-state", max_age=600)
    except Exception:
        return HttpResponseRedirect(f"{front}?strava=error&reason=invalid_state")
    flow = (state_payload or {}).get("flow")
    user = None
    if flow != "signup":
        try:
            user = User.objects.get(id=state_payload["uid"])
        except Exception:
            return HttpResponseRedirect(f"{front}?strava=error&reason=invalid_state")
    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": os.getenv("STRAVA_CLIENT_ID"),
            "client_secret": os.getenv("STRAVA_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if not resp.ok:
        error_front = f"{settings.APP_BASE_URL.rstrip('/')}/login?mode=register&strava=error&reason=token_exchange"
        return HttpResponseRedirect(error_front if flow == "signup" else f"{front}?strava=error&reason=token_exchange")
    payload = resp.json()
    if flow == "signup":
        prefill = _strava_signup_prefill_from_access_token(payload.get("access_token", ""))
        signup_token = signing.dumps(
            {
                "athlete_id": payload["athlete"]["id"],
                "access_token": payload.get("access_token"),
                "refresh_token": payload.get("refresh_token"),
                "expires_at": payload.get("expires_at"),
                "scopes": [s.strip() for s in str(payload.get("scope", "")).split(",") if s.strip()],
                "prefill": prefill,
            },
            salt="strava-signup-token",
            compress=True,
        )
        login_front = f"{settings.APP_BASE_URL.rstrip('/')}/login?{urlencode({'mode': 'register', 'strava': 'prefill', 'token': signup_token})}"
        return HttpResponseRedirect(login_front)
    expires = dt.datetime.fromtimestamp(payload["expires_at"], tz=dt.timezone.utc)
    athlete_id = payload["athlete"]["id"]
    StravaConnection.objects.filter(athlete_id=athlete_id).exclude(user=user).delete()
    StravaConnection.objects.update_or_create(
        user=user,
        defaults={
            "athlete_id": athlete_id,
            "access_token": payload["access_token"],
            "refresh_token": payload["refresh_token"],
            "expires_at": expires,
            "scopes": [s.strip() for s in payload.get("scope", "").split(",") if s.strip()],
        },
    )
    try:
        sync_athlete_profile_from_strava(user, payload["access_token"], force=True)
    except Exception:
        pass
    inline_sync = settings.DEBUG or os.getenv("STRAVA_SYNC_INLINE_ON_CONNECT", "0") == "1"
    if inline_sync:
        try:
            sync_now_for_user(user.id)
        except Exception:
            pass
    else:
        sync_now_for_user.delay(user.id)
    return HttpResponseRedirect(f"{front}?strava=connected")


@api_view(["POST"])
def sync_now(request):
    if not StravaConnection.objects.filter(user=request.user).exists():
        return Response({"detail": "Connect Strava first"}, status=400)
    inline_sync = settings.DEBUG or os.getenv("STRAVA_SYNC_INLINE", "0") == "1"
    if inline_sync:
        result = sync_now_for_user(request.user.id)
        return Response({"queued": False, "synced": True, "result": result})
    sync_now_for_user.delay(request.user.id)
    return Response({"queued": True, "synced": False})


@api_view(["GET"])
def activities(request):
    qs = Activity.objects.filter(user=request.user, is_deleted=False)
    if t := request.GET.get("type"):
        qs = qs.filter(type__iexact=t)
    if q := request.GET.get("q"):
        qs = qs.filter(Q(name__icontains=q))
    if frm := request.GET.get("from"):
        qs = qs.filter(start_date__date__gte=frm)
    if to := request.GET.get("to"):
        qs = qs.filter(start_date__date__lte=to)
    return Response(ActivitySerializer(qs.order_by("-start_date")[:200], many=True).data)


@api_view(["GET"])
def activity_detail(request, pk):
    activity = Activity.objects.get(pk=pk, user=request.user)
    if not ActivityStream.objects.filter(activity=activity).exists():
        conn = StravaConnection.objects.filter(user=request.user).first()
        if conn:
            try:
                token = refresh_if_needed(conn)
                sync_streams_for_activity(request.user, activity, token)
            except Exception:
                pass
    data = ActivitySerializer(activity).data
    stream = ActivityStream.objects.filter(activity=activity).values("raw_streams").first()
    metrics = DerivedMetrics.objects.filter(activity=activity).values().first()
    profile, _ = AthleteProfile.objects.get_or_create(user=request.user)
    ranges = {}
    if isinstance(profile.hr_zones, list):
        for idx, zone in enumerate(profile.hr_zones[:5]):
            zmin = zone.get("min")
            zmax = zone.get("max")
            if zmin is None:
                continue
            ranges[f"Z{idx + 1}"] = f"{zmin}+ bpm" if zmax in (None, -1) else f"{zmin}-{zmax} bpm"
    if not ranges:
        ranges = {"Z1": "<120 bpm", "Z2": "120-139 bpm", "Z3": "140-159 bpm", "Z4": "160-174 bpm", "Z5": "175+ bpm"}
    data["streams"] = stream["raw_streams"] if stream else {}
    data["derived_metrics"] = metrics or {}
    data["hr_zone_ranges"] = ranges
    data["coach_note"] = CoachNote.objects.filter(activity=activity).order_by("-created_at").values().first()
    data["activity_reaction"] = (
        CoachNote.objects.filter(activity=activity, prompt_version="v2_activity_reaction")
        .order_by("-created_at")
        .values()
        .first()
    )
    return Response(data)


@api_view(["POST"])
def regenerate(request, pk):
    Activity.objects.get(pk=pk, user=request.user)
    return Response({"detail": "Regenerate note is disabled in AI Coaching v2."}, status=410)


@api_view(["GET", "PATCH"])
def profile(request):
    p, _ = AthleteProfile.objects.get_or_create(user=request.user)
    if request.method == "PATCH":
        hr_zones_updated = "hr_zones" in (request.data or {})
        s = ProfileSerializer(p, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        if hr_zones_updated:
            recalculated = _recompute_hr_metrics_for_user(request.user)
            return Response({**ProfileSerializer(p).data, "recalculated_hr_metrics": recalculated})
    return Response(ProfileSerializer(p).data)


@api_view(["GET", "PATCH"])
def goal_settings(request):
    p, _ = AthleteProfile.objects.get_or_create(user=request.user)
    if request.method == "PATCH":
        goal = _goal_payload(p)
        payload = request.data or {}
        race_related_keys = {
            "type",
            "event_name",
            "event_date",
            "race_distance_km",
            "has_time_goal",
            "target_time_min",
            "target_distance_km",
        }
        validate_race_fields = any(key in payload for key in race_related_keys)
        if "type" in payload:
            goal["type"] = payload.get("type") or goal.get("type") or "race"
        if "target_distance_km" in payload:
            goal["target_distance_km"] = payload.get("target_distance_km")
        if "target_time_min" in payload:
            goal["target_time_min"] = payload.get("target_time_min")
        if "race_distance_km" in payload:
            goal["race_distance_km"] = payload.get("race_distance_km")
        if "has_time_goal" in payload:
            goal["has_time_goal"] = bool(payload.get("has_time_goal"))
        if "event_name" in payload:
            goal["event_name"] = payload.get("event_name")
        if "event_date" in payload:
            goal["event_date"] = payload.get("event_date")
        if "annual_km_goal" in payload:
            goal["annual_km_goal"] = payload.get("annual_km_goal")
        if "weekly_activity_goal_total" in payload:
            goal["weekly_activity_goal_total"] = _goal_int(payload, "weekly_activity_goal_total")
        if "weekly_activity_goal_run" in payload:
            goal["weekly_activity_goal_run"] = _goal_int(payload, "weekly_activity_goal_run")
        if "weekly_activity_goal_swim" in payload:
            goal["weekly_activity_goal_swim"] = _goal_int(payload, "weekly_activity_goal_swim")
        if "weekly_activity_goal_ride" in payload:
            goal["weekly_activity_goal_ride"] = _goal_int(payload, "weekly_activity_goal_ride")
        if "notes" in payload:
            goal["notes"] = payload.get("notes") or ""

        if min(
            goal["weekly_activity_goal_total"],
            goal["weekly_activity_goal_run"],
            goal["weekly_activity_goal_swim"],
            goal["weekly_activity_goal_ride"],
        ) < 0:
            return Response({"detail": "Weekly goals cannot be negative."}, status=400)
        split_sum = goal["weekly_activity_goal_run"] + goal["weekly_activity_goal_swim"] + goal["weekly_activity_goal_ride"]
        if split_sum > goal["weekly_activity_goal_total"]:
            return Response({"detail": "Weekly sport split cannot exceed total goal.", "split_sum": split_sum}, status=400)

        if goal["type"] == "race" and validate_race_fields:
            goal["target_distance_km"] = goal.get("race_distance_km")
            if not goal.get("event_name") or not goal.get("event_date"):
                return Response({"detail": "Race goal requires event name and event date."}, status=400)
            if not goal.get("race_distance_km"):
                return Response({"detail": "Race goal requires race distance (km)."}, status=400)
            if not goal.get("has_time_goal"):
                goal["target_time_min"] = None

        schedule = p.schedule or {}
        schedule["goal"] = goal
        p.schedule = schedule
        p.goal_event_name = goal.get("event_name") or ""
        p.goal_event_date = goal.get("event_date") or None
        p.goals = goal.get("notes") or ""
        p.save(update_fields=["schedule", "goal_event_name", "goal_event_date", "goals"])
    return Response(_goal_payload(p))


@api_view(["GET", "PATCH"])
def ai_settings(request):
    p, _ = AthleteProfile.objects.get_or_create(user=request.user)
    schedule = p.schedule or {}
    ai = schedule.get("ai_settings", {})
    feature_flags = ai.get("feature_flags", {})
    if request.method == "PATCH":
        ai["memory_days"] = int(request.data.get("memory_days") or ai.get("memory_days") or 30)
        ai["lookback_days"] = int(request.data.get("lookback_days") or ai.get("lookback_days") or ai["memory_days"] or 15)
        ai["max_reply_chars"] = int(request.data.get("max_reply_chars") or ai.get("max_reply_chars") or 160)
        ai["ai_model"] = str(request.data.get("ai_model") or ai.get("ai_model") or os.getenv("OPENAI_MODEL", "gpt-5-mini"))
        ai["weekly_plan_enabled"] = _as_bool(request.data.get("weekly_plan_enabled", ai.get("weekly_plan_enabled", True)))
        if "feature_flags" in request.data and isinstance(request.data.get("feature_flags"), dict):
            incoming = request.data.get("feature_flags") or {}
            feature_flags.update(
                {
                    "weekly_plan": _as_bool(incoming.get("weekly_plan", feature_flags.get("weekly_plan", True))),
                    "coach_says": _as_bool(incoming.get("coach_says", feature_flags.get("coach_says", True))),
                    "weekly_summary": _as_bool(incoming.get("weekly_summary", feature_flags.get("weekly_summary", True))),
                    "general_chat": _as_bool(incoming.get("general_chat", feature_flags.get("general_chat", True))),
                    "quick_encouragement": _as_bool(incoming.get("quick_encouragement", feature_flags.get("quick_encouragement", True))),
                }
            )
        ai["feature_flags"] = {
            "weekly_plan": _as_bool(request.data.get("enable_weekly_plan", feature_flags.get("weekly_plan", True))),
            "coach_says": _as_bool(request.data.get("enable_coach_says", feature_flags.get("coach_says", True))),
            "weekly_summary": _as_bool(request.data.get("enable_weekly_summary", feature_flags.get("weekly_summary", True))),
            "general_chat": _as_bool(request.data.get("enable_general_chat", feature_flags.get("general_chat", True))),
            "quick_encouragement": _as_bool(request.data.get("enable_quick_encouragement", feature_flags.get("quick_encouragement", True))),
        }
        schedule["ai_settings"] = ai
        p.schedule = schedule
        p.save(update_fields=["schedule"])
    return Response(
        {
            "memory_days": int(ai.get("memory_days") or 30),
            "lookback_days": int(ai.get("lookback_days") or ai.get("memory_days") or 15),
            "max_reply_chars": int(ai.get("max_reply_chars") or 160),
            "ai_model": str(ai.get("ai_model") or os.getenv("OPENAI_MODEL", "gpt-5-mini")),
            "weekly_plan_enabled": bool(ai.get("weekly_plan_enabled", True)),
            "feature_flags": {
                "weekly_plan": bool((ai.get("feature_flags") or {}).get("weekly_plan", True)),
                "coach_says": bool((ai.get("feature_flags") or {}).get("coach_says", True)),
                "weekly_summary": bool((ai.get("feature_flags") or {}).get("weekly_summary", True)),
                "general_chat": bool((ai.get("feature_flags") or {}).get("general_chat", True)),
                "quick_encouragement": bool((ai.get("feature_flags") or {}).get("quick_encouragement", True)),
            },
        }
    )


@api_view(["GET"])
def ai_context_preview(request):
    mode = (request.GET.get("mode") or "general").strip().lower()
    snapshot = build_context_snapshot(request.user, mode)
    return Response(snapshot)


@api_view(["POST"])
def ai_onboarding_generate(request):
    result = generate_onboarding_summary(request.user)
    return Response(result)


@api_view(["GET"])
def ai_history(request):
    mode = (request.GET.get("mode") or "").strip()
    try:
        qs = AIInteraction.objects.filter(user=request.user).order_by("-created_at")
    except Exception:
        return Response([])
    if mode:
        qs = qs.filter(mode=mode)
    out = []
    for r in qs[:100]:
        req = r.request_params_json or {}
        out.append(
            {
                "id": r.id,
                "mode": r.mode,
                "source": r.source,
                "status": r.status,
                "model": r.model,
                "max_chars": r.max_chars,
                "question": req.get("question") or "",
                "response_text": r.response_text,
                "prompt_system": r.prompt_system,
                "prompt_user": r.prompt_user,
                "context_hash": r.context_hash,
                "created_at": r.created_at,
            }
        )
    return Response(out)


@api_view(["GET"])
def ai_weekly_summary(request):
    return Response(generate_weekly_summary(request.user))


@api_view(["GET"])
def ai_quick_encouragement(request):
    payload = generate_quick_encouragement(request.user)
    return Response(payload)


@api_view(["POST"])
def ai_ask(request):
    p, _ = AthleteProfile.objects.get_or_create(user=request.user)
    schedule = p.schedule or {}
    ai = schedule.get("ai_settings", {})
    memory_days = int(ai.get("memory_days") or 30)
    max_chars = int(request.data.get("max_chars") or ai.get("max_reply_chars") or 160)
    max_chars = max(20, min(max_chars, 1200))
    mode = (request.data.get("mode") or "general").strip().lower()
    question = (request.data.get("question") or "").strip()
    raw_recent = request.data.get("include_recent_ai_hour", False)
    include_recent_ai_hour = str(raw_recent).lower() in {"1", "true", "yes", "on"}
    related_activity = None
    if request.data.get("activity_id"):
        related_activity = Activity.objects.filter(id=request.data.get("activity_id"), user=request.user).first()
    context = build_context_snapshot(
        request.user,
        mode,
        related_activity=related_activity,
        include_recent_ai_hour=include_recent_ai_hour,
    )
    if mode == "general_chat":
        result = answer_general_chat(request.user, question, max_chars=max_chars)
    else:
        system_prompt = (
            f"You are a concise endurance coach. Reply in practical and specific style. Never exceed {max_chars} characters. "
            "If the question mentions shoes/gear/equipment, use the provided gear context explicitly before giving advice."
        )
        user_prompt = (
            f"Mode={mode}. Max chars={max_chars}. "
            f"Context={json.dumps(context, ensure_ascii=False)}. "
            f"Question={question}"
        )
        result = run_ai_and_log(
            user=request.user,
            mode=mode,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_chars=max_chars,
            context_snapshot=context,
            related_activity=related_activity,
            request_params={
                "memory_days": memory_days,
                "max_chars": max_chars,
                "question": question,
                "include_recent_ai_hour": include_recent_ai_hour,
            },
        )
    answer = result["answer"]
    source = result["source"]
    memory = schedule.get("ai_memory", [])
    memory.append({"ts": timezone.now().isoformat(), "mode": mode, "q": question, "a": answer})
    cutoff = timezone.now() - dt.timedelta(days=memory_days)
    cleaned = []
    for m in memory[-120:]:
        try:
            mts = dt.datetime.fromisoformat(m.get("ts"))
            if timezone.is_naive(mts):
                mts = timezone.make_aware(mts, dt.timezone.utc)
            if mts >= cutoff:
                cleaned.append(m)
        except Exception:
            cleaned.append(m)
    schedule["ai_memory"] = cleaned[-80:]
    p.schedule = schedule
    p.save(update_fields=["schedule"])
    return Response(
        {
            "answer": answer,
            "mode": mode,
            "memory_count": len(schedule["ai_memory"]),
            "source": source,
            "interaction_id": result["interaction_id"],
        }
    )


@api_view(["GET"])
def current_week_plan(request):
    today = timezone.localdate()
    week_start = today - dt.timedelta(days=today.weekday())
    week_end = week_start + dt.timedelta(days=6)
    tp = TrainingPlan.objects.filter(user=request.user, status="active", start_date__lte=week_end, end_date__gte=week_start).order_by("-start_date").first()
    if not tp:
        # Ensure dashboard has a visible plan for current week.
        profile, _ = AthleteProfile.objects.get_or_create(user=request.user)
        goal = _goal_payload(profile)
        training_days = _training_days_for_user(request.user)
        sports = (["run"] * int(goal.get("weekly_activity_goal_run") or 3)) + (["swim"] * int(goal.get("weekly_activity_goal_swim") or 0)) + (["ride"] * int(goal.get("weekly_activity_goal_ride") or 0))
        if not sports:
            sports = [str(profile.primary_sport or "run").lower()]
        candidate_dates = [week_start + dt.timedelta(days=i) for i in range(7)]
        if training_days:
            candidate_dates = [d for d in candidate_dates if _weekday_key(d) in training_days] or candidate_dates
        days = []
        for i, sport in enumerate(sports[: max(1, len(candidate_dates))]):
            d = candidate_dates[i % len(candidate_dates)]
            days.append(
                {
                    "date": d.isoformat(),
                    "sport": sport,
                    "duration_min": 45 if sport != "swim" else 35,
                    "distance_km": 8 if sport == "run" else (25 if sport == "ride" else 1.5),
                    "hr_zone": "Z2",
                    "title": f"{sport.title()} aerobic",
                    "workout_type": "aerobic",
                    "coach_notes": f"Keep {sport} effort smooth and controlled. End with good form.",
                    "status": "planned",
                }
            )
        tp = TrainingPlan.objects.create(
            user=request.user,
            status="active",
            start_date=week_start,
            end_date=week_end,
            plan_json={"week_start": week_start.isoformat(), "week_end": week_end.isoformat(), "days": days, "source": "fallback_current_week"},
        )
    tp = refresh_week_plan_status(request.user, tp)
    return Response(tp.plan_json or {})


@api_view(["POST"])
def generate_week_plan(request):
    force = bool(request.data.get("force", True))
    inline = settings.DEBUG or os.getenv("CELERY_TASK_ALWAYS_EAGER", "1") == "1"
    if inline:
        result = generate_weekly_plan(request.user, force=force)
        return Response(result)
    generate_weekly_plan_task.delay(request.user.id, force)
    return Response({"queued": True})


@api_view(["GET"])
def coach_tone_view(request):
    try:
        row = AIInteraction.objects.filter(user=request.user, mode="coach_tone").order_by("-created_at").values("id", "response_text", "source", "created_at").first()
        if row:
            return Response(row)
        quick = generate_quick_encouragement(request.user)
        return Response({"response_text": quick.get("encouragement", ""), "source": "cache"})
    except Exception:
        return Response({"response_text": "", "source": "n/a"})


@api_view(["POST"])
def refresh_coach_tone(request):
    inline = settings.DEBUG or os.getenv("CELERY_TASK_ALWAYS_EAGER", "1") == "1"
    if inline:
        result = generate_coach_tone(request.user)
        return Response(result)
    generate_coach_tone_task.delay(request.user.id)
    return Response({"queued": True})


@api_view(["GET"])
def next_workout(request):
    today_date = timezone.localdate()
    week_start = today_date - dt.timedelta(days=today_date.weekday())
    week_end = week_start + dt.timedelta(days=6)
    tp = TrainingPlan.objects.filter(user=request.user, status="active", start_date__lte=week_end, end_date__gte=week_start).order_by("-start_date").first()
    if not tp:
        profile, _ = AthleteProfile.objects.get_or_create(user=request.user)
        goal = _goal_payload(profile)
        training_days = _training_days_for_user(request.user)
        sports = (["run"] * int(goal.get("weekly_activity_goal_run") or 3)) + (["swim"] * int(goal.get("weekly_activity_goal_swim") or 0)) + (["ride"] * int(goal.get("weekly_activity_goal_ride") or 0))
        if not sports:
            sports = [str(profile.primary_sport or "run").lower()]
        candidate_dates = [week_start + dt.timedelta(days=i) for i in range(7)]
        if training_days:
            candidate_dates = [d for d in candidate_dates if _weekday_key(d) in training_days] or candidate_dates
        plan_days = []
        for i, sport in enumerate(sports[: max(1, len(candidate_dates))]):
            d = candidate_dates[i % len(candidate_dates)]
            plan_days.append(
                {
                    "date": d.isoformat(),
                    "sport": sport,
                    "duration_min": 45 if sport != "swim" else 35,
                    "distance_km": 8 if sport == "run" else (25 if sport == "ride" else 1.5),
                    "hr_zone": "Z2",
                    "title": f"{sport.title()} aerobic",
                    "workout_type": "aerobic",
                    "coach_notes": f"Keep {sport} effort smooth and controlled. End with good form.",
                    "status": "planned",
                }
            )
        tp = TrainingPlan.objects.create(
            user=request.user,
            status="active",
            start_date=week_start,
            end_date=week_end,
            plan_json={"week_start": week_start.isoformat(), "week_end": week_end.isoformat(), "days": plan_days, "source": "fallback_current_week"},
        )
        days = plan_days
    else:
        tp = refresh_week_plan_status(request.user, tp)
        days = (tp.plan_json or {}).get("days") or []
    today = timezone.localdate().isoformat()
    for item in days:
        if item.get("status") == "planned" and item.get("date", "") >= today:
            return Response(item)
    for item in days:
        if item.get("status") == "planned":
            return Response(item)
    return Response({})


@api_view(["GET", "PATCH"])
def integrations(request):
    i, _ = NotificationSettings.objects.get_or_create(user=request.user)
    if request.method == "PATCH":
        s = IntegrationSerializer(i, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
    payload = IntegrationSerializer(i).data
    payload["strava_connected"] = StravaConnection.objects.filter(user=request.user).exists()
    return Response(payload)


def _telegram_setup_payload(user: User):
    conn, _ = TelegramConnection.objects.get_or_create(user=user)
    bot_info, bot_err = _telegram_api("getMe")
    bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "").strip()
    if not bot_username and isinstance(bot_info, dict):
        bot_username = bot_info.get("username") or ""
    return {
        "enabled": bool(_telegram_bot_token()),
        "connected": bool(conn.telegram_chat_id),
        "bot_username": bot_username,
        "bot_error": bot_err,
        "setup_code": conn.setup_code,
        "setup_code_expires_at": conn.setup_code_expires_at,
        "telegram_username": conn.telegram_username,
        "telegram_chat_id": conn.telegram_chat_id,
        "last_verified_at": conn.last_verified_at,
    }


@api_view(["GET"])
def telegram_setup_status(request):
    return Response(_telegram_setup_payload(request.user))


@api_view(["POST"])
def telegram_generate_code(request):
    conn, _ = TelegramConnection.objects.get_or_create(user=request.user)
    code = f"PP{secrets.token_hex(3).upper()}"
    conn.setup_code = code
    conn.setup_code_expires_at = timezone.now() + dt.timedelta(minutes=20)
    conn.save(update_fields=["setup_code", "setup_code_expires_at", "updated_at"])
    payload = _telegram_setup_payload(request.user)
    payload["setup_code"] = code
    payload["instruction"] = "Open Telegram bot and send: /start " + code
    return Response(payload)


@api_view(["POST"])
def telegram_verify_setup(request):
    conn, _ = TelegramConnection.objects.get_or_create(user=request.user)
    code = (request.data.get("code") or conn.setup_code or "").strip()
    if not code:
        return Response({"detail": "No setup code. Generate a setup code first."}, status=400)
    if conn.setup_code_expires_at and conn.setup_code_expires_at < timezone.now():
        return Response({"detail": "Setup code expired. Generate a new one."}, status=400)
    updates, err = _telegram_api("getUpdates", params={"offset": max(0, int(conn.last_update_id)), "timeout": 1, "limit": 100}, timeout=10)
    if err:
        return Response({"detail": f"Telegram verify failed: {err}"}, status=400)

    matched = None
    highest_update = int(conn.last_update_id or 0)
    for upd in updates or []:
        highest_update = max(highest_update, int(upd.get("update_id", 0)) + 1)
        msg = upd.get("message") or {}
        txt = (msg.get("text") or "").strip()
        if not txt:
            continue
        normalized = txt.replace("/start", "").replace("@", " ").strip()
        if txt.endswith(code) or normalized == code or txt == code:
            matched = msg
            break
    conn.last_update_id = highest_update
    if not matched:
        conn.save(update_fields=["last_update_id", "updated_at"])
        return Response({"verified": False, "detail": "No matching setup message found yet. Send /start CODE to the bot, then verify again."}, status=400)

    chat = matched.get("chat") or {}
    frm = matched.get("from") or {}
    conn.telegram_chat_id = str(chat.get("id") or "")
    conn.telegram_user_id = str(frm.get("id") or "")
    conn.telegram_username = frm.get("username") or ""
    conn.connected_at = conn.connected_at or timezone.now()
    conn.last_verified_at = timezone.now()
    conn.setup_code = ""
    conn.setup_code_expires_at = None
    conn.save()

    settings_row, _ = NotificationSettings.objects.get_or_create(user=request.user)
    settings_row.telegram_chat_id = conn.telegram_chat_id
    settings_row.telegram_enabled = True
    settings_row.save(update_fields=["telegram_chat_id", "telegram_enabled"])
    return Response({"verified": True, **_telegram_setup_payload(request.user)})


@api_view(["POST"])
def telegram_disconnect(request):
    conn, _ = TelegramConnection.objects.get_or_create(user=request.user)
    conn.telegram_chat_id = ""
    conn.telegram_user_id = ""
    conn.telegram_username = ""
    conn.setup_code = ""
    conn.setup_code_expires_at = None
    conn.save()
    settings_row, _ = NotificationSettings.objects.get_or_create(user=request.user)
    settings_row.telegram_chat_id = ""
    settings_row.telegram_enabled = False
    settings_row.save(update_fields=["telegram_chat_id", "telegram_enabled"])
    return Response({"ok": True, **_telegram_setup_payload(request.user)})


@api_view(["POST"])
def test_email(request):
    send_test_email_task.delay(request.user.id)
    return Response({"queued": True})


@api_view(["POST"])
def test_telegram(request):
    send_test_telegram_task.delay(request.user.id)
    return Response({"queued": True})


@api_view(["GET", "POST", "PATCH"])
def plan(request):
    tp = TrainingPlan.objects.filter(user=request.user, status="active").order_by("-created_at").first()
    if request.method == "POST" and request.path.endswith("/generate"):
        tp = TrainingPlan.objects.create(
            user=request.user,
            start_date=dt.date.today(),
            end_date=dt.date.today() + dt.timedelta(days=14),
            plan_json={"days": []},
        )
    elif request.method == "PATCH" and tp:
        s = PlanSerializer(tp, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
    if not tp:
        return Response({})
    return Response(PlanSerializer(tp).data)


@api_view(["POST"])
def import_demo_activity(request):
    now = timezone.now()
    activity_id = int(now.timestamp()) + request.user.id
    duration_s = 45 * 60
    distance_m = 10200
    stream_points = [
        [37.7749, -122.4194],
        [37.7766, -122.4172],
        [37.7781, -122.4146],
        [37.7793, -122.4117],
        [37.7802, -122.4088],
        [37.7811, -122.4062],
    ]
    activity = Activity.objects.create(
        user=request.user,
        strava_activity_id=activity_id,
        type="Run",
        name="Demo Tempo Run",
        start_date=now - dt.timedelta(days=1),
        distance_m=distance_m,
        moving_time_s=duration_s,
        elapsed_time_s=duration_s + 180,
        total_elevation_gain_m=120,
        average_speed_mps=distance_m / duration_s,
        max_speed_mps=4.8,
        avg_hr=156,
        max_hr=172,
        calories=760,
        suffer_score=76,
        raw_payload={
            "map": {"polyline_points": stream_points},
            "splits_metric": [{"split": idx + 1, "distance": 1000, "elapsed_time": t} for idx, t in enumerate([278, 276, 275, 272, 270, 269, 267, 268, 271, 274])],
        },
    )
    ActivityStream.objects.update_or_create(
        activity=activity,
        defaults={
            "raw_streams": {
                "latlng": stream_points,
                "heartrate": [142, 148, 152, 157, 161, 164],
                "altitude": [18, 21, 24, 28, 27, 23],
                "distance": [0, 1700, 3500, 5400, 7600, 10200],
            },
            "has_latlng": True,
            "has_hr": True,
            "has_cadence": False,
        },
    )
    DerivedMetrics.objects.update_or_create(
        activity=activity,
        defaults={
            "avg_pace_sec_per_km": duration_s / (distance_m / 1000),
            "intensity_score": 74.0,
            "hr_zone_distribution": {"z1": 12, "z2": 28, "z3": 36, "z4": 18, "z5": 6},
            "best_effort_estimates": {"5k": 1320, "10k": 2740},
        },
    )
    generate_activity_reaction_task.delay(activity.id, request.user.id)
    return Response({"ok": True, "activity_id": activity.id})


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def strava_webhook(request):
    if request.method == "GET":
        if request.GET.get("hub.verify_token") == os.getenv("STRAVA_VERIFY_TOKEN", "dev_verify_token"):
            return Response({"hub.challenge": request.GET.get("hub.challenge")})
        return Response(status=403)
    return Response({"received": True})
