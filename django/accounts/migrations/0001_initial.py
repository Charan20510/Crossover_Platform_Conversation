"""
State-only adoption of the Account model into the accounts app.

Zero DDL: db_table stays "api_account" (already created by
api/migrations/0001_initial.py), so this migration only rewrites Django's
migration state, never the database.
"""

import secrets
import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("api", "0027_alter_device_device_token_mailaccount_email_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="Account",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("name", models.CharField(max_length=255)),
                        ("email", models.EmailField(max_length=254, unique=True)),
                        ("account_token", models.CharField(default=secrets.token_urlsafe, max_length=64, unique=True)),
                        ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                        ("user", models.OneToOneField(
                            blank=True, null=True,
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name="account", to=settings.AUTH_USER_MODEL,
                        )),
                    ],
                    options={"db_table": "api_account"},
                ),
            ],
        ),
    ]
