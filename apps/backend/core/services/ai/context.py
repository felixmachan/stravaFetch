from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

from django.contrib.auth.models import User
from django.db.models import Avg
from django.utils import timezone

from core.models import AIFeatureCache, Activity, AthleteProfile, PlannedWorkout, TrainingPlan
from core.services.planned_workouts import ensure_week_rows_from_training_plan


def get_ai_settings(profile: AthleteProfile) -> dict[str, Any]:
    schedule = profile.schedule or {}
    ai = schedule.get("ai_settings") or {}
    features = ai.get("feature_flags") or {}
    return {
        "lookback_days": max(1, int(ai.get("lookback_days") or ai.get("memory_days") or 15)),
        "memory_days": max(1, int(ai.get("memory_days") or 30)),
        "max_reply_chars": max(40, int(ai.get("max_reply_chars") or 220)),
        "weekly_plan_enabled": bool(ai.get("weekly_plan_enabled", True)),
        "feature_flags": {
            "weekly_plan": bool(features.get("weekly_plan", True)),
            "coach_says": bool(features.get("coach_says", True)),
            "weekly_summary": bool(features.get("weekly_summary", True)),
            "general_chat": bool(features.get("general_chat", True)),
            "quick_encouragement": bool(features.get("quick_encouragement", True)),
        },
    }


def _goal_payload(profile: AthleteProfile) -> dict[str, Any]:
    schedule = profile.schedule or {}
    goal = schedule.get("goal") or {}
    return {
        "type": goal.get("type") or "race",
        "target_distance_km": goal.get("target_distance_km"),
        "target_time_min": goal.get("target_time_min"),
        "race_distance_km": goal.get("race_distance_km"),
        "event_name": goal.get("event_name") or profile.goal_event_name,
        "event_date": goal.get("event_date") or (str(profile.goal_event_date) if profile.goal_event_date else None),
        "weekly_activity_goal_total": int(goal.get("weekly_activity_goal_total") or 0),
        "weekly_activity_goal_run": int(goal.get("weekly_activity_goal_run") or 0),
        "weekly_activity_goal_swim": int(goal.get("weekly_activity_goal_swim") or 0),
        "weekly_activity_goal_ride": int(goal.get("weekly_activity_goal_ride") or 0),
        "notes": goal.get("notes") or profile.goals or "",
    }


def profile_json(profile: AthleteProfile) -> dict[str, Any]:
    schedule = profile.schedule or {}
    return {
        "display_name": profile.display_name,
        "primary_sport": profile.primary_sport,
        "age": profile.age,
        "experience_level": profile.experience_level,
        "availability": schedule.get("training_days") or [],
        "constraints": profile.constraints or "",
        "injury_notes": profile.injury_notes or "",
        "weekly_target_hours": profile.weekly_target_hours,
    }


def _activity_compact(a: Activity) -> dict[str, Any]:
    distance_km = round((a.distance_m or 0) / 1000.0, 2)
    duration_min = int((a.moving_time_s or 0) / 60)
    pace_sec_per_km = round((a.moving_time_s / max(distance_km, 0.1)), 1) if distance_km > 0 else None
    return {
        "id": a.id,
        "date": a.start_date.isoformat(),
        "type": a.type,
        "name": a.name,
        "distance_km": distance_km,
        "duration_min": duration_min,
        "avg_hr": int(a.avg_hr) if a.avg_hr else None,
        "pace_sec_per_km": pace_sec_per_km,
        "suffer_score": a.suffer_score,
    }


def workouts_in_lookback(user: User, lookback_days: int) -> list[Activity]:
    cutoff = timezone.now() - dt.timedelta(days=max(1, lookback_days))
    return list(
        Activity.objects.filter(user=user, is_deleted=False, start_date__gte=cutoff).order_by("-start_date")
    )


def recent_workouts(user: User, limit: int = 10) -> list[Activity]:
    return list(
        Activity.objects.filter(user=user, is_deleted=False).order_by("-start_date")[: max(1, int(limit))]
    )


def _weekly_distance(workouts: list[Activity], days: int) -> float:
    cutoff = timezone.now() - dt.timedelta(days=days)
    return round(sum((w.distance_m or 0) for w in workouts if w.start_date >= cutoff) / 1000.0, 1)


