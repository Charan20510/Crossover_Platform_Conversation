
from django.db import migrations

MOVES = [
    ("accounts", ["account"]),
    ("whatsapp", ["device", "contact", "message", "messagetemplate", "autoreply", "incomingmessage"]),
    ("mail", ["mailaccount", "email", "incomingemail"]),
]

def _relabel(apps, old_label, new_label, model_names):
    ContentType = apps.get_model("contenttypes", "ContentType")
    for name in model_names:
        if ContentType.objects.filter(app_label=new_label, model=name).exists():
            continue
        ContentType.objects.filter(app_label=old_label, model=name).update(app_label=new_label)

def forwards(apps, schema_editor):
    for new_label, names in MOVES:
        _relabel(apps, "api", new_label, names)

def backwards(apps, schema_editor):
    for new_label, names in MOVES:
        _relabel(apps, new_label, "api", names)

class Migration(migrations.Migration):

    dependencies = [
        ("api", "0028_move_models_out"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
