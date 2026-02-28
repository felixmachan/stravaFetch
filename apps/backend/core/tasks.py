import datetime as dt
import os
import requests
from celery import shared_task
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.utils import timezone
from .models import Activity, ActivityStream, AthleteProfile, CoachNote, DerivedMetrics, NotificationSettings, StravaConnection
from .services.ai import refresh_weekly_artifacts
from .services.coaching_engine import deterministic_metrics
from .services.ai_coach import (
    generate_activity_reaction as generate_activity_reaction_service,
    generate_coach_tone as generate_coach_tone_service,
    generate_weekly_plan as generate_weekly_plan_service,
)
from .services.personal_records import update_personal_records_for_activity
from .services.strava import refresh_if_needed, sync_athlete_profile_from_connection


def _summary_defaults(user, a):
    return {
        'user': user,
        'type': a.get('type', 'Other'),
        'sport_type': a.get('sport_type') or '',
        'name': a.get('name', 'Activity'),
        'start_date': a['start_date'],
        'start_date_local': a.get('start_date_local'),
        'timezone_name': a.get('timezone') or '',
        'distance_m': a.get('distance', 0),
        'moving_time_s': a.get('moving_time', 0),
        'elapsed_time_s': a.get('elapsed_time', 0),
        'total_elevation_gain_m': a.get('total_elevation_gain', 0),
        'average_speed_mps': a.get('average_speed', 0),
        'max_speed_mps': a.get('max_speed', 0),
        'average_cadence': a.get('average_cadence'),
        'average_watts': a.get('average_watts'),
        'weighted_average_watts': a.get('weighted_average_watts'),
        'avg_hr': a.get('average_heartrate'),
        'max_hr': a.get('max_heartrate'),
        'calories': a.get('calories'),
        'suffer_score': a.get('suffer_score'),
        'achievement_count': int(a.get('achievement_count') or 0),
        'kudos_count': int(a.get('kudos_count') or 0),
        'comment_count': int(a.get('comment_count') or 0),
        'device_name': a.get('device_name') or '',
        'trainer': bool(a.get('trainer')),
        'commute': bool(a.get('commute')),
        'manual': bool(a.get('manual')),
        'map_summary_polyline': a.get('map', {}).get('summary_polyline'),
        'raw_payload': a,
        'is_deleted': False,
    }


@shared_task
def poll_strava_activities():
    for conn in StravaConnection.objects.select_related('user').all():
        sync_now_for_user.delay(conn.user_id)


@shared_task
def generate_weekly_plan_scheduler():
    # Runs hourly from beat; users control day/hour in schedule.plan_generation.
    now = timezone.localtime()
    weekday_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    next_week_start = (timezone.localdate() - dt.timedelta(days=timezone.localdate().weekday())) + dt.timedelta(days=7)
    next_week_key = next_week_start.isoformat()
    for profile in AthleteProfile.objects.select_related("user").all():
        schedule = profile.schedule or {}
        ai_settings = schedule.get("ai_settings") or {}
        if ai_settings.get("weekly_plan_enabled", True):
            cfg = (schedule.get("plan_generation") or {}) if isinstance(schedule, dict) else {}
            day = str(cfg.get("day") or "sun").strip().lower()[:3]
            hour = int(cfg.get("hour") or 2)
            if day not in {"sat", "sun"}:
                day = "sun"
            hour = max(0, min(23, hour))
            if now.weekday() != weekday_map[day] or now.hour != hour:
                continue
            if str(cfg.get("last_auto_generated_week_start") or "") == next_week_key:
                continue
            generate_weekly_plan_task.delay(profile.user_id, False, next_week_key)
            cfg["last_auto_generated_week_start"] = next_week_key
            schedule["plan_generation"] = cfg
            profile.schedule = schedule
            profile.save(update_fields=["schedule"])


@shared_task
def generate_weekly_plan_sunday():
    # Backward-compatible task name.
    return generate_weekly_plan_scheduler()


@shared_task
def generate_weekly_plan_task(user_id, force=False, target_week_start_iso=None):
    user = User.objects.get(id=user_id)
    target_week_start = None
    if target_week_start_iso:
        try:
            target_week_start = dt.date.fromisoformat(str(target_week_start_iso))
        except Exception:
            target_week_start = None
    return generate_weekly_plan_service(user, force=bool(force), target_week_start=target_week_start)


@shared_task
def generate_coach_tone_task(user_id):
    user = User.objects.get(id=user_id)
    return generate_coach_tone_service(user)


@shared_task
def refresh_weekly_artifacts_task(user_id):
    user = User.objects.get(id=user_id)
    return refresh_weekly_artifacts(user)


