from django import template
from django.urls import reverse

register = template.Library()

@register.simple_tag(takes_context=True)
def nav_active(context, url, exact=False):
    path = context["request"].path
    matches = path == url if exact else path.startswith(url)
    return "active" if matches else ""

@register.simple_tag(takes_context=True)
def nav_active_url(context, url_name, exact=False):
    return nav_active(context, reverse(url_name), exact=exact)
