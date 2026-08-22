
SECTIONS = ("whatsapp", "mail")

INBOX_URL_NAME = {
    "whatsapp": "whatsapp:inbox",
    "mail": "mail:inbox",
    "unified": "core:all_inbox",
}

def nav(request):
    namespace = getattr(request.resolver_match, "namespace", "") or ""
    section = namespace if namespace in SECTIONS else "unified"
    return {
        "nav_section": section,
        "nav_include": f"core/nav/_{section}.html",
        "nav_inbox_url": INBOX_URL_NAME[section],
    }
