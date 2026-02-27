from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_athleteprofile_onboarding_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="athleteprofile",
            name="hr_zones",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
