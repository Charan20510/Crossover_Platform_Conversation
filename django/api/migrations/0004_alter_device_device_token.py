
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_alter_account_account_token_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='device_token',
            field=models.CharField(default='WdR-tC7Tzw_ZcCaSPy2soB_6WLJLrhTGgkoWjBEnXhQ', max_length=64, unique=True),
        ),
    ]
