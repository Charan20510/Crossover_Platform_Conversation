
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_alter_device_device_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='device_token',
            field=models.CharField(default='yFfaTLRyRS-obRXIqA7tvj_HrVn6GRXkK1-d-Xi_y8I', max_length=64, unique=True),
        ),
    ]
