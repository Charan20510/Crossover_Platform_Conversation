
import re
import random
import requests
from django.conf import settings

def normalize_phone(raw_phone, country_code=None):
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

def contact_key(sender, country_code=None):
    raw = str(sender or "").split("@")[0].split(":")[0].strip()
    return normalize_phone(raw, country_code) if raw else ""

def to_jid(phone, country_code=None):
    return f"{normalize_phone(phone, country_code)}@s.whatsapp.net"

def apply_variables(message, variables):
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
    delay_str = str(delay_str)
    if "-" in delay_str:
        parts = delay_str.split("-")
        min_s = float(parts[0])
        max_s = float(parts[1])
        return int(random.uniform(min_s, max_s) * 1000)
    return int(float(delay_str) * 1000)

def parse_targets(target_str):
    results = []
    for entry in target_str.split(","):
        parts = entry.split("|")
        phone = parts[0].strip()
        vars_list = [p.strip() for p in parts[1:]]
        results.append({"phone": phone, "vars": vars_list})
    return results

def call_worker(path, method="POST", data=None, token=None):
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
    import secrets
    return secrets.token_urlsafe(32)

def call_mail_worker(path, method="POST", data=None, token=None):
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
    if not raw:
        return ""
    return _fernet().encrypt(raw.encode()).decode()

def decrypt_secret(token):
    if not token:
        return ""
    return _fernet().decrypt(token.encode()).decode()
