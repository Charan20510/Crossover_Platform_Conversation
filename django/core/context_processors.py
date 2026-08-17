"""
Section-aware nav: derives the active top-bar section from the resolved URL
namespace, so no view has to remember to pass it — the whatsapp/mail/core
ui_urls.py app_name IS the section.
"""

SECTIONS = ("whatsapp", "mail")

INBOX_URL_NAME = {
    "whatsapp": "whatsapp:inbox",
    "mail": "mail:inbox",
    "unified": "core:all_inbox",
}


def nav(request):
    # resolver_match is None while rendering error pages (404/500) -> fall
    # back to unified rather than raising.
    namespace = getattr(request.resolver_match, "namespace", "") or ""
    section = namespace if namespace in SECTIONS else "unified"
    return {
        "nav_section": section,
        "nav_include": f"core/nav/_{section}.html",
        "nav_inbox_url": INBOX_URL_NAME[section],
    }
