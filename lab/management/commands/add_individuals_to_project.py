from django.core.management.base import BaseCommand, CommandError
from lab.models import Project, Individual, CrossIdentifier, IdentifierType

class Command(BaseCommand):
    help = 'Adds individuals to a project by their RareBoost IDs.'

    def add_arguments(self, parser):
        parser.add_argument('project_name', type=str, help='The name of the project to add individuals to.')
        parser.add_argument('rareboost_ids', nargs='+', type=str, help='A list of RareBoost IDs of the individuals to add.')

    def handle(self, *args, **options):
        project_name = options['project_name']
        rareboost_ids = options['rareboost_ids']

        try:
            project = Project.objects.get(name=project_name)
        except Project.DoesNotExist:
            raise CommandError(f'Project "{project_name}" does not exist.')

        try:
            rareboost_id_type = IdentifierType.objects.get(name="RareBoost")
        except IdentifierType.DoesNotExist:
            raise CommandError('"RareBoost" IdentifierType does not exist. Please create it first.')

        for rb_id in rareboost_ids:
            try:
                cross_identifier = CrossIdentifier.objects.get(id_type=rareboost_id_type, id_value=rb_id)
                individual = cross_identifier.individual
                project.individuals.add(individual)
                self.stdout.write(self.style.SUCCESS(f'Successfully added individual with RareBoost ID "{rb_id}" to project "{project_name}".'))
            except CrossIdentifier.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'Could not find an individual with RareBoost ID "{rb_id}".'))
