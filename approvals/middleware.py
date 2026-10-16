"""Supply authenticated request actors to existing business-operation services."""
from .proposals import _request_actor, _request_key

class ApprovalActorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        key_token = _request_key.set(request.headers.get('Idempotency-Key') or (request.POST.get('_approval_key') if request.method == 'POST' else None))
        token = _request_actor.set(request.user if request.user.is_authenticated else None)
        try:
            return self.get_response(request)
        finally:
            _request_actor.reset(token)
            _request_key.reset(key_token)
