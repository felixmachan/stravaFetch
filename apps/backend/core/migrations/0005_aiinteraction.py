from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_telegramconnection"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIInteraction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(max_length=64)),
                ("source", models.CharField(default="unknown", max_length=32)),
                ("model", models.CharField(blank=True, max_length=64)),
                ("status", models.CharField(default="success", max_length=32)),
                ("error_message", models.TextField(blank=True)),
                ("max_chars", models.IntegerField(default=160)),
                ("response_text", models.TextField(blank=True)),
                ("prompt_system", models.TextField(blank=True)),
                ("prompt_user", models.TextField(blank=True)),
                ("prompt_messages_json", models.JSONField(blank=True, default=list)),
                ("context_snapshot_json", models.JSONField(blank=True, default=dict)),
                ("context_hash", models.CharField(blank=True, max_length=64)),
                ("request_params_json", models.JSONField(blank=True, default=dict)),
                ("tokens_input", models.IntegerField(blank=True, null=True)),
                ("tokens_output", models.IntegerField(blank=True, null=True)),
                ("cost_estimate", models.FloatField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("related_activity", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.activity")),
                ("related_training_plan", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.trainingplan")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
