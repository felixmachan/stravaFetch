from django.conf import settings
from django.db import models


class AthleteProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    goals = models.CharField(max_length=255, blank=True)
    schedule = models.JSONField(default=dict, blank=True)
    constraints = models.TextField(blank=True)
    injury_notes = models.TextField(blank=True)
    experience_level = models.CharField(max_length=64, blank=True)
    preferred_sports = models.JSONField(default=list, blank=True)
    weekly_target_hours = models.FloatField(default=0)


class StravaConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    athlete_id = models.BigIntegerField(unique=True)
    access_token = models.TextField()
    refresh_token = models.TextField()
    expires_at = models.DateTimeField()
    scopes = models.JSONField(default=list, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_polled_at = models.DateTimeField(null=True, blank=True)


class Activity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    strava_activity_id = models.BigIntegerField(unique=True)
    type = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    start_date = models.DateTimeField()
    distance_m = models.FloatField(default=0)
    moving_time_s = models.IntegerField(default=0)
    elapsed_time_s = models.IntegerField(default=0)
    total_elevation_gain_m = models.FloatField(default=0)
    average_speed_mps = models.FloatField(default=0)
    max_speed_mps = models.FloatField(default=0)
    avg_hr = models.FloatField(null=True, blank=True)
    max_hr = models.FloatField(null=True, blank=True)
    calories = models.FloatField(null=True, blank=True)
    suffer_score = models.FloatField(null=True, blank=True)
    map_summary_polyline = models.TextField(null=True, blank=True)
    raw_payload = models.JSONField(default=dict)
    is_deleted = models.BooleanField(default=False)


class ActivityStream(models.Model):
    activity = models.OneToOneField(Activity, on_delete=models.CASCADE)
    raw_streams = models.JSONField(default=dict)
    has_latlng = models.BooleanField(default=False)
    has_hr = models.BooleanField(default=False)
    has_cadence = models.BooleanField(default=False)


class DerivedMetrics(models.Model):
    activity = models.OneToOneField(Activity, on_delete=models.CASCADE)
    avg_pace_sec_per_km = models.FloatField(null=True, blank=True)
    best_effort_estimates = models.JSONField(default=dict)
    intensity_score = models.FloatField(default=0)
    hr_zone_distribution = models.JSONField(default=dict)


class CoachNote(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE)
    model = models.CharField(max_length=64)
    prompt_version = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    json_output = models.JSONField(default=dict)
    text_summary = models.TextField()
    tokens_used = models.IntegerField(null=True, blank=True)
    cost_usd_estimate = models.FloatField(null=True, blank=True)


class TrainingPlan(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=32, default='active')
    start_date = models.DateField()
    end_date = models.DateField()
    plan_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class NotificationSettings(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    email_enabled = models.BooleanField(default=False)
    telegram_enabled = models.BooleanField(default=False)
    email_address = models.EmailField(blank=True)
    telegram_chat_id = models.CharField(max_length=64, blank=True)
    daily_summary_enabled = models.BooleanField(default=False)
    weekly_summary_enabled = models.BooleanField(default=False)
