
import secrets
import uuid
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("api", "0027_alter_device_device_token_mailaccount_email_and_more"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="Device",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("device_token", models.CharField(default=secrets.token_urlsafe, max_length=64, unique=True)),
                        ("name", models.CharField(max_length=30)),
                        ("phone_number", models.CharField(max_length=15, unique=True)),
                        ("status", models.CharField(choices=[("connect", "Connected"), ("disconnect", "Disconnected")], default="disconnect", max_length=10)),
                        ("package", models.CharField(choices=[("free", "Free"), ("regular", "Regular"), ("regular_pro", "Regular Pro"), ("master", "Master"), ("super", "Super"), ("advanced", "Advanced"), ("ultra", "Ultra")], default="free", max_length=15)),
                        ("quota", models.IntegerField(default=1000)),
                        ("messages_sent", models.IntegerField(default=0)),
                        ("webhook_url", models.URLField(blank=True, null=True)),
                        ("autoread", models.BooleanField(default=False)),
                        ("expires_at", models.DateTimeField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                        ("account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="devices", to="accounts.account")),
                    ],
                    options={"db_table": "api_device"},
                ),
                migrations.CreateModel(
                    name="Contact",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("phone", models.CharField(max_length=20)),
                        ("name", models.CharField(blank=True, max_length=255)),
                        ("extra_data", models.JSONField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                        ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contacts", to="whatsapp.device")),
                    ],
                    options={"db_table": "api_contact", "unique_together": {("device", "phone")}},
                ),
                migrations.CreateModel(
                    name="Message",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("target", models.CharField(max_length=20)),
                        ("body", models.TextField()),
                        ("status", models.CharField(choices=[("process", "Processing"), ("pending", "Pending / Scheduled"), ("sent", "Sent"), ("delivered", "Delivered"), ("read", "Read"), ("failed", "Failed")], default="process", max_length=10)),
                        ("state", models.CharField(blank=True, max_length=20, null=True)),
                        ("whatsapp_id", models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                        ("scheduled_at", models.DateTimeField(blank=True, null=True)),
                        ("sent_at", models.DateTimeField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                        ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="whatsapp.device")),
                    ],
                    options={"db_table": "api_message"},
                ),
                migrations.CreateModel(
                    name="MessageTemplate",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("name", models.CharField(max_length=100)),
                        ("content", models.TextField()),
                        ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                        ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="templates", to="whatsapp.device")),
                    ],
                    options={"db_table": "api_messagetemplate"},
                ),
                migrations.CreateModel(
                    name="AutoReply",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("keyword", models.CharField(max_length=255)),
                        ("reply", models.TextField()),
                        ("is_default", models.BooleanField(default=False)),
                        ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                        ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="auto_replies", to="whatsapp.device")),
                    ],
                    options={"db_table": "api_autoreply"},
                ),
                migrations.CreateModel(
                    name="IncomingMessage",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("sender", models.CharField(max_length=20)),
                        ("message", models.TextField()),
                        ("name", models.CharField(blank=True, max_length=255)),
                        ("location", models.CharField(blank=True, max_length=100, null=True)),
                        ("attachment_url", models.URLField(blank=True, null=True)),
                        ("inbox_id", models.CharField(blank=True, max_length=100, null=True)),
                        ("timestamp", models.DateTimeField(default=django.utils.timezone.now)),
                        ("received_at", models.DateTimeField(default=django.utils.timezone.now)),
                        ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="incoming_messages", to="whatsapp.device")),
                    ],
                    options={"db_table": "api_incomingmessage"},
                ),
            ],
        ),
    ]
