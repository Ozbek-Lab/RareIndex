from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from lab.models import Profile

class ProfileThemeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client = Client()
        self.client.login(username='testuser', password='password123')

    def test_profile_view_accessible(self):
        response = self.client.get(reverse('lab:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'lab/profile.html')
        self.assertIn('themes', response.context)

    def test_update_theme_view(self):
        response = self.client.post(reverse('lab:update_theme'), {'theme': 'dark'})
        self.assertEqual(response.status_code, 200)
        
        # Verify profile updated
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.display_preferences.get('theme'), 'dark')

    def test_context_processor_provides_theme(self):
        # Default theme
        response = self.client.get(reverse('lab:dashboard'))
        self.assertEqual(response.context['user_theme'], 'light')

        # Update theme and check again
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.display_preferences = {'theme': 'synthwave'}
        profile.save()

        response = self.client.get(reverse('lab:dashboard'))
        self.assertEqual(response.context['user_theme'], 'synthwave')
