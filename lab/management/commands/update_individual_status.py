from django.core.management.base import BaseCommand, CommandError
from lab.models import Individual, Status, CrossIdentifier, IdentifierType

class Command(BaseCommand):
    help = 'Updates the status of specified individuals.'

    def add_arguments(self, parser):
        parser.add_argument('status_name', type=str, help='The name of the status to set for the individuals.')
        parser.add_argument('individual_ids', nargs='+', type=str, help='A list of IDs for the individuals to update.')
        parser.add_argument(
            '--id_type',
            type=str,
            default='RareBoost',
            help='The type of ID being provided (e.g., RareBoost, Biobank). Defaults to RareBoost.'
        )

    def handle(self, *args, **options):
        status_name = options['status_name']
        individual_ids = options['individual_ids']
        id_type_name = options['id_type']

        try:
            new_status = Status.objects.get(name__iexact=status_name)
        except Status.DoesNotExist:
            raise CommandError(f'Status with name "{status_name}" does not exist.')

        try:
            identifier_type = IdentifierType.objects.get(name=id_type_name)
        except IdentifierType.DoesNotExist:
            raise CommandError(f'IdentifierType "{id_type_name}" does not exist. Please create it first.')

        for individual_id in individual_ids:
            try:
                cross_identifier = CrossIdentifier.objects.get(id_type=identifier_type, id_value=individual_id)
                individual = cross_identifier.individual
                individual.status = new_status
                individual.save()
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully updated status for individual with {id_type_name} ID "{individual_id}" to "{status_name}".'
                ))
            except CrossIdentifier.DoesNotExist:
                self.stdout.write(self.style.WARNING(
                    f'Individual with {id_type_name} ID "{individual_id}" not found.'
                ))
