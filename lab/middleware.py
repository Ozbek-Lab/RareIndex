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


class HtmxRedirectUnauthorizedMiddleware(MiddlewareMixin):
    """Ensure HTMX requests perform a full redirect to the login page on auth failures.

    - If a view protected by @login_required returns a 302 to LOGIN_URL, convert it to
      an HX-Redirect so HTMX performs a full navigation rather than swapping HTML.
    - Also handle 401/403 by issuing HX-Redirect to the login URL.
    """

    def _is_htmx(self, request):
        try:
            return request.headers.get("HX-Request") == "true" or getattr(request, "htmx", False)
        except Exception:
            return False

    def _login_url(self):
        try:
            from django.conf import settings
            return getattr(settings, "LOGIN_URL", "/accounts/login/")
        except Exception:
            return "/accounts/login/"

    def process_request(self, request):
        # Early guard: if HTMX and unauthenticated, instruct client to full-redirect
        try:
            if self._is_htmx(request):
                user = getattr(request, "user", None)
                if not getattr(user, "is_authenticated", False):
                    from django.http import HttpResponse
                    resp = HttpResponse(status=401)
                    resp["HX-Redirect"] = self._login_url()
                    return resp
        except Exception:
            pass

    def process_response(self, request, response):
        is_htmx = self._is_htmx(request)

        if not is_htmx:
            return response

        login_url = self._login_url()

        # Case 1: Redirects to login (e.g., produced by @login_required)
        try:
            if response.status_code in (301, 302):
                location = response.headers.get("Location") or response.get("Location")
                if location and location.startswith(login_url):
                    response["HX-Redirect"] = location
                    return response
        except Exception:
            pass

        # Case 2: Unauthorized/Forbidden responses
        try:
            if response.status_code in (401, 403):
                response["HX-Redirect"] = login_url
                return response
        except Exception:
            pass

        return response
