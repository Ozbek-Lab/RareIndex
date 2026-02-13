from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from lab.models import Individual, Project, Status
from lab.htmx_views import task_create_modal

User = get_user_model()

class TaskCreateModalTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.project = Project.objects.create(name="Test Project")
        self.individual = Individual.objects.create(name="Test Indiv")
        self.status = Status.objects.create(name="Registered", description="Test Status")
        self.factory = RequestFactory()

    def test_task_create_modal_individual_context(self):
        """
        Verify that task_create_modal does not raise NameError
        and correctly populates the context for an Individual.
        """
        ct = ContentType.objects.get_for_model(Individual)
        url = reverse('lab:task_create_modal', args=[ct.id, self.individual.id])
        
        request = self.factory.get(url)
        request.user = self.user
        
        # We need to render it to check for template errors
        response = task_create_modal(request, ct.id, self.individual.id)
        
        self.assertEqual(response.status_code, 200)
        # Check if 'individual' is in context (implicit in render success, but good to check)
        # Note: 'render' returns HttpResponse, not TemplateResponse with context accessible easily
        # unless we use test client. But we called view directly.
        # Let's use test client for easier context access
        
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('individual', response.context)
        self.assertEqual(response.context['individual'], self.individual)
