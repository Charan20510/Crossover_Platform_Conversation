
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0025_alter_device_device_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='device_token',
            field=models.CharField(default='qHJKBaInsbSxGQV8PP8mhJT7idQ36ish-uSBvhHNSiI', max_length=64, unique=True),
        ),
    ]
