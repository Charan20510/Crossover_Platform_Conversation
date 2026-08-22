from django.contrib import admin

from .models import Contact


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "whatsapp", "email", "account")
    search_fields = ("name", "company", "whatsapp", "email")
