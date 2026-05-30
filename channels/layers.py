class InMemoryChannelLayer:
    async def group_add(self, group, channel):
        return None

    async def group_discard(self, group, channel):
        return None

    async def group_send(self, group, message):
        return None


_default_layer = InMemoryChannelLayer()


def get_channel_layer(alias="default"):
    return _default_layer
