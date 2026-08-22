
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
                    name="MailAccount",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("mail_token", models.CharField(default=secrets.token_urlsafe, max_length=64, unique=True)),
                        ("name", models.CharField(max_length=30)),
                        ("email_address", models.EmailField(max_length=254)),
                        ("imap_host", models.CharField(max_length=255)),
                        ("imap_port", models.IntegerField(default=993)),
                        ("imap_secure", models.BooleanField(default=True)),
                        ("smtp_host", models.CharField(max_length=255)),
                        ("smtp_port", models.IntegerField(default=587)),
                        ("smtp_secure", models.BooleanField(default=False)),
                        ("username", models.CharField(max_length=255)),
                        ("password_enc", models.TextField()),
                        ("status", models.CharField(choices=[("connect", "Connected"), ("disconnect", "Disconnected")], default="disconnect", max_length=10)),
                        ("emails_sent", models.IntegerField(default=0)),
                        ("last_sync_at", models.DateTimeField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                        ("account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mail_accounts", to="accounts.account")),
                    ],
                    options={"db_table": "api_mailaccount"},
                ),
                migrations.CreateModel(
                    name="Email",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("to_addr", models.CharField(max_length=500)),
                        ("cc", models.CharField(blank=True, max_length=500)),
                        ("bcc", models.CharField(blank=True, max_length=500)),
                        ("subject", models.CharField(blank=True, max_length=500)),
                        ("body", models.TextField()),
                        ("status", models.CharField(choices=[("process", "Processing"), ("pending", "Pending / Scheduled"), ("sent", "Sent"), ("delivered", "Delivered"), ("read", "Read"), ("failed", "Failed")], default="process", max_length=10)),
                        ("message_id", models.CharField(blank=True, db_index=True, max_length=255, null=True)),
                        ("scheduled_at", models.DateTimeField(blank=True, null=True)),
                        ("sent_at", models.DateTimeField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                        ("mail_account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="emails", to="mail.mailaccount")),
                    ],
                    options={"db_table": "api_email"},
                ),
                migrations.CreateModel(
                    name="IncomingEmail",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("uid", models.CharField(blank=True, max_length=50)),
                        ("message_id", models.CharField(db_index=True, max_length=255)),
                        ("sender", models.CharField(max_length=255)),
                        ("sender_name", models.CharField(blank=True, max_length=255)),
                        ("subject", models.CharField(blank=True, max_length=500)),
                        ("body_text", models.TextField(blank=True)),
                        ("body_html", models.TextField(blank=True)),
                        ("folder", models.CharField(default="INBOX", max_length=100)),
                        ("is_read", models.BooleanField(default=False)),
                        ("has_attachments", models.BooleanField(default=False)),
                        ("received_at", models.DateTimeField(default=django.utils.timezone.now)),
                        ("mail_account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="incoming_emails", to="mail.mailaccount")),
                    ],
                    options={"db_table": "api_incomingemail", "unique_together": {("mail_account", "message_id")}},
                ),
            ],
        ),
    ]
