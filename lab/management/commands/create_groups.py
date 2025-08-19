from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group


class Command(BaseCommand):
    help = 'Create groups'

    def handle(self, *args, **options):
        if not Group.objects.filter(name='RareIndex Admin').exists():
            Group.objects.get_or_create(name='RareIndex Admin')
        if not Group.objects.filter(name='RareIndex User').exists():
            Group.objects.get_or_create(name='RareIndex User')
        if not Group.objects.filter(name='RareIndex User(Sensitive Data)').exists():
            Group.objects.get_or_create(name='RareIndex User(Sensitive Data)')
        if not Group.objects.filter(name='RareIndex Lab').exists():
            Group.objects.get_or_create(name='RareIndex Lab')
        if not Group.objects.filter(name='Collaborator').exists():
            Group.objects.get_or_create(name='Collaborator')
        if not Group.objects.filter(name='Pleb').exists():
            Group.objects.get_or_create(name='Pleb')
        if not Group.objects.filter(name='Gennext').exists():
            Group.objects.get_or_create(name='Gennext')

        