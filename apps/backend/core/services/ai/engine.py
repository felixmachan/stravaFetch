from __future__ import annotations

import datetime as dt
import re
from typing import Any

from django.contrib.auth.models import User
from django.utils import timezone

from core.models import AIInteraction, Activity, AthleteProfile, CoachNote, TrainingPlan

from .client import OpenAIResponsesClient
from .context import (
    athlete_state_for_user,
    athlete_state_from_workouts,
    current_week_plan_json,
    get_ai_settings,
    get_or_set_cache,
    goal_json,
    json_hash,
    profile_json,
    recent_workouts,
    relevant_workouts,
    weekly_stats,
    workouts_in_lookback,
)
from .model_router import route_model
from .prompts import (
    SHARED_SYSTEM_POLICY,
    coach_says_user_prompt,
    general_chat_user_prompt,
    quick_encouragement_user_prompt,
    weekly_plan_user_prompt,
    weekly_summary_user_prompt,
)
from .schemas import (
    COACH_SAYS_SCHEMA,
    QUICK_ENCOURAGEMENT_SCHEMA,
    WEEKLY_PLAN_SCHEMA,
    WEEKLY_SUMMARY_SCHEMA,
    CoachSaysOutput,
    QuickEncouragementOutput,
    WeeklyPlanOutput,
    WeeklySummaryOutput,
)


def _week_start(date: dt.date | None = None) -> dt.date:
    d = date or timezone.localdate()
    return d - dt.timedelta(days=d.weekday())


def _week_end(date: dt.date | None = None) -> dt.date:
    return _week_start(date) + dt.timedelta(days=6)


def _log_interaction(
    *,
    user: User,
    mode: str,
    model: str,
    status: str,
    source: str,
    response_text: str,
    system_prompt: str,
    user_prompt: str,
    context_snapshot: dict[str, Any],
    request_params: dict[str, Any] | None = None,
    error_message: str = "",
    related_activity: Activity | None = None,
    tokens_input: int | None = None,
    tokens_output: int | None = None,
) -> AIInteraction | None:
    try:
        return AIInteraction.objects.create(
            user=user,
            mode=mode,
            model=model,
            status=status,
            source=source,
            error_message=error_message,
            response_text=response_text,
            prompt_system=system_prompt,
            prompt_user=user_prompt,
            prompt_messages_json=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            context_snapshot_json=context_snapshot,
            context_hash=json_hash(context_snapshot),
            request_params_json=request_params or {},
            related_activity=related_activity,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
        )
    except Exception:
        return None


def _cap_sentences(text: str, max_sentences: int) -> str:
    chunks = [c.strip() for c in text.replace("\n", " ").split(".") if c.strip()]
    if not chunks:
        return ""
    return ". ".join(chunks[:max_sentences]).strip() + "."


def _normalize_sentences(text: str, *, min_sentences: int, max_sentences: int, filler: str) -> str:
    chunks = [c.strip() for c in (text or "").replace("\n", " ").split(".") if c.strip()]
    chunks = chunks[:max_sentences]
    while len(chunks) < min_sentences:
        chunks.append(filler)
    return ". ".join(chunks).strip() + "."


def _build_context(user: User, *, bootstrap_last_n: int | None = None) -> dict[str, Any]:
    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    ai = get_ai_settings(profile)
    lookback = ai["lookback_days"]
    if bootstrap_last_n:
        workouts = recent_workouts(user, bootstrap_last_n)
        athlete_state = athlete_state_from_workouts(profile, workouts, lookback_days=lookback)
        athlete_state_cache_key = f"bootstrap_last_{bootstrap_last_n}"
    else:
        workouts = workouts_in_lookback(user, lookback)
        athlete_state, athlete_state_cache_key = athlete_state_for_user(user, lookback)
    return {
        "profile": profile,
        "profile_json": profile_json(profile),
        "goal_json": goal_json(profile),
        "lookback_days": lookback,
        "workouts": workouts,
        "relevant_workouts_json": relevant_workouts(workouts),
        "athlete_state_json": athlete_state,
        "athlete_state_cache_key": athlete_state_cache_key,
        "training_plan_json": current_week_plan_json(user),
        "ai_settings": ai,
    }


def _plan_locked_encouragement_text(training_plan_json: dict[str, Any], weekly_stats_json: dict[str, Any]) -> str:
    planned = int(training_plan_json.get("planned_session_count") or 0)
    completed = int(training_plan_json.get("completed_session_count") or 0)
    done_distance = float(weekly_stats_json.get("distance_km") or 0.0)
    first = f"You have completed {completed} of {completed + planned} planned sessions this week."
    second = (
        f"Keep the remaining sessions consistent and easy where planned; current completed distance is {done_distance:.1f} km."
    )
    return f"{first} {second}"