@shared_task
def generate_activity_reaction_task(activity_id, user_id):
    user = User.objects.get(id=user_id)
    activity = Activity.objects.get(id=activity_id, user=user)
    try:
        result = generate_activity_reaction_service(user, activity)
    except Exception:
        # Onboarding readiness depends on reaction coverage; store a fallback note
        # so a transient AI/provider error cannot stall the registration flow forever.
        CoachNote.objects.get_or_create(
            activity=activity,
            defaults={
                "model": "deterministic_fallback",
                "prompt_version": "fallback_coach_says",
                "json_output": {"source": "fallback", "reason": "reaction_generation_failed"},
                "text_summary": "Nice work. Keep the next session easy and controlled while we recover full AI context.",
                "tokens_used": 0,
            },
        )
        result = {"answer": "Fallback reaction created.", "source": "fallback", "status": "fallback"}
    refresh_weekly_artifacts_task.delay(user.id)
    return result


@shared_task
def sync_now_for_user(user_id, import_from_date_iso=None):
    user = User.objects.get(id=user_id)
    conn = StravaConnection.objects.get(user=user)
    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    schedule = profile.schedule or {}
    onboarding = schedule.get("onboarding", {})
    onboarding["sync_in_progress"] = True
    onboarding["full_sync_complete"] = False
    schedule["onboarding"] = onboarding
    profile.schedule = schedule
    profile.save(update_fields=["schedule"])
    token = refresh_if_needed(conn)
    try:
        sync_athlete_profile_from_connection(user, conn, force=False)
    except Exception:
        pass
    # On onboarding, sync at most the latest 30 activities.

    fetched = 0
    upserted = 0
    new_activities = 0
    max_activities = 30
    import_from_date = None
    sync_failed = False
    sync_error = ""
    synced_strava_ids = []
    parsed_activities = 0
    selected_activities = 0
    import_from_schedule = str((profile.schedule or {}).get("import_from_date") or "").strip()
    import_from_value = str(import_from_date_iso or import_from_schedule or "").strip()
    if import_from_value:
        try:
            import_from_date = dt.date.fromisoformat(import_from_value)
            max_activities = None
        except Exception:
            import_from_date = None

    def _activity_date(activity_payload):
        raw_start = str(activity_payload.get("start_date") or "").strip()
        if not raw_start:
            return None
        normalized = raw_start.replace("Z", "+00:00")
        try:
            return dt.datetime.fromisoformat(normalized).date()
        except Exception:
            return None

    try:
        if import_from_date:
            # Backfill mode for onboarding: walk pages until we pass the cutoff date.
            per_page = 100
            page = 1
            while True:
                r = requests.get(
                    'https://www.strava.com/api/v3/athlete/activities',
                    headers={'Authorization': f'Bearer {token}'},
                    params={'per_page': per_page, 'page': page},
                    timeout=30,
                )
                if r.status_code == 429:
                    sync_failed = True
                    sync_error = "strava_rate_limited"
                    break
                r.raise_for_status()
                batch = r.json() or []
                if not batch:
                    break
                fetched += len(batch)
                stop_after_batch = False
                for a in batch:
                    parsed_activities += 1
                    activity_date = _activity_date(a)
                    if activity_date and activity_date < import_from_date:
                        stop_after_batch = True
                        continue
                    selected_activities += 1
                    obj, created = Activity.objects.update_or_create(
                        strava_activity_id=a['id'],
                        defaults=_summary_defaults(user, a),
                    )
                    synced_strava_ids.append(int(a['id']))
                    try:
                        sync_streams_for_activity(user, obj, token)
                    except Exception:
                        # Keep activity row even if stream sync fails.
                        pass
                    upserted += 1
                    if created:
                        new_activities += 1
                if stop_after_batch or len(batch) < per_page:
                    break
                page += 1
        else:
            # Regular polling mode: keep request light.
            r = requests.get(
                'https://www.strava.com/api/v3/athlete/activities',
                headers={'Authorization': f'Bearer {token}'},
                params={'per_page': max_activities, 'page': 1},
                timeout=30,
            )
            if r.status_code == 429:
                sync_failed = True
                sync_error = "strava_rate_limited"
            else:
                r.raise_for_status()
                items = r.json() or []
                # Defensive sort to ensure newest-first ordering.
                items = sorted(items, key=lambda x: str(x.get('start_date') or ''), reverse=True)[:max_activities]
                fetched = len(items)
                parsed_activities = len(items)
                selected_activities = len(items)
                for a in items:
                    obj, created = Activity.objects.update_or_create(
                        strava_activity_id=a['id'],
                        defaults=_summary_defaults(user, a),
                    )
                    synced_strava_ids.append(int(a['id']))
                    try:
                        sync_streams_for_activity(user, obj, token)
                    except Exception:
                        # Keep activity row even if stream sync fails.
                        pass
                    upserted += 1
                    if created:
                        new_activities += 1
    except Exception as exc:
        sync_failed = True
        sync_error = str(exc)[:250]

    # Do not hard-delete or hide non-polled historical rows here.
    # Poll windows can be partial (e.g., date-based import) and should not mark other activities deleted.

    conn.last_sync_at = timezone.now()
    conn.last_polled_at = timezone.now()
    conn.save(update_fields=['last_sync_at', 'last_polled_at'])

    # Activity AI reactions are generated manually per workout (one-time).

    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    schedule = profile.schedule or {}
    onboarding = schedule.get("onboarding", {})
    recent_ids = list(
        Activity.objects.filter(user=user, is_deleted=False)
        .order_by("-start_date")
        .values_list("id", flat=True)[:10]
    )
    recent_total = len(recent_ids)
    recent_fully_synced = Activity.objects.filter(id__in=recent_ids, fully_synced=True).count() if recent_ids else 0
    full_sync_complete = bool((not sync_failed) and (recent_total == 0 or recent_fully_synced == recent_total))
    onboarding["sync_in_progress"] = False
    onboarding["full_sync_complete"] = full_sync_complete
    onboarding["last_full_sync_at"] = timezone.now().isoformat()
    onboarding["last_sync_result"] = {
        "fetched": fetched,
        "upserted": upserted,
        "new_activities": new_activities,
        "max_activities": max_activities,
        "import_from_date": import_from_date.isoformat() if import_from_date else None,
        "parsed_activities": parsed_activities,
        "selected_activities": selected_activities,
        "failed": sync_failed,
        "error": sync_error,
    }
    onboarding["recent_10_total"] = recent_total
    onboarding["recent_10_fully_synced"] = recent_fully_synced
    schedule["onboarding"] = onboarding
    profile.schedule = schedule
    profile.save(update_fields=["schedule"])
    if not sync_failed:
        generate_coach_tone_task.delay(user.id)
        refresh_weekly_artifacts_task.delay(user.id)
    return {
        'rate_limited': sync_error == "strava_rate_limited",
        'fetched': fetched,
        'upserted': upserted,
        'new_activities': new_activities,
        'failed': sync_failed,
        'error': sync_error,
        'max_activities': max_activities,
        'import_from_date': import_from_date.isoformat() if import_from_date else None,
        'parsed_activities': parsed_activities,
        'selected_activities': selected_activities,
        'full_sync_complete': full_sync_complete,
        'recent_10_total': recent_total,
        'recent_10_fully_synced': recent_fully_synced,
    }


