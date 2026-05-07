import logging

from .models import Profile
from .display_preferences import DEFAULT_INSTITUTION_DISPLAY, normalize_institution_display
from .profile_views import DEFAULT_FONT_SIZE, FONT_SIZE_MAP

logger = logging.getLogger(__name__)

def user_profile(request):
    """
    Context processor to add the user's theme and font size to the context.
    """
    theme = 'light'
    font_size = DEFAULT_FONT_SIZE
    institution_display = DEFAULT_INSTITUTION_DISPLAY
    if request.user.is_authenticated:
        try:
            # Safer way to get profile
            profile = Profile.objects.filter(user=request.user).first()
            if profile:
                theme = profile.display_preferences.get('theme', 'light')
                font_size = profile.display_preferences.get('font_size', DEFAULT_FONT_SIZE)
                institution_display = normalize_institution_display(
                    profile.display_preferences.get('institution_display', DEFAULT_INSTITUTION_DISPLAY)
                )
                if font_size not in FONT_SIZE_MAP:
                    font_size = DEFAULT_FONT_SIZE
        except Exception:
            pass
    
    return {
        'user_theme': theme,
        'user_font_size': font_size,
        'user_font_size_css': FONT_SIZE_MAP[font_size],
        'user_institution_display': institution_display,
    }
