"""Backfill IncomingMessage.contact from the JID stored in sender."""

from django.db import migrations

from core.utils import contact_key


def forwards(apps, schema_editor):
    IncomingMessage = apps.get_model("whatsapp", "IncomingMessage")
    rows = IncomingMessage.objects.exclude(sender="").filter(contact="")
    batch = []
    for row in rows.only("id", "sender").iterator(chunk_size=2000):
        row.contact = contact_key(row.sender)
        batch.append(row)
        if len(batch) >= 2000:
            IncomingMessage.objects.bulk_update(batch, ["contact"])
            batch = []
    if batch:
        IncomingMessage.objects.bulk_update(batch, ["contact"])


class Migration(migrations.Migration):

    dependencies = [
        ("whatsapp", "0002_incomingmessage_contact_alter_incomingmessage_sender_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
