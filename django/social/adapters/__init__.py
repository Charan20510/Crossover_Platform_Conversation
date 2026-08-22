
from .base import ChannelAdapter
from .telegram import TelegramAdapter

ADAPTERS = {
    TelegramAdapter.slug: TelegramAdapter(),
}

def get_adapter(slug):
    return ADAPTERS.get(slug)
