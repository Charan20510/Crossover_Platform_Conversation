
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_alter_device_device_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='device_token',
            field=models.CharField(default='KTV3VTnz_4eMWXlL0SZENZQ6Lv0d2VcSb9DrJV1vMmk', max_length=64, unique=True),
        ),
    ]