def _infer_intensity_minutes(workouts: list[Activity]) -> dict[str, int]:
    easy = moderate = hard = 0
    for w in workouts:
        mins = int((w.moving_time_s or 0) / 60)
        if mins <= 0:
            continue
        if w.avg_hr is None:
            easy += mins
            continue
        if w.avg_hr < 135:
            easy += mins
        elif w.avg_hr < 155:
            moderate += mins
        else:
            hard += mins
    return {"easy": easy, "moderate": moderate, "hard": hard}


def _risk_flags(workouts: list[Activity], trend7: float, trend28: float, profile: AthleteProfile) -> list[str]:
    flags: list[str] = []
    if profile.injury_notes:
        flags.append("injury")
    if trend28 > 0 and trend7 > trend28 * 0.45:
        flags.append("sudden_load_spike")
    hard_minutes = _infer_intensity_minutes(workouts)["hard"]
    if hard_minutes >= 120:
        flags.append("overtraining")
    return flags


def _readiness_hint(flags: list[str]) -> str:
    if not flags:
        return "Readiness appears stable for normal progression."
    if "injury" in flags:
        return "Readiness is limited by injury notes; prioritize easy load and recovery."
    if "overtraining" in flags:
        return "Readiness looks reduced from high intensity load; keep next sessions easy."
    return "Readiness is mixed due to recent load spike; reduce stress short term."


def _build_athlete_state(profile: AthleteProfile, workouts: list[Activity], lookback_days: int) -> dict[str, Any]:
    total_distance = round(sum((w.distance_m or 0) for w in workouts) / 1000.0, 1)
    total_duration = int(sum((w.moving_time_s or 0) for w in workouts) / 60)
    trend7 = _weekly_distance(workouts, 7)
    trend28 = _weekly_distance(workouts, 28)
    risk_flags = _risk_flags(workouts, trend7, trend28, profile)

    key_sessions = []
    for w in workouts[:10]:
        lower = (w.name or "").lower()
        is_key = "long" in lower or "tempo" in lower or "interval" in lower
        if (w.avg_hr and w.avg_hr >= 155) or is_key:
            key_sessions.append(_activity_compact(w))
        if len(key_sessions) >= 3:
            break

    state = {
        "lookback_days": lookback_days,
        "totals": {
            "distance_km": total_distance,
            "duration_min": total_duration,
            "session_count": len(workouts),
        },
        "intensity_minutes": _infer_intensity_minutes(workouts),
        "key_sessions": key_sessions,
        "fatigue_risk_flags": risk_flags,
        "readiness_hint": _readiness_hint(risk_flags),
        "trend": {"last7_distance_km": trend7, "last28_distance_km": trend28},
        "constraints": {
            "availability": (profile.schedule or {}).get("training_days") or [],
            "injury_notes": profile.injury_notes or "",
            "constraints": profile.constraints or "",
        },
    }
    return state


def athlete_state_from_workouts(profile: AthleteProfile, workouts: list[Activity], lookback_days: int) -> dict[str, Any]:
    return _build_athlete_state(profile, workouts, lookback_days)


def athlete_state_for_user(user: User, lookback_days: int) -> tuple[dict[str, Any], str]:
    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    workouts = workouts_in_lookback(user, lookback_days)
    last_workout = workouts[0] if workouts else None
    cache_key = f"{user.id}:{lookback_days}:{last_workout.id if last_workout else 0}"

    cached = AIFeatureCache.objects.filter(user=user, feature="athlete_state", cache_key=cache_key).first()
    if cached and isinstance(cached.payload_json, dict) and cached.payload_json:
        return cached.payload_json, cache_key

    state = _build_athlete_state(profile, workouts, lookback_days)

    AIFeatureCache.objects.update_or_create(
        user=user,
        feature="athlete_state",
        cache_key=cache_key,
        defaults={"payload_json": state, "model": "deterministic", "input_hash": ""},
    )
    return state, cache_key


