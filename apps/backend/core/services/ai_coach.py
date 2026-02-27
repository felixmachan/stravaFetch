import datetime as dt
import hashlib
import json
import os
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from openai import OpenAI

from core.models import AIInteraction, Activity, AthleteProfile, CoachNote, TrainingPlan


def _goal_payload(profile: AthleteProfile) -> dict[str, Any]:
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


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _ensure_long_run_session(days: list[dict[str, Any]], goal: dict[str, Any], context_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(days, list) or not days:
        return days
    is_race = str(goal.get("type") or "").lower() == "race"
    race_distance = _to_float(goal.get("race_distance_km") or goal.get("target_distance_km"))
    if not is_race or race_distance < 21.0:
        return days

    run_indices = [idx for idx, d in enumerate(days) if "run" in str(d.get("sport") or "").lower()]
    if not run_indices:
        return days

    has_long = False
    for idx in run_indices:
        d = days[idx]
        workout_type = str(d.get("workout_type") or "").lower()
        title = str(d.get("title") or "").lower()
        dist = _to_float(d.get("distance_km"))
        if "long" in workout_type or "long" in title or dist >= 12:
            has_long = True
            break
    if has_long:
        return days

    recent_runs = [
        _to_float(a.get("distance_km"))
        for a in (context_snapshot.get("activities_window") or [])
        if "run" in str((a or {}).get("type") or "").lower()
    ]
    recent_max = max(recent_runs) if recent_runs else 8.0
    long_km = round(max(10.0, min(18.0, recent_max * 1.25)), 1)

    target_idx = run_indices[-1]
    selected = dict(days[target_idx])
    selected["workout_type"] = "long_run"
    selected["title"] = selected.get("title") or "Long run"
    selected["distance_km"] = max(_to_float(selected.get("distance_km")), long_km)
    selected["duration_min"] = max(int(selected.get("duration_min") or 0), int(selected["distance_km"] * 6))
    selected["hr_zone"] = selected.get("hr_zone") or "Z2"
    selected["coach_notes"] = (
        "Long run for half-marathon prep. Hold controlled Z2 effort, stay relaxed early, "
        "and keep form stable in the final third."
    )
    days[target_idx] = selected
    return days


def _week_start_monday(date: dt.date | None = None) -> dt.date:
    base = date or timezone.localdate()
    return base - dt.timedelta(days=base.weekday())


def _week_end_sunday(date: dt.date | None = None) -> dt.date:
    start = _week_start_monday(date)
    return start + dt.timedelta(days=6)


def _training_days_for_profile(profile: AthleteProfile) -> list[str]:
    schedule = profile.schedule or {}
    raw = schedule.get("training_days") or []
    allowed = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    out = []
    for day in raw:
        key = str(day).strip().lower()[:3]
        if key in allowed and key not in out:
            out.append(key)
    return out


def _weekday_key(date_obj: dt.date) -> str:
    return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][date_obj.weekday()]


def _align_days_to_training_days(
    days: list[dict[str, Any]],
    *,
    week_start: dt.date,
    training_days: list[str],
) -> list[dict[str, Any]]:
    if not days or not training_days:
        return days
    allowed_dates = [week_start + dt.timedelta(days=i) for i in range(7) if _weekday_key(week_start + dt.timedelta(days=i)) in training_days]
    if not allowed_dates:
        return days
    aligned = []
    for idx, item in enumerate(days):
        if not isinstance(item, dict):
            continue
        copy = dict(item)
        copy["date"] = allowed_dates[idx % len(allowed_dates)].isoformat()
        aligned.append(copy)
    return aligned


def _safe_iso_date(value: Any, fallback: dt.date) -> dt.date:
    raw = str(value or "").strip()
    try:
        return dt.date.fromisoformat(raw)
    except Exception:
        return fallback


