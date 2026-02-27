from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_athleteprofile_hr_zones"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramConnection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telegram_chat_id", models.CharField(blank=True, max_length=64)),
                ("telegram_user_id", models.CharField(blank=True, max_length=64)),
                ("telegram_username", models.CharField(blank=True, max_length=128)),
                ("setup_code", models.CharField(blank=True, max_length=32)),
                ("setup_code_expires_at", models.DateTimeField(blank=True, null=True)),
                ("last_update_id", models.BigIntegerField(default=0)),
                ("connected_at", models.DateTimeField(blank=True, null=True)),
                ("last_verified_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
