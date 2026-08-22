
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_alter_device_device_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='device_token',
            field=models.CharField(default='mYpApjQan5CDR3aANAKsqEbIJfzMDBZoVxodJOA3Z4w', max_length=64, unique=True),
        ),
    ]
