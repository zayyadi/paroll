from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from core.middleware import DevNoCacheMiddleware, NO_CACHE_HEADERS


class DevNoCacheMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = lambda request: HttpResponse("ok")

    @override_settings(DEBUG=True)
    def test_sets_no_cache_headers_when_debug(self):
        response = DevNoCacheMiddleware(self.get_response)(self.factory.get("/"))
        for header, value in NO_CACHE_HEADERS.items():
            self.assertEqual(response[header], value)

    @override_settings(DEBUG=False)
    def test_leaves_response_untouched_when_not_debug(self):
        response = DevNoCacheMiddleware(self.get_response)(self.factory.get("/"))
        for header in NO_CACHE_HEADERS:
            self.assertNotIn(header, response)
