from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_aiinteraction"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIFeatureCache",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("feature", models.CharField(max_length=64)),
                ("cache_key", models.CharField(max_length=255)),
                ("input_hash", models.CharField(blank=True, max_length=64)),
                ("payload_json", models.JSONField(blank=True, default=dict)),
                ("model", models.CharField(blank=True, max_length=64)),
                ("tokens_input", models.IntegerField(blank=True, null=True)),
                ("tokens_output", models.IntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={
                "unique_together": {("user", "feature", "cache_key")},
            },
        ),
        migrations.AddIndex(
            model_name="aifeaturecache",
            index=models.Index(fields=["user", "feature", "cache_key"], name="core_aifeat_user_id_fa97db_idx"),
        ),
        migrations.AddIndex(
            model_name="aifeaturecache",
            index=models.Index(fields=["updated_at"], name="core_aifeat_updated_47a448_idx"),
        ),
    ]
