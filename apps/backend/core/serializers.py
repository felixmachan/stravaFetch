from rest_framework import serializers
from .models import Activity, AthleteProfile, NotificationSettings, TrainingPlan, CoachNote


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = '__all__'


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AthleteProfile
        exclude = ('user',)


class IntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationSettings
        exclude = ('user',)


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingPlan
        exclude = ('user',)


class CoachNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoachNote
        fields = '__all__'
