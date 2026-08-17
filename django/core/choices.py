"""
Shared model choice lists.

Both whatsapp.Device/whatsapp.Message and mail.MailAccount/mail.Email use the
same connect/disconnect and send-status vocabulary. Previously this was
expressed as `MailAccount.STATUS_CHOICES = Device.STATUS_CHOICES` (a
cross-app class-attribute coupling) — defining the lists once here breaks
that coupling without changing the values.
"""

CONNECTION_STATUS_CHOICES = [
    ("connect", "Connected"),
    ("disconnect", "Disconnected"),
]

SEND_STATUS_CHOICES = [
    ("process", "Processing"),
    ("pending", "Pending / Scheduled"),
    ("sent", "Sent"),
    ("delivered", "Delivered"),
    ("read", "Read"),
    ("failed", "Failed"),
]
