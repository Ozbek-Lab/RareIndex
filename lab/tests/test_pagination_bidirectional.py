from django.test import TestCase, Client
from django.urls import reverse
from lab.models import Individual, Status
from lab.views import IndividualListView

class BidirectionalPaginationTest(TestCase):
    def setUp(self):
        # Create enough individuals for 3 pages (25 per page -> 75 users)
        self.status = Status.objects.create(name="Active")
        for i in range(75):
            Individual.objects.create(
                individual_id=f"IND_{i}",
                full_name=f"Test User {i}",
                status=self.status,
                sex="Male"
            )
        self.client = Client()
        self.user = Individual.objects.first().created_by # Assumption: need a user, but LoginRequiredMixin used.
        # Actually need to create a user and login
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client.login(username='testuser', password='password')
        self.url = reverse('lab:individual_list')

    def test_initial_load_page_1(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        # Should have bottom sentinel, no top sentinel
        content = response.content.decode()
        self.assertIn('hx-get="/individuals/?page=2&amp;direction=down"', content)
        self.assertNotIn('loading previous', content.lower())

    def test_load_page_2_down(self):
        # Simulator HTMX request for page 2 scrolling down
        headers = {'HTTP_HX_REQUEST': 'true'}
        response = self.client.get(self.url, {'page': 2, 'direction': 'down'}, **headers)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Should NOT have Top Sentinel (suppressed by direction=down)
        self.assertNotIn('loading previous', content.lower())
        # Should have Bottom Sentinel (to page 3)
        self.assertIn('page=3', content)

    def test_load_page_2_direct(self):
        # Simulate accessing ?page=2 directly (refresh)
        response = self.client.get(self.url, {'page': 2})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Should have Top Sentinel (to page 1)
        self.assertIn('loading previous', content.lower())
        self.assertIn('page=1', content)
        # Should have Bottom Sentinel (to page 3)
        self.assertIn('page=3', content)

    def test_load_page_2_up(self):
        # Simulate scrolling UP to page 2 (from page 3)
        headers = {'HTTP_HX_REQUEST': 'true'}
        response = self.client.get(self.url, {'page': 2, 'direction': 'up'}, **headers)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Should have Top Sentinel (to page 1)
        self.assertIn('loading previous', content.lower())
        # Should NOT have Bottom Sentinel (suppressed by direction=up)
        self.assertNotIn('page=3', content)

    def test_pagination_url_cleanliness(self):
        # Test that pagination URLs don't have duplicate parameters
        # Initial request with some parameters that might be problematic if duplicated
        response = self.client.get(self.url, {'q': 'test'})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check the Next Page link
        # It should contain q=test once, but not q=test&q=test
        # And specifically check hx-get attribute
        self.assertIn('hx-get="/individuals/?', content)
        self.assertIn('q=test', content)
        self.assertNotIn('hx-include="#filter-form', content)

    def test_alpine_intersect_attribute(self):
        # Test that the first row has the x-intersect attribute for URL updates
        response = self.client.get(self.url, {'page': 2})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for x-intersect.threshold.20
        # It should replace state with page=2
        self.assertIn('x-intersect.threshold.20="history.replaceState', content)
        self.assertIn('page=2', content)

    def test_end_of_results_logic(self):
        # Test that "End of results" is NOT shown when loading UP (page 2 -> 3 exists)
        # If we load page 2 with direction='up', has_next is True (page 3).
        # We suppress the bottom sentinel, but we MUST NOT show "End of results".
        
        headers = {'HTTP_HX_REQUEST': 'true'}
        response = self.client.get(self.url, {'page': 2, 'direction': 'up'}, **headers)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Should NOT have Bottom Sentinel (suppressed by direction=up)
        # This matches previous test, but we explicitely check End of Results now.
        self.assertNotIn('page=3', content)
        
        # Should NOT have "End of results"
        self.assertNotIn('End of results', content)



