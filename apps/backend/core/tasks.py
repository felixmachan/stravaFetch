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
from .services.strava import refresh_if_needed, sync_athlete_profile_from_connection


@shared_task
def poll_strava_activities():
    for conn in StravaConnection.objects.select_related('user').all():
        sync_now_for_user.delay(conn.user_id)


@shared_task
def generate_weekly_plan_sunday():
    # Runs from beat schedule; creates/refreshes next week plans for opted-in users.
    for profile in AthleteProfile.objects.select_related("user").all():
        schedule = profile.schedule or {}
        ai_settings = schedule.get("ai_settings") or {}
        if ai_settings.get("weekly_plan_enabled", True):
            generate_weekly_plan_task.delay(profile.user_id, False)


@shared_task
def generate_weekly_plan_task(user_id, force=False):
    user = User.objects.get(id=user_id)
    return generate_weekly_plan_service(user, force=bool(force))


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
    result = generate_activity_reaction_service(user, activity)
    refresh_weekly_artifacts_task.delay(user.id)
    return result


@shared_task
def sync_now_for_user(user_id):
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
    # Always perform full history sync from Strava.
    after = 0

    fetched = 0
    upserted = 0
    new_activities = 0
    reaction_cutoff = timezone.now() - dt.timedelta(days=10)
    page = 1
    per_page = 100
    while True:
        r = requests.get(
            'https://www.strava.com/api/v3/athlete/activities',
            headers={'Authorization': f'Bearer {token}'},
            params={'after': after, 'per_page': per_page, 'page': page},
            timeout=30,
        )
        if r.status_code == 429:
            return {'rate_limited': True, 'fetched': fetched, 'upserted': upserted}
        r.raise_for_status()
        items = r.json()
        if not items:
            break

        fetched += len(items)
        for a in items:
            obj, created = Activity.objects.update_or_create(strava_activity_id=a['id'], defaults={
                'user': user, 'type': a.get('type', 'Other'), 'name': a.get('name', 'Activity'),
                'start_date': a['start_date'], 'distance_m': a.get('distance', 0), 'moving_time_s': a.get('moving_time', 0),
                'elapsed_time_s': a.get('elapsed_time', 0), 'total_elevation_gain_m': a.get('total_elevation_gain', 0),
                'average_speed_mps': a.get('average_speed', 0), 'max_speed_mps': a.get('max_speed', 0),
                'avg_hr': a.get('average_heartrate'), 'max_hr': a.get('max_heartrate'), 'calories': a.get('calories'),
                'suffer_score': a.get('suffer_score'), 'map_summary_polyline': a.get('map', {}).get('summary_polyline'), 'raw_payload': a,
            })
            sync_streams_for_activity(user, obj, token)
            upserted += 1
            if created:
                new_activities += 1
                if obj.start_date >= reaction_cutoff:
                    generate_activity_reaction_task.delay(obj.id, user.id)

        if len(items) < per_page:
            break
        page += 1

    conn.last_sync_at = timezone.now()
    conn.last_polled_at = timezone.now()
    conn.save(update_fields=['last_sync_at', 'last_polled_at'])

    # Ensure last 10 days are fully covered by AI reactions, not only newly created rows.
    cutoff_recent = timezone.now() - dt.timedelta(days=10)
    recent_ids = list(
        Activity.objects.filter(user=user, is_deleted=False, start_date__gte=cutoff_recent).values_list("id", flat=True)
    )
    noted_ids = set(
        CoachNote.objects.filter(activity_id__in=recent_ids).values_list("activity_id", flat=True).distinct()
    ) if recent_ids else set()
    for aid in recent_ids:
        if aid not in noted_ids:
            generate_activity_reaction_task.delay(aid, user.id)

    profile, _ = AthleteProfile.objects.get_or_create(user=user)
    schedule = profile.schedule or {}
    onboarding = schedule.get("onboarding", {})
    onboarding["sync_in_progress"] = False
    onboarding["full_sync_complete"] = True
    onboarding["last_full_sync_at"] = timezone.now().isoformat()
    onboarding["last_sync_result"] = {
        "fetched": fetched,
        "upserted": upserted,
        "new_activities": new_activities,
    }
    schedule["onboarding"] = onboarding
    profile.schedule = schedule
    profile.save(update_fields=["schedule"])
    if new_activities > 0:
        generate_coach_tone_task.delay(user.id)
        refresh_weekly_artifacts_task.delay(user.id)
    return {'rate_limited': False, 'fetched': fetched, 'upserted': upserted, 'new_activities': new_activities}


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
    detail_resp = requests.get(detail_url, headers={'Authorization': f'Bearer {token}'}, params={'include_all_efforts': 'false'}, timeout=30)
    if detail_resp.ok:
        detail = detail_resp.json()
        raw_payload = activity.raw_payload or {}
        raw_payload['splits_metric'] = detail.get('splits_metric', raw_payload.get('splits_metric', []))
        raw_payload['splits_standard'] = detail.get('splits_standard', raw_payload.get('splits_standard', []))
        activity.raw_payload = raw_payload
        activity.save(update_fields=['raw_payload'])

    stream_url = f"https://www.strava.com/api/v3/activities/{activity.strava_activity_id}/streams"
    params = {
        'keys': 'time,distance,heartrate,altitude,latlng,cadence',
        'key_by_type': 'true',
    }
    r = requests.get(stream_url, headers={'Authorization': f'Bearer {token}'}, params=params, timeout=30)
    if r.status_code in (401, 404):
        return
    r.raise_for_status()
    payload = r.json() or {}
    streams = {k: v.get('data', []) for k, v in payload.items() if isinstance(v, dict)}
    heartrate = streams.get('heartrate', [])
    distance = streams.get('distance', [])

    ActivityStream.objects.update_or_create(
        activity=activity,
        defaults={
            'raw_streams': streams,
            'has_latlng': bool(streams.get('latlng')),
            'has_hr': bool(heartrate),
            'has_cadence': bool(streams.get('cadence')),
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