def relevant_workouts(workouts: list[Activity]) -> list[dict[str, Any]]:
    selected: dict[int, dict[str, Any]] = {}

    for w in workouts[:3]:
        selected[w.id] = _activity_compact(w)

    long_run = next((w for w in workouts if "run" in (w.type or "").lower() and (w.distance_m or 0) >= 12_000), None)
    if long_run:
        selected[long_run.id] = _activity_compact(long_run)

    hard = next((w for w in workouts if (w.avg_hr or 0) >= 155 or "interval" in (w.name or "").lower()), None)
    if hard:
        selected[hard.id] = _activity_compact(hard)

    run_workouts = [w for w in workouts if "run" in (w.type or "").lower() and w.avg_hr and w.distance_m and w.moving_time_s]
    baseline = run_workouts and Activity.objects.filter(id__in=[w.id for w in run_workouts]).aggregate(avg=Avg("avg_hr")).get("avg")
    if baseline:
        for w in run_workouts:
            pace = w.moving_time_s / max((w.distance_m / 1000.0), 0.1)
            if w.avg_hr and w.avg_hr >= baseline + 10 and pace > 390:
                selected[w.id] = {**_activity_compact(w), "anomaly": "high_hr_drift"}
                break

    ordered = sorted(selected.values(), key=lambda x: x.get("date", ""), reverse=True)
    return ordered[:7]


def weekly_stats(user: User, lookback_days: int | None = None) -> dict[str, Any]:
    today = timezone.localdate()
    week_start = today - dt.timedelta(days=today.weekday())
    week_end = week_start + dt.timedelta(days=6)
    dt_cutoff = timezone.now() - dt.timedelta(days=max(1, int(lookback_days or 3650)))
    workouts = list(
        Activity.objects.filter(
            user=user,
            is_deleted=False,
            start_date__date__gte=week_start,
            start_date__date__lte=week_end,
            start_date__gte=dt_cutoff,
        ).order_by("start_date")
    )
    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "count": len(workouts),
        "distance_km": round(sum((w.distance_m or 0) for w in workouts) / 1000.0, 1),
        "duration_min": int(sum((w.moving_time_s or 0) for w in workouts) / 60),
        "workouts": [_activity_compact(w) for w in workouts],
    }


def json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_or_set_cache(
    *,
    user: User,
    feature: str,
    cache_key: str,
    input_hash: str,
    generator,
):
    row = AIFeatureCache.objects.filter(user=user, feature=feature, cache_key=cache_key).first()
    if row and row.input_hash == input_hash and isinstance(row.payload_json, dict) and row.payload_json:
        return row.payload_json, row
    payload, meta = generator()
    row, _ = AIFeatureCache.objects.update_or_create(
        user=user,
        feature=feature,
        cache_key=cache_key,
        defaults={
            "input_hash": input_hash,
            "payload_json": payload,
            "model": meta.get("model", ""),
            "tokens_input": meta.get("tokens_input"),
            "tokens_output": meta.get("tokens_output"),
        },
    )
    return payload, row


def goal_json(profile: AthleteProfile) -> dict[str, Any]:
    return _goal_payload(profile)


def current_week_plan_json(user: User) -> dict[str, Any]:
    today = timezone.localdate()
    week_start = today - dt.timedelta(days=today.weekday())
    week_end = week_start + dt.timedelta(days=6)
    tp = (
        TrainingPlan.objects.filter(user=user, status="active", start_date__lte=week_end, end_date__gte=week_start)
        .order_by("-start_date")
        .first()
    )
    if tp:
        ensure_week_rows_from_training_plan(user, tp)
    rows = list(
        PlannedWorkout.objects.filter(user=user, week_start=week_start, week_end=week_end).order_by("planned_date", "sort_order", "id")
    )
    compact_days = [
        {
            "date": row.planned_date.isoformat(),
            "sport": row.sport,
            "title": row.title,
            "status": row.status or "planned",
        }
        for row in rows
    ]
    planned_count = len([d for d in compact_days if d.get("status") == "planned"])
    done_count = len([d for d in compact_days if d.get("status") in {"done", "partial_done"}])
    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "has_plan": bool(tp or rows),
        "planned_session_count": planned_count,
        "completed_session_count": done_count,
        "days": compact_days,
    }
