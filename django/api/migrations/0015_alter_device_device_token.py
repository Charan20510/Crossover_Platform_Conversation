
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0014_alter_device_device_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='device_token',
            field=models.CharField(default='TkNOEyKaJr2jbqQkRil3aTY2PUrvsogjMQbYRu_e0so', max_length=64, unique=True),
        ),
    ]
