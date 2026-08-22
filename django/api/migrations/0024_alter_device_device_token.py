
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0023_alter_device_device_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='device_token',
            field=models.CharField(default='MbCl96nAED10T8vTtGwzpGCHb8aM4FSDrxs1fZT31ts', max_length=64, unique=True),
        ),
    ]
