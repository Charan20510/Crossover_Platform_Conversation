"""
Adapter registry. Each platform module registers a ChannelAdapter subclass
here; views.py and webhooks.py look adapters up by slug instead of branching
on platform name.
"""

from .base import ChannelAdapter
from .telegram import TelegramAdapter

ADAPTERS = {
    TelegramAdapter.slug: TelegramAdapter(),
}


def get_adapter(slug):
    return ADAPTERS.get(slug)
