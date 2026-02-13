from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User, Permission
from lab.models import Individual, Sample, Test, SampleType, TestType, Status, IdentifierType, CrossIdentifier, Project, Institution
import csv
import io

class IndividualExportTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.user.user_permissions.add(Permission.objects.get(codename='view_sensitive_data'))
        self.client.login(username='testuser', password='password')
        
        # Setup basic data
        self.status = Status.objects.create(name="Active", created_by=self.user)
        self.sample_type = SampleType.objects.create(name="Blood", created_by=self.user)
        self.test_type = TestType.objects.create(name="WGS", created_by=self.user)
        
        # Create Individual with Sample and Test
        self.individual = Individual.objects.create(
            full_name="John Doe",
            tc_identity=12345678901,
            birth_date="2000-01-01",
            sex="male",
            status=self.status,
            created_by=self.user
        )
        
        self.sample = Sample.objects.create(
            individual=self.individual,
            sample_type=self.sample_type,
            status=self.status,
            receipt_date="2023-01-01",
            isolation_by=self.user,
            created_by=self.user
        )
        
        self.test = Test.objects.create(
            sample=self.sample,
            test_type=self.test_type,
            status=self.status,
            performed_date="2023-01-05",
            created_by=self.user
        )
        
        # Create Individual without Sample
        self.individual_empty = Individual.objects.create(
            full_name="Jane Empty",
            status=self.status,
            created_by=self.user
        )

    def test_export_access(self):
        url = reverse('lab:individual_export')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')

    def test_export_content(self):
        url = reverse('lab:individual_export')
        response = self.client.get(url)
        
        content = response.content.decode('utf-8-sig') # Handle BOM
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        
        # Header check
        self.assertEqual(len(rows[0]), 26) # 26 columns based on implementation
        self.assertIn("Özbek Lab. ID", rows[0])
        
        # Data check
        # John Doe Row
        john_rows = [r for r in rows if r[2] == "John Doe"]
        self.assertEqual(len(john_rows), 1)
        self.assertEqual(john_rows[0][18], "Blood") # Sample Type
        self.assertEqual(john_rows[0][22], "WGS") # Test Name

        # Jane Empty Row
        jane_rows = [r for r in rows if r[2] == "Jane Empty"]
        self.assertEqual(len(jane_rows), 1)
        self.assertEqual(jane_rows[0][18], "") # No sample type

    def test_export_filtering(self):
        url = reverse('lab:individual_export')
        response = self.client.get(url, {'search': 'John'})
        
        content = response.content.decode('utf-8-sig')
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        
        # Should only have header and John
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][2], "John Doe")
