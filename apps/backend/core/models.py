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
    sport_type = models.CharField(max_length=32, blank=True)
    name = models.CharField(max_length=255)
    start_date = models.DateTimeField()
    start_date_local = models.DateTimeField(null=True, blank=True)
    timezone_name = models.CharField(max_length=64, blank=True)
    distance_m = models.FloatField(default=0)
    moving_time_s = models.IntegerField(default=0)
    elapsed_time_s = models.IntegerField(default=0)
    total_elevation_gain_m = models.FloatField(default=0)
    average_speed_mps = models.FloatField(default=0)
    max_speed_mps = models.FloatField(default=0)
    average_cadence = models.FloatField(null=True, blank=True)
    average_watts = models.FloatField(null=True, blank=True)
    weighted_average_watts = models.FloatField(null=True, blank=True)
    max_watts = models.FloatField(null=True, blank=True)
    kilojoules = models.FloatField(null=True, blank=True)
    avg_hr = models.FloatField(null=True, blank=True)
    max_hr = models.FloatField(null=True, blank=True)
    calories = models.FloatField(null=True, blank=True)
    suffer_score = models.FloatField(null=True, blank=True)
    description = models.TextField(blank=True)
    device_name = models.CharField(max_length=128, blank=True)
    trainer = models.BooleanField(default=False)
    commute = models.BooleanField(default=False)
    manual = models.BooleanField(default=False)
    average_temp = models.FloatField(null=True, blank=True)
    elev_high = models.FloatField(null=True, blank=True)
    elev_low = models.FloatField(null=True, blank=True)
    achievement_count = models.IntegerField(default=0)
    kudos_count = models.IntegerField(default=0)
    comment_count = models.IntegerField(default=0)
    gear_id = models.CharField(max_length=64, blank=True)
    detail_synced_at = models.DateTimeField(null=True, blank=True)
    streams_synced_at = models.DateTimeField(null=True, blank=True)
    fully_synced = models.BooleanField(default=False)
    sync_error = models.CharField(max_length=255, blank=True)
    map_summary_polyline = models.TextField(null=True, blank=True)
    raw_payload = models.JSONField(default=dict)
    is_deleted = models.BooleanField(default=False)


class ActivityStream(models.Model):
    activity = models.OneToOneField(Activity, on_delete=models.CASCADE)
    raw_streams = models.JSONField(default=dict)
    stream_types = models.JSONField(default=list, blank=True)
    sample_count = models.IntegerField(default=0)
    has_latlng = models.BooleanField(default=False)
    has_hr = models.BooleanField(default=False)
    has_cadence = models.BooleanField(default=False)
    has_power = models.BooleanField(default=False)
    has_temp = models.BooleanField(default=False)
    has_velocity = models.BooleanField(default=False)
    has_grade = models.BooleanField(default=False)
    has_moving = models.BooleanField(default=False)


class DerivedMetrics(models.Model):
    activity = models.OneToOneField(Activity, on_delete=models.CASCADE)
    avg_pace_sec_per_km = models.FloatField(null=True, blank=True)
    best_effort_estimates = models.JSONField(default=dict)
    intensity_score = models.FloatField(default=0)
    hr_zone_distribution = models.JSONField(default=dict)


class PersonalRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    effort_key = models.CharField(max_length=96)
    effort_label = models.CharField(max_length=128)
    distance_m = models.FloatField(null=True, blank=True)
    rank = models.PositiveSmallIntegerField(default=1)
    elapsed_time_s = models.PositiveIntegerField()
    achieved_at = models.DateTimeField(null=True, blank=True)
    source_activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL)
    source_strava_activity_id = models.BigIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "effort_key", "rank")
        indexes = [
            models.Index(fields=["user", "effort_key", "rank"]),
            models.Index(fields=["user", "updated_at"]),
        ]


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


class PlannedWorkout(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    training_plan = models.ForeignKey(TrainingPlan, null=True, blank=True, on_delete=models.SET_NULL)
    week_start = models.DateField()
    week_end = models.DateField()
    planned_date = models.DateField()
    sport = models.CharField(max_length=32, default="run")
    duration_min = models.IntegerField(default=0)
    distance_km = models.FloatField(null=True, blank=True)
    hr_zone = models.CharField(max_length=16, blank=True)
    title = models.CharField(max_length=255, blank=True)
    workout_type = models.CharField(max_length=64, blank=True)
    coach_notes = models.TextField(blank=True)
    status = models.CharField(max_length=16, default="planned")
    sort_order = models.PositiveIntegerField(default=0)
    source = models.CharField(max_length=32, default="plan_json")
    meta_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "week_start", "planned_date", "sort_order")
        indexes = [
            models.Index(fields=["user", "week_start", "planned_date"]),
            models.Index(fields=["user", "planned_date", "status"]),
        ]


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


class AIChatSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
        ]


class AIChatMessage(models.Model):
    session = models.ForeignKey(AIChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16)  # user | assistant
    content = models.TextField(blank=True)
    source = models.CharField(max_length=32, blank=True)
    model = models.CharField(max_length=64, blank=True)
    interaction = models.ForeignKey(AIInteraction, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["session", "created_at"]),
            models.Index(fields=["role"]),
        ]


class AIFeatureCache(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    feature = models.CharField(max_length=64)
    cache_key = models.CharField(max_length=255)
    input_hash = models.CharField(max_length=64, blank=True)
    payload_json = models.JSONField(default=dict, blank=True)
    model = models.CharField(max_length=64, blank=True)
    tokens_input = models.IntegerField(null=True, blank=True)
    tokens_output = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "feature", "cache_key")
        indexes = [
            models.Index(fields=["user", "feature", "cache_key"]),
            models.Index(fields=["updated_at"]),
        ]
