"""
Drop the 10 models from the api app's migration state — they now live in
accounts/whatsapp/mail (adopted in each app's 0001_initial with the same
db_table, so no data moves). Zero DDL.

Children deleted before parents so no intermediate state has a dangling FK
reference (e.g. deleting Device while IncomingMessage.device still points at
'api.device' would raise "lazy reference to api.device").
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0027_alter_device_device_token_mailaccount_email_and_more"),
        ("accounts", "0001_initial"),
        ("whatsapp", "0001_initial"),
        ("mail", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="IncomingEmail"),
                migrations.DeleteModel(name="Email"),
                migrations.DeleteModel(name="MailAccount"),
                migrations.DeleteModel(name="Contact"),
                migrations.DeleteModel(name="Message"),
                migrations.DeleteModel(name="MessageTemplate"),
                migrations.DeleteModel(name="AutoReply"),
                migrations.DeleteModel(name="IncomingMessage"),
                migrations.DeleteModel(name="Device"),
                migrations.DeleteModel(name="Account"),
            ],
        ),
    ]
