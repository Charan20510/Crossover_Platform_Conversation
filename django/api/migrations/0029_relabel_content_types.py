"""
Re-point the ContentType rows for the 10 moved models from app_label="api" to
their new app (accounts/whatsapp/mail), in place, by UPDATE rather than
delete+recreate. This keeps content_type_id stable so auth_permission and
django_admin_log rows keep resolving correctly instead of being orphaned
under the old "api" label while create_permissions() silently creates a
fresh, ungranted set under the new label.

On a fresh database this is a no-op: no "api.<model>" content types exist
yet (they haven't been created), so both directions just find 0 rows.
"""

from django.db import migrations

MOVES = [
    ("accounts", ["account"]),
    ("whatsapp", ["device", "contact", "message", "messagetemplate", "autoreply", "incomingmessage"]),
    ("mail", ["mailaccount", "email", "incomingemail"]),
]


def _relabel(apps, old_label, new_label, model_names):
    ContentType = apps.get_model("contenttypes", "ContentType")
    for name in model_names:
        # Idempotent, and safe to re-run: never delete a ContentType (that
        # would cascade-delete its auth_permission rows).
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
