import threading
from django.utils.deprecation import MiddlewareMixin


_current_user_storage = threading.local()


def get_current_user():
    """Return the current authenticated user captured by middleware, if any."""
    return getattr(_current_user_storage, "user", None)


class CurrentUserMiddleware(MiddlewareMixin):
    """Store request.user in thread-local storage for model-layer access.

    Must be placed AFTER AuthenticationMiddleware.
    """

    def process_request(self, request):
        try:
            _current_user_storage.user = getattr(request, "user", None)
        except Exception:
            _current_user_storage.user = None

    def process_response(self, request, response):
        try:
            _current_user_storage.user = None
        except Exception:
            pass
        return response

    def process_exception(self, request, exception):
        try:
            _current_user_storage.user = None
        except Exception:
            pass

