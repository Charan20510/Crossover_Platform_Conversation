
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0022_alter_device_device_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='device_token',
            field=models.CharField(default='2jqAbQoMpVPQTU9LoGXW3KXaTSWXtuPJKMGSJeqnuIs', max_length=64, unique=True),
        ),
    ]
