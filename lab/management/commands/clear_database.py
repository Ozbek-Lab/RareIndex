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
    Individual,
    Sample,
    Test,
    AnalysisType,
    Analysis,
    IdentifierType,
    CrossIdentifier,
    ImportFieldState,
)
from lab import history_notifications
from simple_history.signals import post_create_historical_record


class Command(BaseCommand):
    help = (
        "Clear all entries from the database except the superuser and default statuses"
    )

    def handle(self, *args, **options):
        self.stdout.write("Clearing database...")

        # Delete all data in reverse order of dependencies
        self.stdout.write("Deleting ImportFieldState entries...")
        ImportFieldState.objects.all().delete()

        self.stdout.write("Deleting Analysis entries...")
        Analysis.objects.all().delete()

        self.stdout.write("Deleting AnalysisType entries...")
        AnalysisType.objects.all().delete()

        self.stdout.write("Deleting Test entries...")
        Test.objects.all().delete()

        self.stdout.write("Deleting Sample entries...")
        Sample.objects.all().delete()

        # First nullify the self-referential fields and related FKs
        self.stdout.write("Nullifying Individual self-references...")
        Individual.objects.all().update(mother=None, father=None)
        self.stdout.write("Nullifying Sample.individual...")
        Sample.objects.all().update(individual=None)
        self.stdout.write("Nullifying Test.sample...")
        Test.objects.all().update(sample=None)
        self.stdout.write("Nullifying Analysis.test...")
        Analysis.objects.all().update(test=None)
        # Nullifying CrossIdentifier.individual is not possible due to NOT NULL constraint; delete instead
        self.stdout.write("Deleting CrossIdentifier entries...")
        CrossIdentifier.objects.all().delete()

        # Temporarily disconnect history notification signal to avoid errors during destructive delete
        post_create_historical_record.disconnect(
            receiver=history_notifications.notify_on_history
        )
        try:
            # Delete all Task objects before deleting Project objects
            self.stdout.write("Deleting Task entries...")
            Task.objects.all().delete()
            self.stdout.write("Deleting Project entries...")
            Project.objects.all().delete()

            # Delete all objects that reference Status before deleting Status itself
            self.stdout.write("Deleting Analysis entries...")
            Analysis.objects.all().delete()
            self.stdout.write("Deleting Test entries...")
            Test.objects.all().delete()
            self.stdout.write("Deleting Sample entries...")
            Sample.objects.all().delete()
            self.stdout.write("Deleting Individual entries...")
            Individual.objects.all().delete()
        finally:
            # Reconnect the signal after deletion
            post_create_historical_record.connect(
                receiver=history_notifications.notify_on_history
            )

        # Preserve default statuses
        default_statuses = ["Registered", "Completed", "In Progress"]
        self.stdout.write("Preserving default statuses...")
        Status.objects.exclude(name__in=default_statuses).delete()

        self.stdout.write("Deleting Institution entries...")
        Institution.objects.all().delete()

        self.stdout.write("Deleting SampleType entries...")
        SampleType.objects.all().delete()

        self.stdout.write("Deleting TestType entries...")
        TestType.objects.all().delete()

        # Delete IdentifierTypes after CrossIdentifiers
        self.stdout.write("Deleting IdentifierType entries...")
        IdentifierType.objects.all().delete()

        self.stdout.write("Deleting Note entries...")
        Note.objects.all().delete()

        self.stdout.write("Deleting Project entries...")
        Project.objects.all().delete()

        # Delete objects with required User references before nullifying others
        self.stdout.write("Deleting objects with required User references...")
        Family.objects.all().delete()  # Family has NOT NULL created_by
        Status.objects.all().delete()  # Status has NOT NULL created_by
        Sample.objects.all().delete()  # Sample has NOT NULL created_by
        Test.objects.all().delete()  # Test has NOT NULL created_by
        Analysis.objects.all().delete()  # Analysis has NOT NULL created_by
        Project.objects.all().delete()  # Project has NOT NULL created_by
        Note.objects.all().delete()  # Note has NOT NULL created_by
        Institution.objects.all().delete()  # Institution has NOT NULL created_by
        SampleType.objects.all().delete()  # SampleType has NOT NULL created_by
        TestType.objects.all().delete()  # TestType has NOT NULL created_by
        AnalysisType.objects.all().delete()  # AnalysisType has NOT NULL created_by
        IdentifierType.objects.all().delete()  # IdentifierType has NOT NULL created_by
        CrossIdentifier.objects.all().delete()  # CrossIdentifier has NOT NULL created_by
        Individual.objects.all().delete()  # Individual has NOT NULL created_by

        # Keep superuser, delete other users
        self.stdout.write("Deleting non-superuser User entries...")
        User.objects.filter(is_superuser=False).delete()

        self.stdout.write(self.style.SUCCESS("Successfully cleared database"))
