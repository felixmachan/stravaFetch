import datetime as dt

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from pydantic import ValidationError

from core.models import Activity
from core.services.ai.context import relevant_workouts, workouts_in_lookback
from core.services.ai.schemas import WeeklyPlanOutput


class AISchemaValidationTests(TestCase):
    def test_weekly_plan_schema_validation(self):
        payload = {
            "week_start_date": "2026-02-23",
            "plan": [
                {
                    "date": "2026-02-23",
                    "type": "easy",
                    "duration_min": 45,
                    "distance_km": 8.0,
                    "intensity_notes": "Easy aerobic",
                    "main_set": "Steady effort",
                    "warmup_cooldown": "10 min easy",
                    "coach_note": "Stay relaxed.",
                }
            ],
            "weekly_targets": {
                "total_distance_km": 40.0,
                "total_duration_min": 260,
                "hard_sessions": 2,
                "focus": "Consistency",
            },
            "risk_notes": [],
        }
        parsed = WeeklyPlanOutput.model_validate(payload)
        self.assertEqual(parsed.week_start_date, "2026-02-23")

    def test_weekly_plan_schema_rejects_missing_required(self):
        with self.assertRaises(ValidationError):
            WeeklyPlanOutput.model_validate({"week_start_date": "2026-02-23"})


class AILookbackAndRetrievalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ai_tester", password="pw")

    def _create_activity(self, *, days_ago: int, name: str, type_: str = "Run", distance_km: float = 8.0, duration_min: int = 45, avg_hr: int | None = 145):
        start = timezone.now() - dt.timedelta(days=days_ago)
        return Activity.objects.create(
            user=self.user,
            strava_activity_id=1_000_000 + days_ago + int(distance_km * 10),
            type=type_,
            name=name,
            start_date=start,
            distance_m=distance_km * 1000,
            moving_time_s=duration_min * 60,
            elapsed_time_s=duration_min * 60,
            avg_hr=avg_hr,
        )

    def test_lookback_days_filters_old_workouts(self):
        recent = self._create_activity(days_ago=5, name="Recent easy")
        self._create_activity(days_ago=20, name="Old run")

        results = workouts_in_lookback(self.user, 15)
        ids = {a.id for a in results}
        self.assertIn(recent.id, ids)
        self.assertEqual(len(ids), 1)

    def test_relevant_workouts_selection(self):
        a_recent_1 = self._create_activity(days_ago=1, name="Easy run", distance_km=8, avg_hr=138)
        a_recent_2 = self._create_activity(days_ago=2, name="Steady run", distance_km=9, avg_hr=142)
        a_recent_3 = self._create_activity(days_ago=3, name="Recovery run", distance_km=6, avg_hr=132)
        a_long = self._create_activity(days_ago=6, name="Long run", distance_km=18, avg_hr=146)
        a_hard = self._create_activity(days_ago=4, name="Interval session", distance_km=10, avg_hr=162)

        selected = relevant_workouts(workouts_in_lookback(self.user, 15))
        selected_ids = {row["id"] for row in selected}

        self.assertIn(a_recent_1.id, selected_ids)
        self.assertIn(a_recent_2.id, selected_ids)
        self.assertIn(a_recent_3.id, selected_ids)
        self.assertIn(a_long.id, selected_ids)
        self.assertIn(a_hard.id, selected_ids)
        self.assertLessEqual(len(selected), 7)