def _mentions_specific_dates(text: str) -> bool:
    value = text or ""
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", value):
        return True
    if re.search(r"\b(mon|tue|wed|thu|fri|sat|sun)(day)?\b", value, flags=re.IGNORECASE):
        return True
    return False


def _mentions_unplanned_iso_date(text: str, allowed_dates: set[str]) -> bool:
    found = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text or "")
    return any(date not in allowed_dates for date in found)


def _call_json(
    *,
    feature: str,
    user: User,
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: dict[str, Any],
    validator,
    risk_flags: list[str] | None = None,
    request_params: dict[str, Any] | None = None,
    context_snapshot: dict[str, Any] | None = None,
    related_activity: Activity | None = None,
):
    client = OpenAIResponsesClient()
    low_confidence = False
    route = route_model(feature, low_confidence=False, risk_flags=risk_flags)
    response = client.complete_json(
        model=route.model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_name=schema_name,
        schema=schema,
    )
    error_text = (response.error_message or "").lower()
    provider_bad_request = response.status == "failed" and ("400" in error_text or "invalid_request" in error_text)

    parsed = response.parsed
    if parsed is None:
        low_confidence = True
    else:
        try:
            validator.model_validate(parsed)
        except Exception:
            low_confidence = True
            parsed = None

    if low_confidence and not provider_bad_request:
        repair_prompt = f"Fix schema exactly. Keep concise. Original input: {user_prompt}"
        response = client.complete_json(
            model=route.model,
            system_prompt=system_prompt,
            user_prompt=repair_prompt,
            schema_name=schema_name,
            schema=schema,
        )
        parsed = response.parsed
        if parsed is not None:
            try:
                validator.model_validate(parsed)
                low_confidence = False
            except Exception:
                parsed = None

    if low_confidence and not provider_bad_request and route_model(feature, low_confidence=True, risk_flags=risk_flags).allow_escalation:
        esc = route_model(feature, low_confidence=True, risk_flags=risk_flags)
        response = client.complete_json(
            model=esc.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_name=schema_name,
            schema=schema,
        )
        parsed = response.parsed

    interaction = _log_interaction(
        user=user,
        mode=feature,
        model=response.model,
        status=response.status,
        source=response.source,
        response_text=response.text,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        context_snapshot=context_snapshot or {},
        request_params=request_params,
        error_message=response.error_message,
        related_activity=related_activity,
        tokens_input=response.tokens_input,
        tokens_output=response.tokens_output,
    )
    if response.status == "failed":
        print(f"[ai:{feature}] provider_error model={response.model} source={response.source} error={response.error_message[:300]}")
    return parsed, response, interaction


