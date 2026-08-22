
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Contact',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(db_index=True, max_length=255)),
                ('company', models.CharField(blank=True, max_length=255)),
                ('notes', models.TextField(blank=True)),
                ('whatsapp', models.CharField(blank=True, max_length=32)),
                ('mobile', models.CharField(blank=True, max_length=32)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('instagram', models.CharField(blank=True, max_length=100)),
                ('facebook', models.CharField(blank=True, max_length=100)),
                ('x', models.CharField(blank=True, max_length=100)),
                ('linkedin', models.CharField(blank=True, max_length=200)),
                ('slack', models.CharField(blank=True, max_length=100)),
                ('gbp', models.CharField(blank=True, max_length=200)),
                ('telegram', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contacts', to='accounts.account')),
            ],
            options={
                'db_table': 'core_contact',
                'ordering': ['name'],
            },
        ),
    ]
