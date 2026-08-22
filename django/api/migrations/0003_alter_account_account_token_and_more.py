
import secrets
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_alter_account_account_token_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='account',
            name='account_token',
            field=models.CharField(default=secrets.token_urlsafe, max_length=64, unique=True),
        ),
        migrations.AlterField(
            model_name='device',
            name='device_token',
            field=models.CharField(default='9jouSjjMzX8BekZGnY6yus2VbQSS7EeuE_EVNLNOals', max_length=64, unique=True),
        ),
    ]
