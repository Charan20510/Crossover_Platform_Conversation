
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from accounts.models import Account

class Command(BaseCommand):
    help = "Create a default superuser and a demo account automatically."

    def handle(self, *args, **options):
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser(
                username="admin",
                email="admin@wa-gateway.local",
                password="admin123",
            )
            self.stdout.write(self.style.SUCCESS("Superuser created: admin / admin123"))
        else:
            self.stdout.write("Superuser 'admin' already exists.")

        if not Account.objects.filter(email="demo@wa-gateway.local").exists():
            account = Account.objects.create(
                name="Demo Account",
                email="demo@wa-gateway.local",
            )
            self.stdout.write(self.style.SUCCESS(
                f"Demo account created. Account token: {account.account_token}"
            ))
        else:
            self.stdout.write("Demo account already exists.")

        if not Account.objects.filter(email="demo@wa-gateway.local").exists():
            pass
        else:
            account = Account.objects.get(email="demo@wa-gateway.local")
            if account.devices.count() == 0:
                device = account.devices.create(
                    name="Demo Device",
                    phone_number="910000000000",
                    package="free",
                    quota=1000,
                )
                self.stdout.write(self.style.SUCCESS(
                    f"Demo device created. Device token: {device.device_token}"
                ))
