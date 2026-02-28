from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_rename_core_planned_user_id_bf7d26_idx_core_planne_user_id_a8097f_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="achievement_count",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="activity",
            name="average_cadence",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="average_temp",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="average_watts",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="comment_count",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="activity",
            name="commute",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="activity",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="detail_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="device_name",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="activity",
            name="elev_high",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="elev_low",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="fully_synced",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="activity",
            name="gear_id",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="activity",
            name="kilojoules",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="kudos_count",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="activity",
            name="manual",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="activity",
            name="max_watts",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="sport_type",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="activity",
            name="start_date_local",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="streams_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="sync_error",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="activity",
            name="timezone_name",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="activity",
            name="trainer",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="activity",
            name="weighted_average_watts",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activitystream",
            name="has_grade",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="activitystream",
            name="has_moving",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="activitystream",
            name="has_power",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="activitystream",
            name="has_temp",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="activitystream",
            name="has_velocity",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="activitystream",
            name="sample_count",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="activitystream",
            name="stream_types",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
