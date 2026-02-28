from __future__ import annotations

import datetime as dt
from typing import Any

from django.contrib.auth.models import User
from django.utils import timezone

from core.models import Activity, PlannedWorkout, TrainingPlan


def _safe_date(value: Any) -> dt.date | None:
    raw = str(value or "").strip()
    try:
        return dt.date.fromisoformat(raw)
    except Exception:
        return None


def replace_week_plan_rows(
    user: User,
    *,
    week_start: dt.date,
    week_end: dt.date,
    days: list[dict],
    training_plan: TrainingPlan | None = None,
    source: str = "plan_json",
) -> int:
    PlannedWorkout.objects.filter(user=user, week_start=week_start, week_end=week_end).delete()
    rows = []
    for idx, item in enumerate(days or []):
        if not isinstance(item, dict):
            continue
        planned_date = _safe_date(item.get("date"))
        if not planned_date:
            continue
        rows.append(
            PlannedWorkout(
                user=user,
                training_plan=training_plan,
                week_start=week_start,
                week_end=week_end,
                planned_date=planned_date,
                sport=str(item.get("sport") or "run").strip().lower()[:32],
                duration_min=int(item.get("duration_min") or 0),
                distance_km=float(item.get("distance_km")) if item.get("distance_km") not in ("", None) else None,
                hr_zone=str(item.get("hr_zone") or "")[:16],
                title=str(item.get("title") or "")[:255],
                workout_type=str(item.get("workout_type") or "")[:64],
                coach_notes=str(item.get("coach_notes") or ""),
                status=str(item.get("status") or "planned")[:16],
                sort_order=idx,
                source=source[:32],
                meta_json={},
            )
        )
    if rows:
        PlannedWorkout.objects.bulk_create(rows)
    return len(rows)


def ensure_week_rows_from_training_plan(user: User, tp: TrainingPlan) -> int:
    if not tp or not isinstance(tp.plan_json, dict):
        return 0
    if PlannedWorkout.objects.filter(user=user, week_start=tp.start_date, week_end=tp.end_date).exists():
        return 0
    days = list(tp.plan_json.get("days") or [])
    source = str(tp.plan_json.get("source") or "plan_json")
    return replace_week_plan_rows(user, week_start=tp.start_date, week_end=tp.end_date, days=days, training_plan=tp, source=source)


def refresh_week_statuses(user: User, week_start: dt.date, week_end: dt.date) -> int:
    rows = list(PlannedWorkout.objects.filter(user=user, week_start=week_start, week_end=week_end).order_by("planned_date", "sort_order", "id"))
    if not rows:
        return 0
    activities = list(
        Activity.objects.filter(user=user, is_deleted=False, start_date__date__gte=week_start, start_date__date__lte=week_end)
    )
    by_day_sport: dict[tuple[dt.date, str], dict[str, float]] = {}
    for a in activities:
        day = a.start_date.date()
        sport = str(a.type or "").lower()
        if "run" in sport:
            key = "run"
        elif "swim" in sport:
            key = "swim"
        elif "ride" in sport or "bike" in sport or "cycle" in sport:
            key = "ride"
        else:
            key = sport[:32]
        bucket = by_day_sport.setdefault((day, key), {"count": 0, "distance_km": 0.0})
        bucket["count"] += 1
        bucket["distance_km"] += float(a.distance_m or 0.0) / 1000.0

    today = timezone.localdate()
    changed = 0
    for row in rows:
        key = (row.planned_date, str(row.sport or "").lower())
        matched = by_day_sport.get(key, {"count": 0, "distance_km": 0.0})
        has_match = int(matched.get("count") or 0) > 0
        actual_km = float(matched.get("distance_km") or 0.0)
        planned_km = float(row.distance_km or 0.0)
        deviation_pct = None
        if has_match and planned_km > 0:
            deviation_pct = (abs(actual_km - planned_km) / planned_km) * 100.0
        if has_match:
            if planned_km <= 0:
                new_status = "done"
            elif deviation_pct is not None and deviation_pct <= 5.0:
                new_status = "done"
            elif deviation_pct is not None and deviation_pct <= 50.0:
                new_status = "partial_done"
            else:
                new_status = "missed" if row.planned_date < today else "planned"
        else:
            new_status = "missed" if row.planned_date < today else "planned"
        meta = dict(row.meta_json or {})
        meta["actual_distance_km"] = round(actual_km, 3) if has_match else 0.0
        meta["planned_distance_km"] = round(planned_km, 3) if planned_km else 0.0
        meta["distance_deviation_pct"] = round(float(deviation_pct), 2) if deviation_pct is not None else None
        meta["matched_activity_count"] = int(matched.get("count") or 0)
        if row.status != new_status:
            row.status = new_status
            row.meta_json = meta
            PlannedWorkout.objects.filter(pk=row.pk).update(status=row.status, meta_json=row.meta_json, updated_at=timezone.now())
            changed += 1
        elif row.meta_json != meta:
            row.meta_json = meta
            PlannedWorkout.objects.filter(pk=row.pk).update(meta_json=row.meta_json, updated_at=timezone.now())
    return changed


def serialize_week_plan(user: User, week_start: dt.date, week_end: dt.date) -> dict[str, Any]:
    rows = list(PlannedWorkout.objects.filter(user=user, week_start=week_start, week_end=week_end).order_by("planned_date", "sort_order", "id"))
    days = [
        {
            "date": row.planned_date.isoformat(),
            "sport": row.sport,
            "duration_min": row.duration_min,
            "distance_km": row.distance_km,
            "hr_zone": row.hr_zone,
            "title": row.title,
            "workout_type": row.workout_type,
            "coach_notes": row.coach_notes,
            "status": row.status,
        }
        for row in rows
    ]
    source = rows[0].source if rows else "planned_workout_table"
    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "days": days,
        "source": source,
    }
