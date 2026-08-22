
from django.contrib import admin
from .models import MailAccount, Email, IncomingEmail

@admin.register(MailAccount)
class MailAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "email_address", "status", "emails_sent", "account")
    list_filter = ("status",)
    search_fields = ("name", "email_address")
    exclude = ("password_enc",)

@admin.register(Email)
class EmailAdmin(admin.ModelAdmin):
    list_display = ("to_addr", "subject", "status", "mail_account", "created_at")
    list_filter = ("status",)
    search_fields = ("to_addr", "subject")

@admin.register(IncomingEmail)
class IncomingEmailAdmin(admin.ModelAdmin):
    list_display = ("sender", "subject", "mail_account", "received_at")
    search_fields = ("sender", "subject")
