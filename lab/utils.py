import time
from django.core import signing
from django.conf import settings

def generate_plot_jwt(user):
    """
    Generate a short-lived signed token for Marimo dashboard access.
    Using django.core.signing since PyJWT is not installed.
    """
    payload = {
        "user_id": user.id,
        "timestamp": time.time()
    }
    # signs the data and returns a string
    return signing.dumps(payload, key=settings.SECRET_KEY)

def verify_plot_jwt(token):
    """
    Verify the signed token and return the user_id if valid.
    Tokens are valid for 60 seconds.
    """
    try:
        payload = signing.loads(token, key=settings.SECRET_KEY, max_age=60)
        return payload.get("user_id")
    except (signing.SignatureExpired, signing.BadSignature):
        return None

from functools import wraps
from django.http import JsonResponse

def jwt_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            # Also check query param ?token= for iframe initial load if needed, 
            # but usually Marimo calls with Bearer.
            token = request.GET.get("token")
        else:
            token = auth_header.split(" ")[1]
        
        if not token:
            return JsonResponse({"error": "No token provided"}, status=401)
        
        user_id = verify_plot_jwt(token)
        if not user_id:
            return JsonResponse({"error": "Invalid or expired token"}, status=401)
        
        # Optionally attach user to request
        from django.contrib.auth.models import User
        try:
            request.user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=401)
            
        return view_func(request, *args, **kwargs)
    return _wrapped_view
