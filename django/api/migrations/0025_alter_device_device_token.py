
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0024_alter_device_device_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='device_token',
            field=models.CharField(default='rkyYS8lxzbiVVcCDnzt4d6s_78RB7K7VEJS4dAVUKp8', max_length=64, unique=True),
        ),
    ]
