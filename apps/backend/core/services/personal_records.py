from __future__ import annotations

from collections import defaultdict

from django.utils import timezone

from core.models import PersonalRecord


def _to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _to_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _distance_label(distance_m: float | None) -> str:
    if not distance_m or distance_m <= 0:
        return "Effort"
    rounded = int(round(distance_m))
    known = {
        400: "400m",
        800: "800m",
        1000: "1K",
        1609: "1 mile",
        2000: "2K",
        3219: "2 mile",
        5000: "5K",
        10000: "10K",
        21097: "Half Marathon",
        42195: "Marathon",
    }
    if rounded in known:
        return known[rounded]
    if rounded >= 1000 and rounded % 1000 == 0:
        return f"{rounded // 1000}K"
    return f"{rounded}m"


def normalize_best_effort(effort: dict) -> dict | None:
    if not isinstance(effort, dict):
        return None
    elapsed = _to_int(effort.get("elapsed_time"), 0)
    if elapsed <= 0:
        return None
    distance_m = _to_float(effort.get("distance"))
    label_raw = str(effort.get("name") or "").strip()
    label = label_raw or _distance_label(distance_m)
    key = label.lower()
    if not key:
        return None
    return {
        "effort_key": key[:96],
        "effort_label": label[:128],
        "distance_m": distance_m,
        "elapsed_time_s": elapsed,
        "pr_rank": _to_int(effort.get("pr_rank"), 0),
    }


def update_personal_records_for_activity(*, user, activity, best_efforts: list[dict]) -> None:
    normalized = [item for item in (normalize_best_effort(e) for e in (best_efforts or [])) if item]
    if not normalized:
        return

    keys = sorted({item["effort_key"] for item in normalized})
    existing_rows = list(
        PersonalRecord.objects.filter(user=user, effort_key__in=keys).select_related("source_activity").order_by("effort_key", "elapsed_time_s", "achieved_at")
    )
    existing_by_key = defaultdict(list)
    for row in existing_rows:
        existing_by_key[row.effort_key].append(
            {
                "effort_key": row.effort_key,
                "effort_label": row.effort_label,
                "distance_m": row.distance_m,
                "elapsed_time_s": int(row.elapsed_time_s or 0),
                "achieved_at": row.achieved_at,
                "source_activity": row.source_activity,
                "source_strava_activity_id": row.source_strava_activity_id,
            }
        )

    now = timezone.now()
    merged_top = defaultdict(list)
    for key in keys:
        candidates = list(existing_by_key.get(key, []))
        for item in [x for x in normalized if x["effort_key"] == key]:
            candidates.append(
                {
                    "effort_key": item["effort_key"],
                    "effort_label": item["effort_label"],
                    "distance_m": item["distance_m"],
                    "elapsed_time_s": item["elapsed_time_s"],
                    "achieved_at": activity.start_date or now,
                    "source_activity": activity,
                    "source_strava_activity_id": activity.strava_activity_id,
                }
            )
        candidates.sort(key=lambda x: (x["elapsed_time_s"], x["achieved_at"] or now))
        deduped = []
        seen = set()
        for item in candidates:
            dedupe_key = (item["elapsed_time_s"], item["source_strava_activity_id"])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            deduped.append(item)
            if len(deduped) >= 3:
                break
        merged_top[key] = deduped

    PersonalRecord.objects.filter(user=user, effort_key__in=keys).delete()
    rows = []
    for key in keys:
        for idx, item in enumerate(merged_top.get(key, []), start=1):
            rows.append(
                PersonalRecord(
                    user=user,
                    effort_key=item["effort_key"],
                    effort_label=item["effort_label"],
                    distance_m=item["distance_m"],
                    rank=idx,
                    elapsed_time_s=item["elapsed_time_s"],
                    achieved_at=item["achieved_at"],
                    source_activity=item["source_activity"],
                    source_strava_activity_id=item["source_strava_activity_id"],
                )
            )
    if rows:
        PersonalRecord.objects.bulk_create(rows)


def personal_records_snapshot(user) -> list[dict]:
    rows = list(
        PersonalRecord.objects.filter(user=user).select_related("source_activity").order_by("effort_label", "rank")
    )
    grouped = defaultdict(list)
    meta = {}
    for row in rows:
        grouped[row.effort_key].append(
            {
                "rank": int(row.rank),
                "elapsed_time_s": int(row.elapsed_time_s),
                "achieved_at": row.achieved_at.isoformat() if row.achieved_at else None,
                "activity_id": row.source_activity_id,
                "activity_name": row.source_activity.name if row.source_activity else "",
                "source_strava_activity_id": row.source_strava_activity_id,
            }
        )
        if row.effort_key not in meta:
            meta[row.effort_key] = {
                "effort_key": row.effort_key,
                "effort_label": row.effort_label,
                "distance_m": row.distance_m,
            }
    out = []
    for effort_key, records in grouped.items():
        out.append({**meta[effort_key], "records": records})
    out.sort(key=lambda x: x.get("effort_label") or "")
    return out


def podium_prs_from_best_efforts(best_efforts: list[dict]) -> list[dict]:
    parsed = []
    for item in best_efforts or []:
        normalized = normalize_best_effort(item)
        if not normalized:
            continue
        rank = normalized.get("pr_rank") or 0
        if rank not in {1, 2, 3}:
            continue
        parsed.append(
            {
                "rank": rank,
                "effort_label": normalized["effort_label"],
                "elapsed_time_s": normalized["elapsed_time_s"],
            }
        )
    parsed.sort(key=lambda x: x["rank"])
    return parsed
