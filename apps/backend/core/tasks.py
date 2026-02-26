import datetime as dt
import os
import requests
from celery import shared_task
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.utils import timezone
from .models import Activity, AthleteProfile, CoachNote, NotificationSettings, StravaConnection
from .services.coaching_engine import deterministic_metrics, generate_coach_json
from .services.strava import refresh_if_needed


@shared_task
def poll_strava_activities():
    for conn in StravaConnection.objects.select_related('user').all():
        sync_now_for_user.delay(conn.user_id)


@shared_task
def sync_now_for_user(user_id):
    user = User.objects.get(id=user_id)
    conn = StravaConnection.objects.get(user=user)
    token = refresh_if_needed(conn)
    after = int((conn.last_sync_at or (timezone.now() - dt.timedelta(days=int(os.getenv('STRAVA_INITIAL_SYNC_DAYS', '30'))))).timestamp())
    r = requests.get('https://www.strava.com/api/v3/athlete/activities', headers={'Authorization': f'Bearer {token}'}, params={'after': after, 'per_page': 50}, timeout=30)
    if r.status_code == 429:
        return
    r.raise_for_status()
    for a in r.json():
        obj, _ = Activity.objects.update_or_create(strava_activity_id=a['id'], defaults={
            'user': user, 'type': a.get('type', 'Other'), 'name': a.get('name', 'Activity'),
            'start_date': a['start_date'], 'distance_m': a.get('distance', 0), 'moving_time_s': a.get('moving_time', 0),
            'elapsed_time_s': a.get('elapsed_time', 0), 'total_elevation_gain_m': a.get('total_elevation_gain', 0),
            'average_speed_mps': a.get('average_speed', 0), 'max_speed_mps': a.get('max_speed', 0),
            'avg_hr': a.get('average_heartrate'), 'max_hr': a.get('max_heartrate'), 'calories': a.get('calories'),
            'suffer_score': a.get('suffer_score'), 'map_summary_polyline': a.get('map', {}).get('summary_polyline'), 'raw_payload': a,
        })
        generate_note_task.delay(obj.id, user.id)
    conn.last_sync_at = timezone.now()
    conn.last_polled_at = timezone.now()
    conn.save(update_fields=['last_sync_at', 'last_polled_at'])


@shared_task
def generate_note_task(activity_id, user_id):
    activity = Activity.objects.get(id=activity_id)
    profile, _ = AthleteProfile.objects.get_or_create(user_id=user_id)
    metrics = deterministic_metrics(activity)
    payload = generate_coach_json(activity, profile)
    CoachNote.objects.create(activity=activity, model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini'), prompt_version='v1_workout_review', json_output=payload, text_summary=payload['summary'])
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
