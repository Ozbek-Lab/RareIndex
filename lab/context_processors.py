from .models import Profile
import logging

logger = logging.getLogger(__name__)

def user_profile(request):
    """
    Context processor to add the user's theme to the context.
    """
    theme = 'light'
    if request.user.is_authenticated:
        try:
            # Safer way to get profile
            profile = Profile.objects.filter(user=request.user).first()
            if profile:
                theme = profile.display_preferences.get('theme', 'light')
        except Exception:
            pass
    
    return {
        'user_theme': theme
    }