def _hr_zones(heartrate, hr_zones=None):
    if not heartrate:
        return {}
    buckets = {"z1": 0, "z2": 0, "z3": 0, "z4": 0, "z5": 0}
    zones = hr_zones if isinstance(hr_zones, list) and hr_zones else None
    for hr in heartrate:
        if zones:
            found = False
            for idx, zone in enumerate(zones[:5]):
                zmin = zone.get('min', -10_000)
                zmax = zone.get('max')
                if zmax in (None, -1):
                    zmax = 10_000
                if hr >= zmin and hr <= zmax:
                    buckets[f'z{idx + 1}'] += 1
                    found = True
                    break
            if not found:
                buckets["z5"] += 1
            continue

        if hr < 120:
            buckets["z1"] += 1
        elif hr < 140:
            buckets["z2"] += 1
        elif hr < 160:
            buckets["z3"] += 1
        elif hr < 175:
            buckets["z4"] += 1
        else:
            buckets["z5"] += 1
    total = max(1, len(heartrate))
    return {k: round((v / total) * 100, 1) for k, v in buckets.items()}


def sync_streams_for_activity(user, activity, token):
    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    detail_url = f"https://www.strava.com/api/v3/activities/{activity.strava_activity_id}"
    detail_ok = False
    detail_resp = requests.get(detail_url, headers={'Authorization': f'Bearer {token}'}, params={'include_all_efforts': 'true'}, timeout=30)
    if detail_resp.ok:
        detail_ok = True
        detail = detail_resp.json()
        raw_payload = activity.raw_payload or {}
        raw_payload['description'] = detail.get('description')
        raw_payload['gear_id'] = detail.get('gear_id')
        raw_payload['average_temp'] = detail.get('average_temp')
        raw_payload['elev_high'] = detail.get('elev_high')
        raw_payload['elev_low'] = detail.get('elev_low')
        raw_payload['average_cadence'] = detail.get('average_cadence')
        raw_payload['average_watts'] = detail.get('average_watts')
        raw_payload['max_watts'] = detail.get('max_watts')
        raw_payload['weighted_average_watts'] = detail.get('weighted_average_watts')
        raw_payload['kilojoules'] = detail.get('kilojoules')
        raw_payload['kudos_count'] = detail.get('kudos_count', raw_payload.get('kudos_count', 0))
        raw_payload['comment_count'] = detail.get('comment_count', raw_payload.get('comment_count', 0))
        raw_payload['achievement_count'] = detail.get('achievement_count', raw_payload.get('achievement_count', 0))
        raw_payload['splits_metric'] = detail.get('splits_metric', raw_payload.get('splits_metric', []))
        raw_payload['splits_standard'] = detail.get('splits_standard', raw_payload.get('splits_standard', []))
        raw_payload['best_efforts'] = detail.get('best_efforts', raw_payload.get('best_efforts', []))
        raw_payload['segment_efforts'] = detail.get('segment_efforts', raw_payload.get('segment_efforts', []))
        raw_payload['highlighted_kudosers'] = detail.get('highlighted_kudosers', raw_payload.get('highlighted_kudosers', []))
        activity.raw_payload = raw_payload
        activity.description = detail.get('description') or activity.description
        activity.gear_id = detail.get('gear_id') or ''
        activity.average_temp = detail.get('average_temp')
        activity.elev_high = detail.get('elev_high')
        activity.elev_low = detail.get('elev_low')
        activity.average_cadence = detail.get('average_cadence')
        activity.average_watts = detail.get('average_watts')
        activity.max_watts = detail.get('max_watts')
        activity.weighted_average_watts = detail.get('weighted_average_watts')
        activity.kilojoules = detail.get('kilojoules')
        activity.kudos_count = int(detail.get('kudos_count') or activity.kudos_count or 0)
        activity.comment_count = int(detail.get('comment_count') or activity.comment_count or 0)
        activity.achievement_count = int(detail.get('achievement_count') or activity.achievement_count or 0)
        activity.avg_hr = detail.get('average_heartrate') if detail.get('average_heartrate') is not None else activity.avg_hr
        activity.max_hr = detail.get('max_heartrate') if detail.get('max_heartrate') is not None else activity.max_hr
        activity.calories = detail.get('calories') if detail.get('calories') is not None else activity.calories
        activity.detail_synced_at = timezone.now()
        activity.save(update_fields=[
            'raw_payload', 'description', 'gear_id', 'average_temp', 'elev_high', 'elev_low',
            'average_cadence', 'average_watts', 'max_watts', 'weighted_average_watts', 'kilojoules',
            'kudos_count', 'comment_count', 'achievement_count', 'avg_hr', 'max_hr', 'calories', 'detail_synced_at'
        ])
        try:
            update_personal_records_for_activity(
                user=user,
                activity=activity,
                best_efforts=detail.get('best_efforts') or [],
            )
        except Exception:
            pass

    stream_url = f"https://www.strava.com/api/v3/activities/{activity.strava_activity_id}/streams"
    params = {
        'keys': 'time,latlng,distance,altitude,velocity_smooth,heartrate,cadence,watts,temp,moving,grade_smooth',
        'key_by_type': 'true',
    }
    r = requests.get(stream_url, headers={'Authorization': f'Bearer {token}'}, params=params, timeout=30)
    if r.status_code in (401, 404):
        activity.fully_synced = False
        activity.sync_error = f"stream_http_{r.status_code}"
        activity.save(update_fields=['fully_synced', 'sync_error'])
        return
    r.raise_for_status()
    payload = r.json() or {}
    streams = {k: v.get('data', []) for k, v in payload.items() if isinstance(v, dict)}
    heartrate = streams.get('heartrate', [])
    distance = streams.get('distance', [])
    stream_types = sorted([k for k, v in streams.items() if isinstance(v, list) and v])
    sample_count = max([len(v) for v in streams.values() if isinstance(v, list)] or [0])

    ActivityStream.objects.update_or_create(
        activity=activity,
        defaults={
            'raw_streams': streams,
            'stream_types': stream_types,
            'sample_count': sample_count,
            'has_latlng': bool(streams.get('latlng')),
            'has_hr': bool(heartrate),
            'has_cadence': bool(streams.get('cadence')),
            'has_power': bool(streams.get('watts')),
            'has_temp': bool(streams.get('temp')),
            'has_velocity': bool(streams.get('velocity_smooth')),
            'has_grade': bool(streams.get('grade_smooth')),
            'has_moving': bool(streams.get('moving')),
        },
    )
    pace = None
    if distance and activity.moving_time_s and activity.distance_m:
        pace = activity.moving_time_s / max(1, (activity.distance_m / 1000))
    DerivedMetrics.objects.update_or_create(
        activity=activity,
        defaults={
            'avg_pace_sec_per_km': pace,
            'best_effort_estimates': {},
            'intensity_score': deterministic_metrics(activity).get('intensity_score', 0),
            'hr_zone_distribution': _hr_zones(heartrate, profile.hr_zones),
        },
    )
    activity.streams_synced_at = timezone.now()
    activity.fully_synced = bool(detail_ok)
    activity.sync_error = "" if detail_ok else "detail_sync_failed"
    try:
        highlighted = (activity.raw_payload or {}).get("highlighted_kudosers") or []
        has_highlighted_kudosers = bool(highlighted)
        has_highlighted_avatars = any(
            isinstance(k, dict) and (
                k.get("avatar_url")
                or k.get("profile")
                or k.get("profile_medium")
                or k.get("avatar")
                or k.get("picture")
            )
            for k in highlighted
        )
        # Small social preview for UI: who gave kudos.
        if (not has_highlighted_kudosers) or (not has_highlighted_avatars):
            kudos_resp = requests.get(
                f"https://www.strava.com/api/v3/activities/{activity.strava_activity_id}/kudos",
                headers={'Authorization': f'Bearer {token}'},
                params={'page': 1, 'per_page': 8},
                timeout=20,
            )
            if kudos_resp.ok:
                preview = []
                for athlete in (kudos_resp.json() or []):
                    if not isinstance(athlete, dict):
                        continue
                    preview.append(
                        {
                            "id": athlete.get("id"),
                            "firstname": athlete.get("firstname") or "",
                            "lastname": athlete.get("lastname") or "",
                            "avatar_url": athlete.get("avatar_url"),
                            "profile": athlete.get("profile") or athlete.get("avatar"),
                            "profile_medium": athlete.get("profile_medium") or athlete.get("picture"),
                        }
                    )
                payload = activity.raw_payload or {}
                payload["kudos_preview"] = preview
                activity.raw_payload = payload
    except Exception:
        pass
    activity.save(update_fields=['streams_synced_at', 'fully_synced', 'sync_error', 'raw_payload'])


