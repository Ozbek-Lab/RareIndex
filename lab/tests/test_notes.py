from django.test import TestCase, Client, RequestFactory
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from lab.models import Note, Individual, Status
from lab.htmx_views import note_create, note_update, note_delete, note_list
import json

class NoteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.other_user = User.objects.create_user(username='otheruser', password='password')
        self.staff_user = User.objects.create_user(username='staffuser', password='password', is_staff=True)
        
        self.status = Status.objects.create(name="Active", created_by=self.user)
        self.individual = Individual.objects.create(
            full_name="John Doe", 
            created_by=self.user,
            status=self.status
        )
        self.client.login(username='testuser', password='password')
        
    def test_create_note(self):
        url = reverse('lab:note_create')
        data = {
            'content': 'Test Note Content',
            'content_type': 'lab.Individual',
            'object_id': self.individual.id,
            'private': 'false'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Note.objects.filter(content='Test Note Content').exists())
        self.assertIn(b'Test Note Content', response.content)

    def test_create_private_note(self):
        url = reverse('lab:note_create')
        data = {
            'content': 'Secret Note',
            'content_type': 'lab.Individual',
            'object_id': self.individual.id,
            'private': 'true'
        }
        self.client.post(url, data)
        note = Note.objects.get(content='Secret Note')
        self.assertEqual(note.private_owner, self.user)
        
        # Other user should not see it
        self.client.login(username='otheruser', password='password')
        response = self.client.get(reverse('lab:note_list'), {
            'content_type': 'lab.Individual',
            'object_id': self.individual.id
        })
        self.assertNotIn(b'Secret Note', response.content)

    def test_update_note_permission(self):
        # Create note by user
        note = Note.objects.create(
            content='Original',
            user=self.user,
            content_object=self.individual
        )
        
        url = reverse('lab:note_update', args=[note.id])
        
        # User can update
        response = self.client.post(url, {'content': 'Updated'})
        self.assertEqual(response.status_code, 200)
        note.refresh_from_db()
        self.assertEqual(note.content, 'Updated')
        
        # Other user cannot update
        self.client.login(username='otheruser', password='password')
        response = self.client.post(url, {'content': 'Hacked'})
        self.assertEqual(response.status_code, 403)
        note.refresh_from_db()
        self.assertEqual(note.content, 'Updated') 

    def test_delete_note(self):
        note = Note.objects.create(
            content='To Delete',
            user=self.user,
            content_object=self.individual
        )
        url = reverse('lab:note_delete', args=[note.id])
        
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Note.objects.filter(id=note.id).exists())

    def test_note_count(self):
        Note.objects.create(content='Note 1', user=self.user, content_object=self.individual)
        Note.objects.create(content='Note 2', user=self.user, content_object=self.individual)
        
        url = reverse('lab:note_count')
        response = self.client.get(url, {
            'content_type': 'lab.Individual',
            'object_id': self.individual.id
        })
        self.assertIn(b'2 Notes', response.content)

    def test_detail_view_integration(self):
        # Create a note
        Note.objects.create(content='Integration Note', user=self.user, content_object=self.individual)
        
        # Get the detail view which includes the note list
        url = reverse('lab:individual_detail', args=[self.individual.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Integration Note', response.content)
        self.assertIn(b'notes-list', response.content) # Helper class still exists wrapping the list
