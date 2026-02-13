from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from lab.models import Task, Status, Individual, Sample, Project, Note, SampleType
from django.utils import timezone
from datetime import timedelta

class DashboardViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.other_user = User.objects.create_user(username='otheruser', password='password')
        self.client.login(username='testuser', password='password')
        
        # Create Statuses
        self.status_pending = Status.objects.create(name="Pending", created_by=self.user)
        self.status_completed = Status.objects.create(name="Completed", created_by=self.user)
        
        # Create Tasks
        self.task1 = Task.objects.create(
            title="My Pending Task",
            assigned_to=self.user,
            created_by=self.user,
            status=self.status_pending,
            due_date=timezone.now() + timedelta(days=1)
        )
        self.task2 = Task.objects.create(
            title="My Completed Task",
            assigned_to=self.user,
            created_by=self.user,
            status=self.status_completed, # Should not show
            due_date=timezone.now() - timedelta(days=1)
        )
        self.task3 = Task.objects.create(
            title="Other User Task",
            assigned_to=self.other_user, # Should not show
            created_by=self.user,
            status=self.status_pending,
            due_date=timezone.now() + timedelta(days=2)
        )
        
        # Create History Items (News Feed)
        # 1. Create Individual
        self.individual = Individual.objects.create(
            full_name="John Doe",
            created_by=self.user,
            status=self.status_pending
        )
        # 2. Create SampleType
        self.sample_type = SampleType.objects.create(name="Blood", created_by=self.user)
        # 3. Create Sample
        self.sample = Sample.objects.create(
            individual=self.individual,
            sample_type=self.sample_type,
            status=self.status_pending,
            isolation_by=self.user,
            created_by=self.user
        )
        # 4. Create Note
        self.note = Note.objects.create(
            content="Some note",
            user=self.user,
            content_object=self.individual
        )

    def test_dashboard_context(self):
        response = self.client.get(reverse('dashboard')) # Assuming url name is 'dashboard'
        self.assertEqual(response.status_code, 200)
        
        # Check "My Tasks"
        tasks = response.context['my_tasks']
        self.assertIn(self.task1, tasks)
        self.assertNotIn(self.task2, tasks)
        self.assertNotIn(self.task3, tasks)
        
        # Check "Completed Tasks"
        completed = response.context['completed_tasks']
        self.assertIn(self.task2, completed)
        self.assertEqual(len(completed), 1)
        
        # Check "News Feed"
        feed = response.context['news_feed']

        # Check 'now' context variable
        self.assertIn('now', response.context)
        from django.utils import timezone
        self.assertAlmostEqual(response.context['now'], timezone.now(), delta=timedelta(seconds=5))

        # We expect historical records in the feed.
        # Since simple_history creates records on save, we should have them.
        # Verify Diff Logic
        # Update the sample status to trigger a change
        old_status = self.sample.status
        self.sample.status = self.status_completed
        self.sample.save()
        
        # Reload dashboard
        response = self.client.get(reverse('dashboard'))
        feed = response.context['news_feed']
        
        # Find the update event
        update_event = None
        for item in feed:
            if item.history_type == '~' and isinstance(item.instance, Sample):
                update_event = item
                break
        
        self.assertIsNotNone(update_event)
        self.assertTrue(hasattr(update_event, 'diff_display'))
        self.assertIn('status', update_event.diff_display)
        
        # Verify My Tasks content_object
        tasks = response.context['my_tasks']
        self.assertTrue(any(t.content_object is not None for t in tasks))

    def test_complete_task_view(self):
        """Test the CompleteTaskView handles POST request correctly"""
        url = reverse('lab:complete_task', args=[self.task1.id])
        self.client.force_login(self.user)
        
        response = self.client.post(url)
        
        # Check success response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        
        # Verify task is completed
        self.task1.refresh_from_db()
        self.assertEqual(self.task1.status.name.lower(), "completed")

    def test_complete_task_view_forbidden(self):
        """Test the CompleteTaskView returns 403 for unauthorized users"""
        other_user = User.objects.create_user(username='otheruser_extra', password='password')
        url = reverse('lab:complete_task', args=[self.task1.id])
        self.client.force_login(other_user)
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 403)

    def test_reopen_task_view(self):
        """Test ReopenTaskView restores status and triggers refresh"""
        # First complete it
        self.task1.status = self.status_completed
        self.task1.previous_status = self.status_pending
        self.task1.save()
        
        url = reverse('lab:reopen_task', args=[self.task1.id])
        self.client.force_login(self.user)
        
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['HX-Trigger'], 'taskChanged')
        
        self.task1.refresh_from_db()
        self.assertEqual(self.task1.status, self.status_pending)
        self.assertIsNone(self.task1.previous_status)
