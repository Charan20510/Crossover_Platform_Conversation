
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_alter_device_device_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='device_token',
            field=models.CharField(default='yyNiN8xsMI3j_RG-NYV2KRfi3kZXtEq-QD62WOINXBs', max_length=64, unique=True),
        ),
    ]