def _normalize_model(ai_settings: dict[str, Any]) -> str:
    allowed = {"gpt-4o-mini", "gpt-4.1-mini"}
    model = str(ai_settings.get("ai_model") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")).strip()
    return model if model in allowed else "gpt-4o-mini"


def get_ai_settings(profile: AthleteProfile) -> dict[str, Any]:
    schedule = profile.schedule or {}
    ai = schedule.get("ai_settings") or {}
    return {
        "memory_days": int(ai.get("memory_days") or 30),
        "max_reply_chars": int(ai.get("max_reply_chars") or 160),
        "ai_model": _normalize_model(ai),
        "weekly_plan_enabled": bool(ai.get("weekly_plan_enabled", True)),
    }


def _activity_summary(a: Activity) -> dict[str, Any]:
    return {
        "id": a.id,
        "date": a.start_date.isoformat(),
        "type": a.type,
        "name": a.name,
        "distance_km": round((a.distance_m or 0) / 1000, 2),
        "duration_min": int((a.moving_time_s or 0) / 60),
        "avg_hr": int(a.avg_hr) if a.avg_hr else None,
    }


def build_context_snapshot(
    user: User,
    mode: str,
    related_activity: Activity | None = None,
    include_recent_ai_hour: bool = False,
) -> dict[str, Any]:
    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    goal = _goal_payload(profile)
    ai = get_ai_settings(profile)
    cutoff = timezone.now() - dt.timedelta(days=ai["memory_days"])
    activities_qs = Activity.objects.filter(user=user, is_deleted=False, start_date__gte=cutoff).order_by("-start_date")[:10]
    activities = [_activity_summary(a) for a in activities_qs]
    related = _activity_summary(related_activity) if related_activity else None
    schedule = profile.schedule or {}
    gear = schedule.get("strava_gear") or {}
    shoes = []
    for shoe in (gear.get("shoes") or []):
        if not isinstance(shoe, dict):
            continue
        shoes.append(
            {
                "id": shoe.get("id"),
                "name": shoe.get("name"),
                "brand_name": shoe.get("brand_name"),
                "model_name": shoe.get("model_name"),
                "distance_km": round(float(shoe.get("distance") or 0) / 1000.0, 1),
                "primary": bool(shoe.get("primary")),
            }
        )
    bikes = []
    for bike in (gear.get("bikes") or []):
        if not isinstance(bike, dict):
            continue
        bikes.append(
            {
                "id": bike.get("id"),
                "name": bike.get("name"),
                "brand_name": bike.get("brand_name"),
                "model_name": bike.get("model_name"),
                "distance_km": round(float(bike.get("distance") or 0) / 1000.0, 1),
                "primary": bool(bike.get("primary")),
            }
        )
    full_profile = {
        "display_name": profile.display_name,
        "age": profile.age,
        "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg,
        "primary_sport": profile.primary_sport,
        "current_race_pace": profile.current_race_pace,
        "goal_race_pace": profile.goal_race_pace,
        "goal_event_name": profile.goal_event_name,
        "goal_event_date": str(profile.goal_event_date) if profile.goal_event_date else None,
        "goals": profile.goals,
        "constraints": profile.constraints,
        "injury_notes": profile.injury_notes,
        "experience_level": profile.experience_level,
        "preferred_sports": profile.preferred_sports or [],
        "weekly_target_hours": profile.weekly_target_hours,
        "hr_zones": profile.hr_zones or [],
        "schedule": schedule,
    }
    snapshot = {
        "mode": mode,
        "identity": {
            "username": user.username,
            "email": user.email,
            "display_name": profile.display_name,
            "primary_sport": profile.primary_sport,
            "height_cm": profile.height_cm,
            "weight_kg": profile.weight_kg,
            "birth_date": (profile.schedule or {}).get("birth_date"),
            "training_days": (profile.schedule or {}).get("training_days", []),
        },
        "goal": goal,
        "time_info": {
            "today": timezone.localdate().isoformat(),
            "week_start": _week_start_monday().isoformat(),
            "week_end": _week_end_sunday().isoformat(),
        },
        "ai_settings": ai,
        "profile_full": full_profile,
        "activities_window": activities,
        "activities_window_count": len(activities),
        "gear": {"shoes": shoes, "bikes": bikes},
        "related_activity": related,
    }
    if include_recent_ai_hour:
        cutoff_ai = timezone.now() - dt.timedelta(hours=1)
        rows = (
            AIInteraction.objects.filter(user=user, mode="general_chat", created_at__gte=cutoff_ai)
            .order_by("-created_at")[:20]
        )
        snapshot["recent_ai_hour"] = [
            {
                "at": r.created_at.isoformat(),
                "question": (r.request_params_json or {}).get("question") or (r.prompt_user or "")[:220],
                "answer": r.response_text,
            }
            for r in rows
        ]
    return snapshot


def _json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_json(text: str) -> dict[str, Any]:
    txt = (text or "").strip()
    if not txt:
        return {}
    try:
        return json.loads(txt)
    except Exception:
        pass
    start = txt.find("{")
    end = txt.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(txt[start : end + 1])
        except Exception:
            return {}
    return {}


def run_ai_and_log(
    *,
    user: User,
    mode: str,
    system_prompt: str,
    user_prompt: str,
    max_chars: int,
    context_snapshot: dict[str, Any],
    related_activity: Activity | None = None,
    related_training_plan: TrainingPlan | None = None,
    request_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = request_params or {}
    model = _normalize_model((context_snapshot.get("ai_settings") or {}))
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    source = "unknown"
    status = "success"
    error_message = ""
    response_text = ""
    tokens_input = None
    tokens_output = None
    key = os.getenv("OPENAI_API_KEY", "").strip()

    if not key:
        source = "no_api_key"
        status = "fallback"
        response_text = "AI key missing. Set OPENAI_API_KEY to enable live responses."
    else:
        try:
            client = OpenAI(api_key=key)
            resp = client.responses.create(
                model=model,
                input=messages,
            )
            source = "openai"
            response_text = (resp.output_text or "").strip() or "No response generated."
            usage = getattr(resp, "usage", None)
            if usage:
                tokens_input = getattr(usage, "input_tokens", None)
                tokens_output = getattr(usage, "output_tokens", None)
        except Exception as exc:
            source = "provider_error"
            status = "failed"
            error_message = str(exc)
            response_text = "AI provider error. Try again shortly."

    interaction = None
    try:
        interaction = AIInteraction.objects.create(
            user=user,
            mode=mode,
            source=source,
            model=model,
            status=status,
            error_message=error_message,
            max_chars=max_chars,
            response_text=response_text,
            prompt_system=system_prompt,
            prompt_user=user_prompt,
            prompt_messages_json=messages,
            context_snapshot_json=context_snapshot,
            context_hash=_json_hash(context_snapshot),
            request_params_json=params,
            related_activity=related_activity,
            related_training_plan=related_training_plan,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
        )
    except Exception:
        # Keep runtime stable even if migration/table is missing.
        interaction = None
    return {
        "answer": response_text,
        "source": source,
        "status": status,
        "interaction_id": interaction.id if interaction else None,
        "model": model,
    }


def _default_week_plan(user: User) -> dict[str, Any]:
    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    goal = _goal_payload(profile)
    training_days = _training_days_for_profile(profile)
    run_target = int(goal.get("weekly_activity_goal_run") or 3)
    swim_target = int(goal.get("weekly_activity_goal_swim") or 0)
    ride_target = int(goal.get("weekly_activity_goal_ride") or 0)
    sports = (["run"] * run_target) + (["swim"] * swim_target) + (["ride"] * ride_target)
    if not sports:
        sports = [str(profile.primary_sport or "run").lower()]
    start = _week_start_monday() + dt.timedelta(days=7)
    candidate_dates = [start + dt.timedelta(days=i) for i in range(7)]
    if training_days:
        candidate_dates = [d for d in candidate_dates if _weekday_key(d) in training_days] or candidate_dates
    days = []
    for i, sport in enumerate(sports[: max(1, len(candidate_dates))]):
        date = candidate_dates[i % len(candidate_dates)]
        if i < len(sports):
            days.append(
                {
                    "date": date.isoformat(),
                    "sport": sport,
                    "duration_min": 45 if sport != "swim" else 35,
                    "distance_km": 8 if sport == "run" else (25 if sport == "ride" else 1.5),
                    "hr_zone": "Z2",
                    "title": f"{sport.title()} aerobic",
                    "workout_type": "aerobic",
                    "coach_notes": f"Keep this {sport} session relaxed and technically clean. Focus on smooth rhythm and controlled breathing.",
                    "status": "planned",
                }
            )
    return {
        "week_start": start.isoformat(),
        "week_end": (start + dt.timedelta(days=6)).isoformat(),
        "days": days,
        "generated_at": timezone.now().isoformat(),
        "source": "fallback",
    }


def _upsert_training_plan(user: User, payload: dict[str, Any], source: str = "ai") -> TrainingPlan:
    week_start = dt.date.fromisoformat(payload["week_start"])
    week_end = dt.date.fromisoformat(payload["week_end"])
    with transaction.atomic():
        tp, _ = TrainingPlan.objects.update_or_create(
            user=user,
            status="active",
            start_date=week_start,
            end_date=week_end,
            defaults={"plan_json": {**payload, "source": source}},
        )
    return tp


def refresh_week_plan_status(user: User, plan: TrainingPlan | None = None) -> TrainingPlan | None:
    tp = plan or TrainingPlan.objects.filter(user=user, status="active").order_by("-start_date").first()
    if not tp or not isinstance(tp.plan_json, dict):
        return tp
    days = list(tp.plan_json.get("days") or [])
    if not days:
        return tp
    activities = Activity.objects.filter(user=user, is_deleted=False, start_date__date__gte=tp.start_date, start_date__date__lte=tp.end_date)
    today = timezone.localdate()
    changed = False
    for idx, item in enumerate(days):
        if not isinstance(item, dict) or not item.get("date"):
            continue
        planned_date = _safe_iso_date(item.get("date"), tp.start_date + dt.timedelta(days=min(idx, 6)))
        normalized_iso = planned_date.isoformat()
        if item.get("date") != normalized_iso:
            item["date"] = normalized_iso
            changed = True
        planned_sport = str(item.get("sport") or "").lower()
        done = False
        for a in activities:
            a_date = a.start_date.date()
            a_type = (a.type or "").lower()
            if a_date == planned_date and planned_sport and planned_sport in a_type:
                done = True
                break
        new_status = "done" if done else ("missed" if planned_date < today else "planned")
        if item.get("status") != new_status:
            item["status"] = new_status
            changed = True
    if changed:
        payload = dict(tp.plan_json)
        payload["days"] = days
        tp.plan_json = payload
        tp.save(update_fields=["plan_json", "updated_at"])
    return tp


def generate_weekly_plan(user: User, force: bool = False) -> dict[str, Any]:
    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    ctx = build_context_snapshot(user, "weekly_plan")
    goal = _goal_payload(profile)
    training_days = _training_days_for_profile(profile)
    ai = get_ai_settings(profile)
    existing = TrainingPlan.objects.filter(user=user, status="active").order_by("-start_date").first()
    next_week_start = _week_start_monday() + dt.timedelta(days=7)
    next_week_end = next_week_start + dt.timedelta(days=6)
    if existing and not force and existing.start_date == next_week_start:
        refreshed = refresh_week_plan_status(user, existing)
        return {"plan": refreshed.plan_json if refreshed else {}, "skipped": True}

    system_prompt = (
        "You are an endurance coach. Return strict JSON only with fields: "
        "week_start, week_end, days[]. days item keys: "
        "date,sport,duration_min,distance_km,hr_zone,title,workout_type,coach_notes,status. "
        "Use status=planned. Keep 3-7 sessions. "
        "If race goal distance is 21km or more, include at least one long run session."
    )
    user_prompt = (
        f"Build next week plan for Monday-Sunday. Context={ctx}. "
        "Use goal and recent workload. Keep practical and safe progression."
    )
    result = run_ai_and_log(
        user=user,
        mode="weekly_plan",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_chars=1200,
        context_snapshot=ctx,
        request_params={"output": "json"},
    )
    parsed = _extract_json(result["answer"])
    if not parsed.get("week_start") or not parsed.get("days"):
        parsed = _default_week_plan(user)
    parsed["week_start"] = parsed.get("week_start") or next_week_start.isoformat()
    parsed["week_end"] = parsed.get("week_end") or next_week_end.isoformat()
    try:
        parsed_week_start = dt.date.fromisoformat(parsed["week_start"])
    except Exception:
        parsed_week_start = next_week_start
    normalized_days = []
    for idx, item in enumerate(parsed.get("days", [])):
        if not isinstance(item, dict):
            continue
        safe_date = _safe_iso_date(item.get("date"), parsed_week_start + dt.timedelta(days=min(idx, 6))).isoformat()
        normalized_days.append(
            {
                "date": safe_date,
                "sport": item.get("sport") or "run",
                "duration_min": item.get("duration_min"),
                "distance_km": item.get("distance_km"),
                "hr_zone": item.get("hr_zone") or "Z2",
                "title": item.get("title") or "Planned workout",
                "workout_type": item.get("workout_type") or "aerobic",
                "coach_notes": item.get("coach_notes")
                or "Stay controlled, focus on technique, and finish with good form.",
                "status": item.get("status") or "planned",
            }
        )
    parsed["days"] = _align_days_to_training_days(
        normalized_days,
        week_start=parsed_week_start,
        training_days=training_days,
    )
    parsed["days"] = _ensure_long_run_session(parsed["days"], goal, ctx)
    tp = _upsert_training_plan(user, parsed, source=result["source"])
    refresh_week_plan_status(user, tp)
    return {"plan": tp.plan_json, "interaction_id": result["interaction_id"], "source": result["source"], "skipped": False}


def generate_coach_tone(user: User) -> dict[str, Any]:
    ctx = build_context_snapshot(user, "coach_tone")
    week_start = _week_start_monday()
    week_end = _week_end_sunday()
    weekly = Activity.objects.filter(user=user, is_deleted=False, start_date__date__gte=week_start, start_date__date__lte=week_end).order_by("start_date")
    rows = [
        {
            "idx_in_week": idx + 1,
            "type": a.type,
            "distance_km": round((a.distance_m or 0) / 1000, 2),
            "duration_min": int((a.moving_time_s or 0) / 60),
            "avg_hr": int(a.avg_hr) if a.avg_hr else None,
        }
        for idx, a in enumerate(weekly)
    ]
    system_prompt = "You are an encouraging coach. Reply in maximum 4 sentences."
    user_prompt = f"Give weekly coach tone from this week's sessions={rows}. Context={ctx}"
    return run_ai_and_log(
        user=user,
        mode="coach_tone",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_chars=450,
        context_snapshot=ctx,
    )


def generate_activity_reaction(user: User, activity: Activity) -> dict[str, Any]:
    ctx = build_context_snapshot(user, "activity_reaction", related_activity=activity)
    system_prompt = "You are an endurance coach. Reply in one short sentence plus one actionable next step."
    user_prompt = f"React to activity quickly. Activity={_activity_summary(activity)}. Context={ctx}"
    result = run_ai_and_log(
        user=user,
        mode="activity_reaction",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_chars=220,
        context_snapshot=ctx,
        related_activity=activity,
    )
    CoachNote.objects.create(
        activity=activity,
        model=result["model"],
        prompt_version="v2_activity_reaction",
        json_output={"interaction_id": result["interaction_id"], "source": result["source"]},
        text_summary=result["answer"],
    )
    return result


def generate_onboarding_summary(user: User) -> dict[str, Any]:
    ctx = build_context_snapshot(user, "onboarding")
    system_prompt = (
        "You are a concise endurance coach. Return strict JSON only with fields: "
        "summary, success_factors(array), risks(array), week_draft(array of short bullets)."
    )
    user_prompt = f"Create onboarding analysis from context={ctx}. Include goal timeline realism and first-week draft."
    result = run_ai_and_log(
        user=user,
        mode="onboarding",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_chars=900,
        context_snapshot=ctx,
        request_params={"output": "json"},
    )
    parsed = _extract_json(result["answer"])
    if not parsed:
        parsed = {
            "summary": result["answer"],
            "success_factors": [],
            "risks": [],
            "week_draft": [],
        }
    return {**parsed, "interaction_id": result["interaction_id"], "source": result["source"]}
