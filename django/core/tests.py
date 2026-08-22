
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import Account
from .models import Contact

class ContactsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u1", password="pw12345!")
        self.account = Account.objects.create(user=self.user, name="Acct", email="acct@example.com")
        self.client.force_login(self.user)

    def test_create_contact(self):
        res = self.client.post(reverse("core:contacts"), {
            "action": "create", "name": "Ramu", "whatsapp": "919876543210",
            "email": "ramu@example.com",
        })
        self.assertRedirects(res, reverse("core:contacts"))
        contact = Contact.objects.get(account=self.account, name="Ramu")
        self.assertEqual(contact.whatsapp, "919876543210")
        self.assertEqual(contact.email, "ramu@example.com")

    def test_edit_contact(self):
        contact = Contact.objects.create(account=self.account, name="Ramu", email="old@example.com")
        self.client.post(reverse("core:contacts"), {
            "action": "edit", "contact_id": str(contact.id),
            "name": "Ramu K", "email": "new@example.com",
        })
        contact.refresh_from_db()
        self.assertEqual(contact.name, "Ramu K")
        self.assertEqual(contact.email, "new@example.com")

    def test_create_normalizes_phone(self):
        self.client.post(reverse("core:contacts"), {
            "action": "create", "name": "Priya", "whatsapp": "+1 555 123 4567",
            "mobile": "098765 43210",
        })
        contact = Contact.objects.get(account=self.account, name="Priya")
        self.assertEqual(contact.whatsapp, "15551234567")
        self.assertEqual(contact.mobile, "919876543210")

    def test_edit_normalizes_phone(self):
        contact = Contact.objects.create(account=self.account, name="Ramu")
        self.client.post(reverse("core:contacts"), {
            "action": "edit", "contact_id": str(contact.id),
            "name": "Ramu", "whatsapp": "+1 555 123 4567",
        })
        contact.refresh_from_db()
        self.assertEqual(contact.whatsapp, "15551234567")

    def test_delete_contact(self):
        contact = Contact.objects.create(account=self.account, name="Ramu")
        self.client.post(reverse("core:contacts"), {
            "action": "delete", "contact_id": str(contact.id),
        })
        self.assertFalse(Contact.objects.filter(id=contact.id).exists())

    def test_search_finds_by_partial_name(self):
        Contact.objects.create(account=self.account, name="Ramu", whatsapp="919876543210")
        res = self.client.get(reverse("core:contacts_search"), {"q": "ra"})
        data = res.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["name"], "Ramu")

    def test_search_requires_two_characters(self):
        Contact.objects.create(account=self.account, name="Ramu")
        res = self.client.get(reverse("core:contacts_search"), {"q": "r"})
        self.assertEqual(res.json()["results"], [])

    def test_search_scoped_to_account(self):
        other_user = User.objects.create_user("u2", password="pw12345!")
        other_account = Account.objects.create(user=other_user, name="Other", email="o@example.com")
        Contact.objects.create(account=other_account, name="Ravi")
        res = self.client.get(reverse("core:contacts_search"), {"q": "ra"})
        self.assertEqual(res.json()["results"], [])
