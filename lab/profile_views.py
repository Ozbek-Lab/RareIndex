from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, View
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from .models import Profile
import json

class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "lab/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Ensure profile exists
        Profile.objects.get_or_create(user=self.request.user)
        context['profile'] = self.request.user.profile
        context['themes'] = [
            'light', 'dark', 'cupcake', 'bumblebee', 'emerald', 'corporate', 
            'synthwave', 'retro', 'cyberpunk', 'valentine', 'halloween', 
            'garden', 'forest', 'aqua', 'lofi', 'pastel', 'fantasy', 
            'wireframe', 'black', 'luxury', 'dracula', 'cmyk', 'autumn', 
            'business', 'acid', 'lemonade', 'night', 'coffee', 'winter', 
            'dim', 'nord', 'sunset', 'abyss', 'silk'
        ]
        return context

class UpdateThemeView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        theme = request.POST.get('theme')
        if theme:
            profile, created = Profile.objects.get_or_create(user=request.user)
            # Use a safer way to update JSONField to ensure Django detects changes
            prefs = profile.display_preferences or {}
            prefs['theme'] = theme
            profile.display_preferences = prefs
            profile.save()
            return HttpResponse(status=204)
        return HttpResponse("No theme provided", status=400)
