from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

from django.contrib.auth.models import User
from django.utils import timezone

from core.models import AIInteraction, Activity, AthleteProfile, TrainingPlan
from core.services.ai import (
    answer_general_chat,
    coach_tone_text,
    generate_coach_says,
    generate_weekly_plan as generate_weekly_plan_v3,
)
from core.services.ai.client import OpenAIResponsesClient
from core.services.ai.context import (
    athlete_state_from_workouts,
    athlete_state_for_user,
    get_ai_settings,
    goal_json,
    profile_json,
    recent_workouts,
    relevant_workouts,
    weekly_stats,
    workouts_in_lookback,
)
from core.services.ai.prompts import SHARED_SYSTEM_POLICY


def _week_start_monday(date: dt.date | None = None) -> dt.date:
    base = date or timezone.localdate()
    return base - dt.timedelta(days=base.weekday())


def _week_end_sunday(date: dt.date | None = None) -> dt.date:
    return _week_start_monday(date) + dt.timedelta(days=6)


def _safe_iso_date(value: Any, fallback: dt.date) -> dt.date:
    raw = str(value or "").strip()
    try:
        return dt.date.fromisoformat(raw)
    except Exception:
        return fallback


def _json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_context_snapshot(
    user: User,
    mode: str,
    related_activity: Activity | None = None,
    include_recent_ai_hour: bool = False,
    bootstrap_last_n: int | None = None,
) -> dict[str, Any]:
    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    settings = get_ai_settings(profile)
    workouts = recent_workouts(user, bootstrap_last_n) if bootstrap_last_n else workouts_in_lookback(user, settings["lookback_days"])
    if bootstrap_last_n:
        athlete_state = athlete_state_from_workouts(profile, workouts, settings["lookback_days"])
    else:
        athlete_state, _ = athlete_state_for_user(user, settings["lookback_days"])

    snapshot = {
        "mode": mode,
        "lookback_days": settings["lookback_days"],
        "profile_json": profile_json(profile),
        "goal_json": goal_json(profile),
        "athlete_state_json": athlete_state,
        "relevant_workouts_json": relevant_workouts(workouts),
        "weekly_stats": weekly_stats(user, settings["lookback_days"]),
        "time_info": {
            "today": timezone.localdate().isoformat(),
            "week_start": _week_start_monday().isoformat(),
            "week_end": _week_end_sunday().isoformat(),
        },
    }
    if related_activity:
        snapshot["related_activity"] = {
            "id": related_activity.id,
            "type": related_activity.type,
            "distance_km": round((related_activity.distance_m or 0) / 1000.0, 2),
            "duration_min": int((related_activity.moving_time_s or 0) / 60),
            "avg_hr": int(related_activity.avg_hr) if related_activity.avg_hr else None,
        }
    if include_recent_ai_hour:
        cutoff = timezone.now() - dt.timedelta(hours=1)
        rows = AIInteraction.objects.filter(user=user, mode="general_chat", created_at__gte=cutoff).order_by("-created_at")[:20]
        snapshot["recent_ai_hour"] = [
            {
                "at": r.created_at.isoformat(),
                "question": (r.request_params_json or {}).get("question") or "",
                "answer": r.response_text,
            }
            for r in rows
        ]
    return snapshot


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
    if mode == "general_chat":
        result = answer_general_chat(user, request_params.get("question") if request_params else user_prompt, max_chars=max_chars)
        return result

    client = OpenAIResponsesClient()
    result = client.complete_text(model="gpt-5-mini", system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.2)
    text = (result.text or "")[:max_chars]
    row = None
    try:
        row = AIInteraction.objects.create(
            user=user,
            mode=mode,
            source=result.source,
            model=result.model,
            status=result.status,
            error_message=result.error_message,
            max_chars=max_chars,
            response_text=text,
            prompt_system=system_prompt,
            prompt_user=user_prompt,
            prompt_messages_json=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            context_snapshot_json=context_snapshot,
            context_hash=_json_hash(context_snapshot),
            request_params_json=request_params or {},
            related_activity=related_activity,
            related_training_plan=related_training_plan,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
        )
    except Exception:
        row = None
    return {
        "answer": text,
        "source": result.source,
        "status": result.status,
        "interaction_id": row.id if row else None,
        "model": result.model,
    }


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
        done = False
        sport = str(item.get("sport") or "").lower()
        for a in activities:
            if a.start_date.date() == planned_date and sport and sport in (a.type or "").lower():
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


def generate_weekly_plan(
    user: User,
    force: bool = False,
    *,
    bootstrap_last_n: int | None = None,
    target_week_start: dt.date | None = None,
) -> dict[str, Any]:
    result = generate_weekly_plan_v3(user, force=force, bootstrap_last_n=bootstrap_last_n, target_week_start=target_week_start)
    start_raw = result.get("plan", {}).get("week_start", _week_start_monday().isoformat())
    try:
        start_date = dt.date.fromisoformat(str(start_raw))
    except Exception:
        start_date = _week_start_monday()
    tp = TrainingPlan.objects.filter(user=user, status="active", start_date=start_date).first()
    if tp:
        refresh_week_plan_status(user, tp)
    return result


def generate_coach_tone(user: User) -> dict[str, Any]:
    return coach_tone_text(user)


def generate_activity_reaction(user: User, activity: Activity) -> dict[str, Any]:
    return generate_coach_says(user, activity)


def generate_onboarding_summary(user: User, *, bootstrap_last_n: int | None = None) -> dict[str, Any]:
    snapshot = build_context_snapshot(user, "onboarding", bootstrap_last_n=bootstrap_last_n)
    system_prompt = SHARED_SYSTEM_POLICY + " Return JSON with summary, success_factors, risks, week_draft."
    user_prompt = f"context={snapshot}"
    result = run_ai_and_log(
        user=user,
        mode="onboarding",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_chars=900,
        context_snapshot=snapshot,
        request_params={"output": "json"},
    )
    return {
        "summary": result.get("answer", ""),
        "success_factors": [],
        "risks": [],
        "week_draft": [],
        "interaction_id": result.get("interaction_id"),
        "source": result.get("source"),
    }
