
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_alter_device_device_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='device_token',
            field=models.CharField(default='XLwKQxGGCVUYQf3Rkoltiz18QzbK1YP5W50Xam1_DvE', max_length=64, unique=True),
        ),
    ]