@shared_task
def generate_note_task(activity_id, user_id):
    # Legacy endpoint compatibility: now delegates to v2 activity reaction flow.
    generate_activity_reaction_task.delay(activity_id, user_id)
    activity = Activity.objects.get(id=activity_id)
    metrics = deterministic_metrics(activity)
    send_activity_notification.delay(activity.id, metrics)


@shared_task
def send_activity_notification(activity_id, metrics):
    activity = Activity.objects.get(id=activity_id)
    s, _ = NotificationSettings.objects.get_or_create(user=activity.user)
    url = f"{os.getenv('APP_BASE_URL', 'http://localhost:5173')}/activities/{activity.id}"
    lines = [f"{activity.start_date.date()} {activity.type}", f"Distance: {activity.distance_m/1000:.2f} km", f"Time: {activity.moving_time_s//60} min", f"Intensity: {metrics['intensity_score']:.1f}", url]
    msg = '\n'.join(lines)
    if s.email_enabled and s.email_address and os.getenv('SMTP_HOST'):
        send_mail(f"PacePilot – New workout analyzed: {activity.name}", msg, os.getenv('SMTP_FROM', 'noreply@pacepilot.local'), [s.email_address], fail_silently=True)
    if s.telegram_enabled and s.telegram_chat_id and os.getenv('TELEGRAM_BOT_TOKEN'):
        requests.post(f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage", json={'chat_id': s.telegram_chat_id, 'text': msg}, timeout=20)


@shared_task
def send_test_email_task(user_id):
    s = NotificationSettings.objects.get(user_id=user_id)
    if s.email_address:
        send_mail('PacePilot test', 'Test message', os.getenv('SMTP_FROM', 'noreply@pacepilot.local'), [s.email_address], fail_silently=True)


@shared_task
def send_test_telegram_task(user_id):
    s = NotificationSettings.objects.get(user_id=user_id)
    if s.telegram_chat_id and os.getenv('TELEGRAM_BOT_TOKEN'):
        requests.post(f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage", json={'chat_id': s.telegram_chat_id, 'text': 'PacePilot test message'}, timeout=20)
