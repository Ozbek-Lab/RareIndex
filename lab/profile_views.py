from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views.generic import TemplateView, View

from .models import Profile
from .display_preferences import (
    DEFAULT_INSTITUTION_DISPLAY,
    INSTITUTION_DISPLAY_OPTIONS,
    INSTITUTION_DISPLAY_VALUES,
    normalize_institution_display,
)

FONT_SIZE_OPTIONS = [
    {
        "value": "small",
        "label": "Small",
        "description": "Current size",
    },
    {
        "value": "medium",
        "label": "Medium",
        "description": "A little larger",
    },
    {
        "value": "large",
        "label": "Large",
        "description": "Largest size",
    },
]

FONT_SIZE_MAP = {
    "small": "100%",
    "medium": "112.5%",
    "large": "125%",
}

FONT_SIZE_VALUES = set(FONT_SIZE_MAP)

DEFAULT_FONT_SIZE = "small"


def _get_profile_preferences(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile, profile.display_preferences or {}


def _save_display_preference(user, key, value):
    profile, prefs = _get_profile_preferences(user)
    prefs[key] = value
    profile.display_preferences = prefs
    profile.save(update_fields=["display_preferences"])


def _normalize_font_size(font_size):
    if font_size in FONT_SIZE_VALUES:
        return font_size
    return DEFAULT_FONT_SIZE

class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "lab/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile, prefs = _get_profile_preferences(self.request.user)
        font_size = _normalize_font_size(prefs.get("font_size", DEFAULT_FONT_SIZE))
        institution_display = normalize_institution_display(
            prefs.get("institution_display", DEFAULT_INSTITUTION_DISPLAY)
        )

        context["profile"] = profile
        context["themes"] = [
            'light', 'dark', 'cupcake', 'bumblebee', 'emerald', 'corporate', 
            'synthwave', 'retro', 'cyberpunk', 'valentine', 'halloween', 
            'garden', 'forest', 'aqua', 'lofi', 'pastel', 'fantasy', 
            'wireframe', 'black', 'luxury', 'dracula', 'cmyk', 'autumn', 
            'business', 'acid', 'lemonade', 'night', 'coffee', 'winter', 
            'dim', 'nord', 'sunset', 'abyss', 'silk'
        ]
        context["font_sizes"] = FONT_SIZE_OPTIONS
        context["institution_display_options"] = INSTITUTION_DISPLAY_OPTIONS
        context["user_font_size"] = font_size
        context["user_font_size_css"] = FONT_SIZE_MAP[font_size]
        context["user_institution_display"] = institution_display
        return context

class UpdateThemeView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        theme = request.POST.get('theme')
        if theme:
            _save_display_preference(request.user, "theme", theme)
            return HttpResponse(status=204)
        return HttpResponse("No theme provided", status=400)


class UpdateFontSizeView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        raw_font_size = request.POST.get("font_size")
        if raw_font_size not in FONT_SIZE_VALUES:
            return HttpResponse("No font size provided", status=400)

        font_size = _normalize_font_size(raw_font_size)
        _save_display_preference(request.user, "font_size", font_size)
        return HttpResponse(status=204)


class UpdateInstitutionDisplayView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        raw_display = request.POST.get("institution_display")
        if raw_display not in INSTITUTION_DISPLAY_VALUES:
            return HttpResponse("No institution display preference provided", status=400)

        institution_display = normalize_institution_display(raw_display)
        _save_display_preference(request.user, "institution_display", institution_display)
        return HttpResponse(status=204)
