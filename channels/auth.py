class AuthMiddlewareStack:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if callable(self.inner):
            return await self.inner(scope, receive, send)
        return None
