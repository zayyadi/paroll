class ProtocolTypeRouter(dict):
    pass


class URLRouter:
    def __init__(self, routes):
        self.routes = routes

    async def __call__(self, scope, receive, send):
        return None
