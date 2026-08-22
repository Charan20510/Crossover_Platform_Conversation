
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
