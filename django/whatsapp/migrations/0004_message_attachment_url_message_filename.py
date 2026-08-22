
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0003_backfill_incomingmessage_contact'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='attachment_url',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='message',
            name='filename',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
