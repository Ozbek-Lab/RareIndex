from django.core.management.base import BaseCommand, CommandError
from lab.models import Project, CrossIdentifier, IdentifierType

class Command(BaseCommand):
    help = 'Adds individuals to a project by identifier value.'

    def add_arguments(self, parser):
        parser.add_argument('project_name', type=str, help='The name of the project to add individuals to.')
        parser.add_argument(
            'identifier_values',
            nargs='+',
            type=str,
            help='A list of identifier values to add to the project.',
        )
        parser.add_argument(
            '--id-type',
            dest='id_type',
            type=str,
            default=None,
            help='Optional IdentifierType name to restrict the lookup (e.g. RareBoost, Biobank).',
        )

    def handle(self, *args, **options):
        project_name = options['project_name']
        identifier_values = options['identifier_values']
        id_type_name = options.get('id_type')

        try:
            project = Project.objects.get(name=project_name)
        except Project.DoesNotExist:
            raise CommandError(f'Project "{project_name}" does not exist.')

        id_type = None
        if id_type_name:
            id_type = IdentifierType.objects.filter(name__iexact=id_type_name).first()
            if not id_type:
                self.stdout.write(
                    self.style.WARNING(
                        f'IdentifierType "{id_type_name}" was not found; searching all identifier types instead.'
                    )
                )

        for raw_value in identifier_values:
            value = str(raw_value).strip()
            if not value:
                self.stdout.write(self.style.WARNING("Skipped an empty identifier value."))
                continue

            matches = CrossIdentifier.objects.filter(id_value=value)
            if id_type:
                matches = matches.filter(id_type=id_type)
            matches = matches.select_related("individual", "id_type")
            matching_links = list(matches)

            if not matching_links and id_type is not None:
                fallback_matches = CrossIdentifier.objects.filter(id_value=value).select_related("individual", "id_type")
                matching_links = list(fallback_matches)
                if matching_links:
                    self.stdout.write(
                        self.style.WARNING(
                            f'No "{id_type.name}" match for "{value}". Added matches from other identifier types instead.'
                        )
                    )

            if not matching_links:
                self.stdout.write(self.style.WARNING(f'Could not find any individual for identifier "{value}".'))
                continue

            unique_individuals = []
            seen_ids = set()
            matched_types = set()
            for link in matching_links:
                matched_types.add(link.id_type.name if link.id_type else "unknown")
                if link.individual_id in seen_ids:
                    continue
                unique_individuals.append(link.individual)
                seen_ids.add(link.individual_id)

            if len(unique_individuals) > 1:
                id_type_label = id_type.name if id_type else "any identifier type"
                self.stdout.write(
                    self.style.WARNING(
                        f'Identifier "{value}" matched {len(unique_individuals)} individuals for {id_type_label}; adding all of them.'
                    )
                )
            elif len(matched_types) > 1 and id_type is None:
                self.stdout.write(
                    self.style.WARNING(
                        f'Identifier "{value}" was found under multiple identifier types: {", ".join(sorted(matched_types))}.'
                    )
                )

            for individual in unique_individuals:
                project.individuals.add(individual)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Added "{individual.full_name}" to project "{project_name}" using identifier "{value}".'
                    )
                )
