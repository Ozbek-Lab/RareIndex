from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from lab.models import Family, Individual, IdentifierType, CrossIdentifier, Status
import json

class FamilyCreateViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpassword")
        self.client.force_login(self.user)
        self.url = reverse('lab:create_family')
        self.status = Status.objects.create(name="Active", created_by=self.user)
        self.id_type = IdentifierType.objects.create(name="Passport", created_by=self.user)

    def test_create_family_with_relationships_and_cross_ids(self):
        """
        Verify that we can create a family with 3 individuals, 
        link them as Father/Mother/Child using indices, 
        and add cross identifiers.
        """
        data = {
            # Family Form
            'family_id': 'FAM-TEST-001',
            'description': 'Test Family',
            'is_consanguineous': True, 
            
            # Management Form
            'individuals-TOTAL_FORMS': '3',
            'individuals-INITIAL_FORMS': '0',
            'individuals-MIN_NUM_FORMS': '0',
            'individuals-MAX_NUM_FORMS': '1000',
            
            # Form 0: Father
            'individuals-0-full_name': 'Father Doe',
            'individuals-0-sex': 'male',
            'individuals-0-birth_date': '1980-01-01',
            'individuals-0-status': self.status.id,
            'individuals-0-is_index': False,
            'individuals-0-is_affected': False,
            # Empty refs
            'individuals-0-father_ref': '',
            'individuals-0-mother_ref': '',
            
            # Form 1: Mother
            'individuals-1-full_name': 'Mother Doe',
            'individuals-1-sex': 'female',
            'individuals-1-birth_date': '1982-01-01',
            'individuals-1-status': self.status.id,
            'individuals-1-is_index': False,
            'individuals-1-is_affected': False,
            
            # Form 2: Child
            'individuals-2-full_name': 'Child Doe',
            'individuals-2-sex': 'male',
            'individuals-2-birth_date': '2005-01-01',
            'individuals-2-status': self.status.id,
            'individuals-2-is_index': True,
            'individuals-2-is_affected': True,
            # Refs to 0 and 1
            'individuals-2-father_ref': '0',
            'individuals-2-mother_ref': '1',
            'individuals-2-cross_identifiers_json': json.dumps([
                {'type_id': self.id_type.id, 'value': 'P12345'}
            ]),
            'individuals-2-note_content': 'Initial Note',
        }
        
        response = self.client.post(self.url, data, follow=True)
        
        # Check success (redirect to individuals list per view)
        if response.status_code != 302 and response.status_code != 200:
             # Should be 302, but if 200 it failed. AssertRedirects checks strictly.
             pass
        
        if response.status_code != 302:
             if 'form' in response.context:
                 print("Form Errors:", response.context['form'].errors)
             if 'individual_formset' in response.context:
                 print("Formset Errors:", response.context['individual_formset'].errors)
                 print("Formset Non-form Errors:", response.context['individual_formset'].non_form_errors())

        self.assertRedirects(response, reverse('lab:individual_list'))
        
        # Verify Family Created
        fam = Family.objects.filter(family_id='FAM-TEST-001').first()
        self.assertIsNotNone(fam)
        if fam.is_consanguineous is not None and not isinstance(fam.is_consanguineous, bool):
             # Handle weird widget output if needed, but ModelForm usually handles it.
             pass
        
        # Verify Individuals
        try:
            father = Individual.objects.get(full_name='Father Doe')
            mother = Individual.objects.get(full_name='Mother Doe')
            child = Individual.objects.get(full_name='Child Doe')
        except Individual.DoesNotExist:
            self.fail("Individuals were not created")
            
        self.assertEqual(child.father, father)
        self.assertEqual(child.mother, mother)
        self.assertEqual(child.family, fam)
        
        # Verify Cross IDs
        xid = CrossIdentifier.objects.filter(individual=child).first()
        self.assertIsNotNone(xid)
        self.assertEqual(xid.id_value, 'P12345')
        self.assertEqual(xid.id_type, self.id_type)
        
        # Verify Notes
        notes = child.notes.all()
        self.assertTrue(notes.exists())
        self.assertEqual(notes.first().content, 'Initial Note')
