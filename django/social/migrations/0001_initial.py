
import django.db.models.deletion
import django.utils.timezone
import secrets
import uuid
from django.db import migrations, models

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SocialAccount',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('platform', models.CharField(choices=[('telegram', 'Telegram'), ('slack', 'Slack'), ('linkedin', 'LinkedIn'), ('facebook', 'Facebook'), ('instagram', 'Instagram'), ('gbp', 'Google Business Profile'), ('x', 'X (Twitter)')], max_length=20)),
                ('social_token', models.CharField(default=secrets.token_urlsafe, max_length=64, unique=True)),
                ('name', models.CharField(max_length=30)),
                ('credentials_enc', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('connect', 'Connected'), ('disconnect', 'Disconnected')], default='disconnect', max_length=10)),
                ('last_sync_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='social_accounts', to='accounts.account')),
            ],
            options={
                'db_table': 'social_account',
            },
        ),
        migrations.CreateModel(
            name='SocialMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('direction', models.CharField(choices=[('in', 'Inbound'), ('out', 'Outbound')], max_length=3)),
                ('external_id', models.CharField(blank=True, db_index=True, max_length=255)),
                ('target', models.CharField(blank=True, max_length=255)),
                ('body', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('process', 'Processing'), ('pending', 'Pending / Scheduled'), ('sent', 'Sent'), ('delivered', 'Delivered'), ('read', 'Read'), ('failed', 'Failed')], default='process', max_length=10)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('social_account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='social.socialaccount')),
            ],
            options={
                'db_table': 'social_message',
            },
        ),
        migrations.AddIndex(
            model_name='socialaccount',
            index=models.Index(fields=['platform'], name='social_acco_platfor_37a64a_idx'),
        ),
        migrations.AddConstraint(
            model_name='socialmessage',
            constraint=models.UniqueConstraint(condition=models.Q(('external_id', ''), _negated=True), fields=('social_account', 'external_id'), name='uniq_social_account_external_id'),
        ),
    ]
