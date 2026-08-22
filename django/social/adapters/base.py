
class ChannelAdapter:
    slug = None
    capabilities = frozenset()

    def connect(self, social_account):
        raise NotImplementedError

    def send(self, social_account, target, body, **kwargs):
        raise NotImplementedError

    def fetch(self, social_account, since=None):
        raise NotImplementedError

    def handle_webhook(self, social_account, payload):
        raise NotImplementedError
