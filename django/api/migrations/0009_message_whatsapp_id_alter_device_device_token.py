
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_alter_device_device_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='whatsapp_id',
            field=models.CharField(blank=True, db_index=True, max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='device',
            name='device_token',
            field=models.CharField(default='pDdbgJIN0Ef27ePjepc9uTFUQAjmnvyGLNNgcJndtLY', max_length=64, unique=True),
        ),
    ]
