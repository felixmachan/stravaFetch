from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_activity_extended_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonalRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("effort_key", models.CharField(max_length=96)),
                ("effort_label", models.CharField(max_length=128)),
                ("distance_m", models.FloatField(blank=True, null=True)),
                ("rank", models.PositiveSmallIntegerField(default=1)),
                ("elapsed_time_s", models.PositiveIntegerField()),
                ("achieved_at", models.DateTimeField(blank=True, null=True)),
                ("source_strava_activity_id", models.BigIntegerField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_activity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.activity")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "unique_together": {("user", "effort_key", "rank")},
            },
        ),
        migrations.AddIndex(
            model_name="personalrecord",
            index=models.Index(fields=["user", "effort_key", "rank"], name="core_persona_user_id_0771e6_idx"),
        ),
        migrations.AddIndex(
            model_name="personalrecord",
            index=models.Index(fields=["user", "updated_at"], name="core_persona_user_id_8e7dbf_idx"),
        ),
    ]
