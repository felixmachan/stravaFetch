from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_rename_core_aifeat_user_id_fa97db_idx_core_aifeat_user_id_c04eb3_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlannedWorkout",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("week_start", models.DateField()),
                ("week_end", models.DateField()),
                ("planned_date", models.DateField()),
                ("sport", models.CharField(default="run", max_length=32)),
                ("duration_min", models.IntegerField(default=0)),
                ("distance_km", models.FloatField(blank=True, null=True)),
                ("hr_zone", models.CharField(blank=True, max_length=16)),
                ("title", models.CharField(blank=True, max_length=255)),
                ("workout_type", models.CharField(blank=True, max_length=64)),
                ("coach_notes", models.TextField(blank=True)),
                ("status", models.CharField(default="planned", max_length=16)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("source", models.CharField(default="plan_json", max_length=32)),
                ("meta_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("training_plan", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.trainingplan")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "unique_together": {("user", "week_start", "planned_date", "sort_order")},
            },
        ),
        migrations.AddIndex(
            model_name="plannedworkout",
            index=models.Index(fields=["user", "week_start", "planned_date"], name="core_planned_user_id_bf7d26_idx"),
        ),
        migrations.AddIndex(
            model_name="plannedworkout",
            index=models.Index(fields=["user", "planned_date", "status"], name="core_planned_user_id_b6cb17_idx"),
        ),
    ]
