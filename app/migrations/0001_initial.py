# Generated by Django 5.1.6 on 2025-02-07 20:21

import app
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Settings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("key", models.CharField(max_length=255)),
                ("value", models.TextField()),
            ],
        ),
        migrations.CreateModel(
            name="Thread",
            fields=[
                (
                    "id",
                    app.KSUIDField(
                        max_length=27, primary_key=True, serialize=False, unique=True
                    ),
                ),
                ("thread_name", models.CharField(max_length=255)),
                ("state", models.CharField(default="idle", max_length=255)),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                ("edited_on", models.DateTimeField(auto_now=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
        ),
        migrations.CreateModel(
            name="Log",
            fields=[
                (
                    "id",
                    app.KSUIDField(
                        max_length=27, primary_key=True, serialize=False, unique=True
                    ),
                ),
                ("sender", models.CharField(max_length=255)),
                ("type", models.CharField(max_length=100)),
                ("payload", models.TextField()),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                ("edited_on", models.DateTimeField(auto_now=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "thread",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logs",
                        to="app.thread",
                    ),
                ),
            ],
        ),
    ]
