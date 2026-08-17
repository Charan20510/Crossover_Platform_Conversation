"""
Shared utility functions — phone normalization, worker HTTP calls, secret
crypto. Used by both the whatsapp and mail apps (moved here verbatim from
api/utils.py so neither app has to depend on the other for these).
"""

import re
import random
import requests
from django.conf import settings


def normalize_phone(raw_phone, country_code=None):
    """
    Normalize a phone number to international format.
    - Strip spaces, dashes, parentheses
    - Replace leading 0 with country code (default 91 for India)
    - Return digits only (no + prefix)
    """
    cc = country_code or settings.DEFAULT_COUNTRY_CODE
    phone = re.sub(r"[\s\-\(\)]", "", str(raw_phone))

    if phone.startswith("+"):
        phone = phone[1:]
    elif phone.startswith("00"):
        phone = phone[2:]
    elif phone.startswith("0"):
        phone = cc + phone[1:]
    elif not phone.startswith(cc):
        phone = cc + phone

    return phone


def to_jid(phone, country_code=None):
    """Convert a phone number to WhatsApp JID format."""
    return f"{normalize_phone(phone, country_code)}@s.whatsapp.net"


def apply_variables(message, variables):
    """
    Replace {name}, {var1}, {var2}, etc. in a message.
    variables is a list: [name, var1, var2, ...]
    """
    if not variables:
        return message

    replacements = {}
    if len(variables) > 0:
        replacements["{name}"] = variables[0]
    for i, v in enumerate(variables[1:], 1):
        replacements[f"{{var{i}}}"] = v

    for key, val in replacements.items():
        message = message.replace(key, str(val))
    return message


def parse_delay(delay_str):
    """
    Parse delay string.
    - "2" -> 2 seconds
    - "1-10" -> random between 1 and 10 seconds
    Returns milliseconds for queue delay.
    """
    delay_str = str(delay_str)
    if "-" in delay_str:
        parts = delay_str.split("-")
        min_s = float(parts[0])
        max_s = float(parts[1])
        return int(random.uniform(min_s, max_s) * 1000)
    return int(float(delay_str) * 1000)


def parse_targets(target_str):
    """
    Parse the target string.
    - "08123456789" -> [{"phone": "08123456789", "vars": []}]
    - "08123456789|John|Admin,08987654321|Jane|User" -> multiple with vars
    """
    results = []
    for entry in target_str.split(","):
        parts = entry.split("|")
        phone = parts[0].strip()
        vars_list = [p.strip() for p in parts[1:]]
        results.append({"phone": phone, "vars": vars_list})
    return results


def call_worker(path, method="POST", data=None, token=None):
    """
    Make an HTTP request to the Node.js Baileys worker.
    """
    url = f"{settings.WORKER_BASE_URL}{path}"
    headers = {}
    if token:
        headers["Authorization"] = token
    if method == "POST":
        response = requests.post(url, json=data, headers=headers, timeout=30)
    else:
        response = requests.get(url, headers=headers, timeout=30)
    return response.json()


def generate_token():
    """Generate a secure random token."""
    import secrets
    return secrets.token_urlsafe(32)


def call_mail_worker(path, method="POST", data=None, token=None):
    """
    Make an HTTP request to the Node.js mail worker (ImapFlow + Nodemailer).
    """
    url = f"{settings.MAIL_WORKER_BASE_URL}{path}"
    headers = {}
    if token:
        headers["Authorization"] = token
    if method == "POST":
        response = requests.post(url, json=data, headers=headers, timeout=30)
    else:
        response = requests.get(url, headers=headers, timeout=30)
    return response.json()


def _fernet():
    """Derive a Fernet key from DJANGO_SECRET_KEY (cached on first use)."""
    global _fernet_instance
    try:
        return _fernet_instance
    except NameError:
        pass
    import hashlib
    import base64
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    _fernet_instance = Fernet(key)
    return _fernet_instance


def encrypt_secret(raw):
    """Encrypt a plaintext secret (e.g. a mail password) for storage."""
    if not raw:
        return ""
    return _fernet().encrypt(raw.encode()).decode()


def decrypt_secret(token):
    """Decrypt a secret previously encrypted with encrypt_secret()."""
    if not token:
        return ""
    return _fernet().decrypt(token.encode()).decode()
