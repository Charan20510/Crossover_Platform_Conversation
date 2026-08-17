"""
Django admin configuration.
"""

from django.contrib import admin
from .models import (
    Account, Device, Contact, Message, MessageTemplate, AutoReply, IncomingMessage,
    MailAccount, Email, IncomingEmail,
)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "created_at")
    search_fields = ("name", "email")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "phone_number", "status", "package", "quota", "messages_sent", "account")
    list_filter = ("status", "package")
    search_fields = ("name", "phone_number")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("target", "status", "device", "created_at", "sent_at")
    list_filter = ("status",)
    search_fields = ("target",)


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("phone", "name", "device")
    search_fields = ("phone", "name")


@admin.register(MessageTemplate)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "device")


@admin.register(AutoReply)
class AutoReplyAdmin(admin.ModelAdmin):
    list_display = ("keyword", "device", "is_default")


@admin.register(IncomingMessage)
class IncomingMessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "message", "device", "received_at")
    search_fields = ("sender", "message")


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