def generate_weekly_plan(user: User, force: bool = False, *, bootstrap_last_n: int | None = None) -> dict[str, Any]:
    ctx = _build_context(user, bootstrap_last_n=bootstrap_last_n)
    if not ctx["ai_settings"]["feature_flags"]["weekly_plan"]:
        return {"plan": {}, "skipped": True, "source": "feature_disabled"}

    next_week = _week_start() + dt.timedelta(days=7)
    input_payload = {
        "profile": ctx["profile_json"],
        "goal": ctx["goal_json"],
        "athlete_state": ctx["athlete_state_json"],
        "relevant_workouts": ctx["relevant_workouts_json"],
        "week_start": next_week.isoformat(),
    }
    input_hash = json_hash(input_payload)
    cache_key = f"{next_week.isoformat()}"

    if not force:
        cached = TrainingPlan.objects.filter(user=user, status="active", start_date=next_week).order_by("-updated_at").first()
        if cached and cached.plan_json.get("input_hash") == input_hash:
            return {"plan": cached.plan_json, "skipped": True, "source": "cache"}

    system_prompt = (
        SHARED_SYSTEM_POLICY
        + " Return strict JSON schema for weekly planning. Rules: max 2 hard sessions/week, avoid >10% weekly distance increase unless stable build is shown, "
        "long run easy by default, respect availability/rest days, and reduce load when risk flags exist."
    )
    user_prompt = weekly_plan_user_prompt(
        ctx["profile_json"],
        ctx["goal_json"],
        ctx["athlete_state_json"],
        ctx["relevant_workouts_json"],
        next_week.isoformat(),
    )
    parsed, response, interaction = _call_json(
        feature="weekly_plan",
        user=user,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_name=WEEKLY_PLAN_SCHEMA["name"],
        schema=WEEKLY_PLAN_SCHEMA["schema"],
        validator=WeeklyPlanOutput,
        risk_flags=list(ctx["athlete_state_json"].get("fatigue_risk_flags") or []),
        context_snapshot=input_payload,
        request_params={"input_hash": input_hash},
    )

    if parsed is None:
        days = []
        for offset in [0, 2, 5]:
            d = next_week + dt.timedelta(days=offset)
            days.append(
                {
                    "date": d.isoformat(),
                    "type": "easy" if offset != 5 else "long",
                    "duration_min": 45 if offset != 5 else 70,
                    "distance_km": 8 if offset != 5 else 12,
                    "intensity_notes": "Comfortable aerobic effort",
                    "main_set": "Steady continuous run",
                    "warmup_cooldown": "10 min easy + mobility",
                    "coach_note": "Keep effort controlled and finish feeling strong.",
                }
            )
        parsed = {
            "week_start_date": next_week.isoformat(),
            "plan": days,
            "weekly_targets": {
                "total_distance_km": 28,
                "total_duration_min": 160,
                "hard_sessions": 0,
                "focus": "consistency",
            },
            "risk_notes": ["ai_fallback"],
        }

    old_days = []
    for d in parsed.get("plan", []):
        old_days.append(
            {
                "date": d.get("date"),
                "sport": "run",
                "duration_min": d.get("duration_min", 0),
                "distance_km": d.get("distance_km", 0),
                "hr_zone": "Z2" if d.get("type") in {"rest", "easy", "long"} else "Z3",
                "title": d.get("type", "easy").title(),
                "workout_type": d.get("type", "easy"),
                "coach_notes": d.get("coach_note", ""),
                "status": "planned",
                "main_set": d.get("main_set", ""),
            }
        )

    plan_json = {
        "week_start": parsed.get("week_start_date", next_week.isoformat()),
        "week_end": (next_week + dt.timedelta(days=6)).isoformat(),
        "days": old_days,
        "weekly_targets": parsed.get("weekly_targets", {}),
        "risk_notes": parsed.get("risk_notes", []),
        "source": response.source,
        "model": response.model,
        "input_hash": input_hash,
    }
    tp, _ = TrainingPlan.objects.update_or_create(
        user=user,
        status="active",
        start_date=next_week,
        end_date=next_week + dt.timedelta(days=6),
        defaults={"plan_json": plan_json},
    )
    return {"plan": tp.plan_json, "interaction_id": interaction.id if interaction else None, "source": response.source, "skipped": False}


def generate_coach_says(user: User, activity: Activity) -> dict[str, Any]:
    ctx = _build_context(user)
    if not ctx["ai_settings"]["feature_flags"]["coach_says"]:
        return {"answer": "Feature disabled.", "source": "feature_disabled", "status": "fallback"}

    workout_json = {
        "id": activity.id,
        "type": activity.type,
        "distance_km": round((activity.distance_m or 0) / 1000.0, 2),
        "duration_min": int((activity.moving_time_s or 0) / 60),
        "avg_hr": int(activity.avg_hr) if activity.avg_hr else None,
    }
    system_prompt = (
        SHARED_SYSTEM_POLICY
        + " Return JSON with coach_says. Keep it 2-3 short sentences. No emojis. "
        + "If referencing planned sessions, use only training_plan_json and do not invent extra dates/sessions."
    )
    user_prompt = coach_says_user_prompt(workout_json, ctx["goal_json"], ctx["athlete_state_json"], ctx["training_plan_json"])
    parsed, response, interaction = _call_json(
        feature="coach_says",
        user=user,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_name=COACH_SAYS_SCHEMA["name"],
        schema=COACH_SAYS_SCHEMA["schema"],
        validator=CoachSaysOutput,
        risk_flags=list(ctx["athlete_state_json"].get("fatigue_risk_flags") or []),
        context_snapshot={
            "workout": workout_json,
            "goal": ctx["goal_json"],
            "athlete_state": ctx["athlete_state_json"],
            "training_plan": ctx["training_plan_json"],
        },
        related_activity=activity,
    )
    text = (parsed or {}).get("coach_says") or "Nice work. Keep the next session easy and controlled."
    text = _normalize_sentences(
        text,
        min_sentences=2,
        max_sentences=3,
        filler="If metrics are missing, use effort and breathing to stay controlled next workout",
    )
    CoachNote.objects.create(
        activity=activity,
        model=response.model,
        prompt_version="v3_coach_says",
        json_output={"interaction_id": interaction.id if interaction else None, "source": response.source},
        text_summary=text,
        tokens_used=(response.tokens_input or 0) + (response.tokens_output or 0),
    )
    refresh_weekly_artifacts(user)
    return {
        "answer": text,
        "source": response.source,
        "status": response.status,
        "interaction_id": interaction.id if interaction else None,
        "model": response.model,
    }


