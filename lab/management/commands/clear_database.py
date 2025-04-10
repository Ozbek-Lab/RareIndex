from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from lab.models import (
    Task,
    Project,
    Note,
    TestType,
    SampleType,
    Institution,
    Family,
    Status,
    StatusLog,
    Individual,
    Sample,
    Test,
    AnalysisType,
    Analysis
)

class Command(BaseCommand):
    help = 'Clear all entries from the database except the superuser'

    def handle(self, *args, **options):
        self.stdout.write('Clearing database...')
        
        # Delete all data in reverse order of dependencies
        self.stdout.write('Deleting Analysis entries...')
        Analysis.objects.all().delete()
        
        self.stdout.write('Deleting AnalysisType entries...')
        AnalysisType.objects.all().delete()
        
        self.stdout.write('Deleting Test entries...')
        Test.objects.all().delete()
        
        self.stdout.write('Deleting Sample entries...')
        Sample.objects.all().delete()
        
        # First nullify the self-referential fields
        self.stdout.write('Nullifying Individual self-references...')
        Individual.objects.all().update(mother=None, father=None)
        
        self.stdout.write('Deleting Individual entries...')
        Individual.objects.all().delete()
        
        self.stdout.write('Deleting Family entries...')
        Family.objects.all().delete()
        
        self.stdout.write('Deleting StatusLog entries...')
        StatusLog.objects.all().delete()
        
        self.stdout.write('Deleting Status entries...')
        Status.objects.all().delete()
        
        self.stdout.write('Deleting Institution entries...')
        Institution.objects.all().delete()
        
        self.stdout.write('Deleting SampleType entries...')
        SampleType.objects.all().delete()
        
        self.stdout.write('Deleting TestType entries...')
        TestType.objects.all().delete()
        
        self.stdout.write('Deleting Note entries...')
        Note.objects.all().delete()
        
        self.stdout.write('Deleting Task entries...')
        Task.objects.all().delete()
        
        self.stdout.write('Deleting Project entries...')
        Project.objects.all().delete()
        
        # Keep superuser, delete other users
        self.stdout.write('Deleting non-superuser User entries...')
        User.objects.filter(is_superuser=False).delete()
        
        self.stdout.write(self.style.SUCCESS('Successfully cleared database')) 