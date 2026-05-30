class AsyncWebsocketConsumer:
    groups = []

    @classmethod
    def as_asgi(cls, **initkwargs):
        async def application(scope, receive, send):
            consumer = cls(**initkwargs)
            consumer.scope = scope
            consumer.receive_asgi = receive
            consumer.send_asgi = send
            return consumer

        return application

    async def accept(self, subprotocol=None, headers=None):
        return None

    async def close(self, code=None, reason=None):
        return None

    async def send(self, text_data=None, bytes_data=None, close=False):
        return None
