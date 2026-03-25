import jwt
import datetime
from django.conf import settings
from django.contrib.auth.models import User

class AuthenticationError(Exception):
    pass

def issue_plot_token(user):
    """
    Generate an HS256 JWT for Marimo dashboard (iframe) access.
    Lifetime from settings.MARIMO_PLOT_TOKEN_MAX_AGE (default 15 minutes).
    """
    import time

    max_age = int(getattr(settings, "MARIMO_PLOT_TOKEN_MAX_AGE", 900))
    now = int(time.time())
    payload = {
        "user_id": user.id,
        "iat": now,
        "exp": now + max_age,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def issue_editor_plot_token(user):
    """
    Longer-lived JWT for staff opening Marimo edit mode via /authoring/marimo/.
    Same verification as dashboard tokens; only the issuance endpoint differs.
    """
    import time

    now = int(time.time())
    max_age = int(getattr(settings, "MARIMO_EDITOR_TOKEN_MAX_AGE", 28800))
    payload = {
        "user_id": user.id,
        "iat": now,
        "exp": now + max_age,
        "scope": "marimo_editor",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

def verify_plot_token(token):
    """
    Verify the JWT and return the User object.
    Raises AuthenticationError if invalid or expired.
    """
    try:
        # Add 30s leeway to handle clock skew between services
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"], leeway=30)
        user_id = payload.get("user_id")
        if not user_id:
            raise AuthenticationError("Invalid payload: missing user_id")
        
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise AuthenticationError("User not found")
            
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(f"Invalid token: {str(e)}")
