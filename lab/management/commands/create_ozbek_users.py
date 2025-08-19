from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth.models import User, Group

class Command(BaseCommand):
    help = 'Create groups and Ozbek users'

    def handle(self, *args, **options):
        call_command('create_groups')

        if not User.objects.filter(username='admin').exists():
            user = User.objects.create_superuser(username='admin', password='admin')
            admin_group = Group.objects.get(name='RareIndex Admin')
            user.groups.add(admin_group)
        if not User.objects.filter(username='pleb').exists():
            user = User.objects.create_user(username='pleb', password='pleb')
            pleb_group = Group.objects.get(name='Pleb')
            user.groups.add(pleb_group)
        if not User.objects.filter(username='emre.ozzeybek').exists():
            user = User.objects.create_superuser(username='emre.ozzeybek', password='Emre', email='emre.ozzeybek@ibg.edu.tr')
            admin_group = Group.objects.get(name='RareIndex Admin')
            user.groups.add(admin_group)
        if not User.objects.filter(username='baris.salman').exists():
            user = User.objects.create_superuser(username='baris.salman', password='Baris', email='baris.salman@ibg.edu.tr')
            admin_group = Group.objects.get(name='RareIndex Admin')
            user.groups.add(admin_group)
        if not User.objects.filter(username='ayca.yigit').exists():
            user = User.objects.create_superuser(username='ayca.yigit', password='Ayça', email='ayca.yigit@ibg.edu.tr')
            sensitive_group = Group.objects.get(name='RareIndex User(Sensitive Data)')
            user.groups.add(sensitive_group)
        if not User.objects.filter(username='mert.pekerbas').exists():
            user = User.objects.create_superuser(username='mert.pekerbas', password='Mert', email='mert.pekerbas@ibg.edu.tr')
            sensitive_group = Group.objects.get(name='RareIndex User(Sensitive Data)')
            user.groups.add(sensitive_group)
        if not User.objects.filter(username='kutay.bulut').exists():
            user = User.objects.create_superuser(username='kutay.bulut', password='Kutay', email='kutay.bulut@ibg.edu.tr')
            user_group = Group.objects.get(name='RareIndex User')
            user.groups.add(user_group)
        if not User.objects.filter(username='gennext').exists():
            user = User.objects.create_superuser(username='gennext', password='gennext')
            gennext_group = Group.objects.get(name='Gennext')
            user.groups.add(gennext_group)
        if not User.objects.filter(username='ezgi.karaca').exists():
            user = User.objects.create_superuser(username='ezgi.karaca', password='Ezgi', email='ezgi.karaca@ibg.edu.tr')
            collaborator_group = Group.objects.get(name='Collaborator')
            user.groups.add(collaborator_group)
