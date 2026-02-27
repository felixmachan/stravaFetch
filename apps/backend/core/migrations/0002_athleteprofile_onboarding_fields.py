from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="athleteprofile",
            name="age",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="athleteprofile",
            name="current_race_pace",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="athleteprofile",
            name="display_name",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="athleteprofile",
            name="goal_event_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="athleteprofile",
            name="goal_event_name",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="athleteprofile",
            name="goal_race_pace",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="athleteprofile",
            name="height_cm",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="athleteprofile",
            name="primary_sport",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="athleteprofile",
            name="weight_kg",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
