
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0010_alter_device_device_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='device_token',
            field=models.CharField(default='BY_bqhbfmubhYrG564pkd2Y4RDjI2YHaROBTc97aEM8', max_length=64, unique=True),
        ),
    ]
