from django.conf import settings
from django.db import models


class AthleteProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    display_name = models.CharField(max_length=128, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    height_cm = models.FloatField(null=True, blank=True)
    weight_kg = models.FloatField(null=True, blank=True)
    primary_sport = models.CharField(max_length=32, blank=True)
    current_race_pace = models.CharField(max_length=32, blank=True)
    goal_race_pace = models.CharField(max_length=32, blank=True)
    goal_event_name = models.CharField(max_length=128, blank=True)
    goal_event_date = models.DateField(null=True, blank=True)
    goals = models.CharField(max_length=255, blank=True)
    schedule = models.JSONField(default=dict, blank=True)
    constraints = models.TextField(blank=True)
    injury_notes = models.TextField(blank=True)
    experience_level = models.CharField(max_length=64, blank=True)
    preferred_sports = models.JSONField(default=list, blank=True)
    weekly_target_hours = models.FloatField(default=0)
    hr_zones = models.JSONField(default=list, blank=True)


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


class TelegramConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    telegram_chat_id = models.CharField(max_length=64, blank=True)
    telegram_user_id = models.CharField(max_length=64, blank=True)
    telegram_username = models.CharField(max_length=128, blank=True)
    setup_code = models.CharField(max_length=32, blank=True)
    setup_code_expires_at = models.DateTimeField(null=True, blank=True)
    last_update_id = models.BigIntegerField(default=0)
    connected_at = models.DateTimeField(null=True, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AIInteraction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    mode = models.CharField(max_length=64)
    source = models.CharField(max_length=32, default="unknown")
    model = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=32, default="success")
    error_message = models.TextField(blank=True)
    max_chars = models.IntegerField(default=160)
    response_text = models.TextField(blank=True)
    prompt_system = models.TextField(blank=True)
    prompt_user = models.TextField(blank=True)
    prompt_messages_json = models.JSONField(default=list, blank=True)
    context_snapshot_json = models.JSONField(default=dict, blank=True)
    context_hash = models.CharField(max_length=64, blank=True)
    request_params_json = models.JSONField(default=dict, blank=True)
    related_activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL)
    related_training_plan = models.ForeignKey(TrainingPlan, null=True, blank=True, on_delete=models.SET_NULL)
    tokens_input = models.IntegerField(null=True, blank=True)
    tokens_output = models.IntegerField(null=True, blank=True)
    cost_estimate = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
