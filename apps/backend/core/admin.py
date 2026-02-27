from django.contrib import admin
from .models import AthleteProfile, StravaConnection, Activity, ActivityStream, DerivedMetrics, CoachNote, TrainingPlan, NotificationSettings, TelegramConnection, AIInteraction

for model in [AthleteProfile, StravaConnection, Activity, ActivityStream, DerivedMetrics, CoachNote, TrainingPlan, NotificationSettings, TelegramConnection, AIInteraction]:
    admin.site.register(model)