def generate_weekly_summary(user: User) -> dict[str, Any]:
    ctx = _build_context(user)
    if not ctx["ai_settings"]["feature_flags"]["weekly_summary"]:
        return {}

    weekly = weekly_stats(user, ctx["lookback_days"])
    last_workout_id = weekly["workouts"][-1]["id"] if weekly["workouts"] else 0
    cache_key = f"{weekly['week_start']}:{last_workout_id}"
    input_payload = {
        "weekly": weekly,
        "goal": ctx["goal_json"],
        "athlete_state": ctx["athlete_state_json"],
        "training_plan": ctx["training_plan_json"],
    }
    input_hash = json_hash(input_payload)

    def _build():
        system_prompt = (
            SHARED_SYSTEM_POLICY
            + " Return strict JSON weekly summary. headline max 8 words, highlights max 4 bullets. "
            + "training_plan_json is source of truth for planned sessions and dates; do not invent extra sessions or dates."
        )
        user_prompt = weekly_summary_user_prompt(weekly, ctx["goal_json"], ctx["athlete_state_json"], ctx["training_plan_json"])
        parsed, response, _ = _call_json(
            feature="weekly_summary",
            user=user,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_name=WEEKLY_SUMMARY_SCHEMA["name"],
            schema=WEEKLY_SUMMARY_SCHEMA["schema"],
            validator=WeeklySummaryOutput,
            risk_flags=list(ctx["athlete_state_json"].get("fatigue_risk_flags") or []),
            context_snapshot=input_payload,
            request_params={"cache_key": cache_key},
        )
        payload = parsed or {
            "headline": "Week in progress",
            "highlights": ["Data limited this week."],
            "what_to_improve": ["Add one easy aerobic session."],
            "next_week_focus": ["Consistency first."],
            "risk_flags": [],
        }
        payload["highlights"] = list(payload.get("highlights") or [])[:4]
        allowed_dates = {str(d.get("date")) for d in (ctx["training_plan_json"].get("days") or []) if isinstance(d, dict) and d.get("date")}
        for key in ["highlights", "what_to_improve", "next_week_focus", "risk_flags"]:
            rows = []
            for item in list(payload.get(key) or []):
                txt = str(item or "").strip()
                if not txt:
                    continue
                if allowed_dates and _mentions_unplanned_iso_date(txt, allowed_dates):
                    continue
                rows.append(txt)
            payload[key] = rows

        needs_addendum = bool(payload.get("risk_flags")) or "sudden_load_spike" in (ctx["athlete_state_json"].get("fatigue_risk_flags") or [])
        if needs_addendum:
            addendum_client = OpenAIResponsesClient()
            mini = addendum_client.complete_text(
                model="gpt-5-mini",
                system_prompt=SHARED_SYSTEM_POLICY + " Write one safe adjustment sentence only.",
                user_prompt=f"risk_flags={payload.get('risk_flags')} readiness={ctx['athlete_state_json'].get('readiness_hint')}",
                temperature=0.1,
            )
            payload["safe_adjustment_note"] = _cap_sentences(mini.text or "Reduce intensity and prioritize recovery next 48 hours.", 1)

        return payload, {"model": response.model, "tokens_input": response.tokens_input, "tokens_output": response.tokens_output}

    payload, _ = get_or_set_cache(user=user, feature="weekly_summary", cache_key=cache_key, input_hash=input_hash, generator=_build)
    return payload


