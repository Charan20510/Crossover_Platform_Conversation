from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag(takes_context=True)
def nav_active(context, url, exact=False):
    """Emit "active" for the current nav item.

    exact=True for section-root links (whatsapp:dashboard, mail:dashboard,
    core:overview) since those would otherwise match as a prefix of every
    page in the section. Everything else uses exact match too today (the
    sidebar has no nested sub-pages), kept as a parameter for when it does.
    """
    path = context["request"].path
    matches = path == url if exact else path.startswith(url)
    return "active" if matches else ""


@register.simple_tag(takes_context=True)
def nav_active_url(context, url_name, exact=False):
    return nav_active(context, reverse(url_name), exact=exact)
