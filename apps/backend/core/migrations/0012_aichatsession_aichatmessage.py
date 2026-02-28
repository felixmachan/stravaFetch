from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_personalrecord"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIChatSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [models.Index(fields=["user", "-updated_at"], name="core_aichat_user_id_c6253e_idx")],
            },
        ),
        migrations.CreateModel(
            name="AIChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(max_length=16)),
                ("content", models.TextField(blank=True)),
                ("source", models.CharField(blank=True, max_length=32)),
                ("model", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "interaction",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.aiinteraction"),
                ),
                (
                    "session",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="core.aichatsession"),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["session", "created_at"], name="core_aichat_sessio_6f9138_idx"),
                    models.Index(fields=["role"], name="core_aichat_role_8ccdb5_idx"),
                ],
            },
        ),
    ]