def generate_quick_encouragement(user: User) -> dict[str, Any]:
    ctx = _build_context(user)
    if not ctx["ai_settings"]["feature_flags"]["quick_encouragement"]:
        return {"encouragement": ""}

    weekly = weekly_stats(user, ctx["lookback_days"])
    last_workout_id = weekly["workouts"][-1]["id"] if weekly["workouts"] else 0
    cache_key = f"{weekly['week_start']}:{last_workout_id}"
    input_payload = {
        "weekly": weekly,
        "goal": ctx["goal_json"],
        "athlete_state": ctx["athlete_state_json"],
        "training_plan": ctx["training_plan_json"],
    }
    input_hash = json_hash(input_payload)

    def _build():
        system_prompt = (
            SHARED_SYSTEM_POLICY
            + " Return JSON with exactly two supportive but concrete sentences in encouragement field. "
            + "Use training_plan_json as source of truth; never mention dates or planned sessions not present there."
        )
        user_prompt = quick_encouragement_user_prompt(
            weekly,
            ctx["goal_json"],
            ctx["athlete_state_json"],
            ctx["training_plan_json"],
        )
        parsed, response, _ = _call_json(
            feature="quick_encouragement",
            user=user,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_name=QUICK_ENCOURAGEMENT_SCHEMA["name"],
            schema=QUICK_ENCOURAGEMENT_SCHEMA["schema"],
            validator=QuickEncouragementOutput,
            risk_flags=list(ctx["athlete_state_json"].get("fatigue_risk_flags") or []),
            context_snapshot=input_payload,
            request_params={"cache_key": cache_key},
        )
        text = (parsed or {}).get("encouragement") or "Good momentum this week. Keep easy days truly easy so quality sessions stay sharp."
        text = _normalize_sentences(
            text,
            min_sentences=2,
            max_sentences=2,
            filler="Protect recovery so your key session quality stays high",
        )
        if _mentions_specific_dates(text):
            text = _normalize_sentences(
                _plan_locked_encouragement_text(ctx["training_plan_json"], weekly),
                min_sentences=2,
                max_sentences=2,
                filler="Stay consistent with your current plan.",
            )
        return {"encouragement": text}, {
            "model": response.model,
            "tokens_input": response.tokens_input,
            "tokens_output": response.tokens_output,
        }

    payload, _ = get_or_set_cache(user=user, feature="quick_encouragement", cache_key=cache_key, input_hash=input_hash, generator=_build)
    return payload


def answer_general_chat(user: User, message: str, *, max_chars: int = 220) -> dict[str, Any]:
    ctx = _build_context(user)
    if not ctx["ai_settings"]["feature_flags"]["general_chat"]:
        return {"answer": "General chat is disabled.", "source": "feature_disabled", "status": "fallback"}

    major_replan = "replan" in (message or "").lower() and any(
        kw in (message or "").lower() for kw in ["injury", "constraint", "available", "availability", "travel"]
    )
    risk_flags = list(ctx["athlete_state_json"].get("fatigue_risk_flags") or [])
    decision = route_model("general_chat", low_confidence=major_replan, risk_flags=risk_flags)
    system_prompt = SHARED_SYSTEM_POLICY + f" Keep response concise and below {max_chars} chars when practical."
    user_prompt = general_chat_user_prompt(
        message,
        ctx["profile_json"],
        ctx["goal_json"],
        ctx["athlete_state_json"],
        ctx["relevant_workouts_json"],
        ctx["training_plan_json"],
    )

    response = OpenAIResponsesClient().complete_text(
        model=decision.model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.2,
    )
    text = (response.text or "")[:max_chars].strip()
    interaction = _log_interaction(
        user=user,
        mode="general_chat",
        model=response.model,
        status=response.status,
        source=response.source,
        response_text=text,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        context_snapshot={
            "profile": ctx["profile_json"],
            "goal": ctx["goal_json"],
            "athlete_state": ctx["athlete_state_json"],
            "relevant_workouts": ctx["relevant_workouts_json"],
            "training_plan": ctx["training_plan_json"],
        },
        request_params={"question": message, "max_chars": max_chars},
        error_message=response.error_message,
        tokens_input=response.tokens_input,
        tokens_output=response.tokens_output,
    )
    return {
        "answer": text,
        "source": response.source,
        "status": response.status,
        "interaction_id": interaction.id if interaction else None,
        "model": response.model,
    }


def refresh_weekly_artifacts(user: User) -> dict[str, Any]:
    summary = generate_weekly_summary(user)
    encouragement = generate_quick_encouragement(user)
    return {"weekly_summary": summary, "quick_encouragement": encouragement}


def coach_tone_text(user: User) -> dict[str, Any]:
    payload = generate_quick_encouragement(user)
    text = payload.get("encouragement") or "Keep training controlled this week and protect recovery."
    interaction = _log_interaction(
        user=user,
        mode="coach_tone",
        model="gpt-5-nano",
        status="success",
        source="cache",
        response_text=text,
        system_prompt=SHARED_SYSTEM_POLICY,
        user_prompt="quick encouragement from weekly state",
        context_snapshot=payload,
    )
    return {"answer": text, "source": "cache", "interaction_id": interaction.id if interaction else None, "status": "success", "model": "gpt-5-nano"}
