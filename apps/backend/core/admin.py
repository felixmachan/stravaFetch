from django.contrib import admin
from .models import AthleteProfile, StravaConnection, Activity, ActivityStream, DerivedMetrics, CoachNote, TrainingPlan, NotificationSettings

for model in [AthleteProfile, StravaConnection, Activity, ActivityStream, DerivedMetrics, CoachNote, TrainingPlan, NotificationSettings]:
    admin.site.register(model)
