import logging
from django.core.management import BaseCommand
from ontologies.models import Ontology, Term, Synonym, CrossReference, Relationship, RelationshipType

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sync ontology from online resource'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ontology',
            dest='ontology',
            choices=['HP', 'MONDO', 'ONCOTREE'],
            help='Ontology Source',
        )

    def handle(self, *args, **options):
        try:
            import pronto
        except ImportError:
            self.stdout.write(self.style.ERROR(
                "The 'pronto' package is required for this command. "
                "Install it using: pip install pronto"
            ))
            return

        if options['ontology'] == 'HP':
            purl = 'http://purl.obolibrary.org/obo/hp.obo'
        elif options['ontology'] == 'MONDO':
            purl = 'http://purl.obolibrary.org/obo/mondo.obo'
        elif options['ontology'] == 'ONCOTREE':
            purl = 'http://purl.obolibrary.org/obo/ncit/ncit-oncotree.obo'
        else:
            self.stdout.write(self.style.ERROR(
                "Please specify an ontology with --ontology=HP|MONDO|ONCOTREE"
            ))
            return

        logger.info(f'Downloading {purl}...')
        self.stdout.write(f'Downloading {purl}...')
        
        try:
            data = pronto.Ontology(purl, timeout=10)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error downloading ontology: {str(e)}'))
            return

        # Get version - adapt to current pronto API
        try:
            # Try different ways to get the version
            if hasattr(data, 'metadata'):
                # Newer pronto versions
                version = data.metadata.data_version
            elif hasattr(data, 'meta'):
                # Older pronto versions
                version = data.meta.get('data_version', ["unknown"])[0]
            else:
                # Fallback
                version = "unknown_version"
                
            self.stdout.write(f"Found version: {version}")
        except Exception as e:
            version = "unknown_version"
            self.stdout.write(f"Could not determine version, using default: {version}. Error: {str(e)}")
        
        # Map ontology name to type id
        ontology_type_map = {'HP': 1, 'MONDO': 2, 'ONCOTREE': 3}
        ontology_type = ontology_type_map.get(options['ontology'])
        
        # Get or create the ontology
        ontology, created = Ontology.objects.get_or_create(
            type=ontology_type,
            label=version
        )

        if not created:
            self.stdout.write(f'Version {version} already exists')
            return

        self.stdout.write(f'Adding version: {version}')
        self.stdout.write('Adding terms...')

        # Store relationship data for later processing
        relations = []
        
        # Create the is_a relationship type
        is_a_relationship, _ = RelationshipType.objects.get_or_create(
            label='is_a',
            defaults={'slug': 'is-a'}
        )
        
        # First pass: Create all terms
        term_objects = {}  # Dictionary to store term objects by ID
        for term_id, term in data.items():
            try:
                # Extract alternate IDs - adapt to current pronto API
                alternate_ids = []
                if hasattr(term, 'alternate_ids'):
                    alternate_ids = term.alternate_ids
                elif hasattr(term, 'other') and 'alt_id' in term.other:
                    alternate_ids = term.other.get('alt_id', [])
                
                alt_ids_str = ",".join([
                    str(self._extract_id(alt_term))
                    for alt_term in alternate_ids
                ])
                
                # Get created_by and creation_date - adapt to current pronto API
                created_by = ""
                created_date = ""
                
                if hasattr(term, 'created_by'):
                    created_by = term.created_by
                elif hasattr(term, 'other') and 'created_by' in term.other:
                    created_by = term.other.get('created_by', [""])[0]
                    
                if hasattr(term, 'creation_date'):
                    created_date = term.creation_date
                elif hasattr(term, 'other') and 'creation_date' in term.other:
                    created_date = term.other.get('creation_date', [""])[0]
                
                # Get description from different possible attributes
                description = ""
                if hasattr(term, 'definition') and term.definition:
                    description = term.definition.value if hasattr(term.definition, 'value') else str(term.definition)
                elif hasattr(term, 'desc') and term.desc:
                    description = term.desc
                
                # Create the term
                term_obj = Term.objects.create(
                    ontology=ontology,
                    identifier=self._extract_id(term_id),
                    label=term.name if hasattr(term, 'name') and term.name else "",
                    description=description,
                    created_by=created_by,
                    created=created_date,
                    alternate_ids=alt_ids_str
                )
                
                # Store the term object for later relationship creation
                term_objects[term_id] = term_obj
                
                # Create synonyms - adapt to current pronto API
                if hasattr(term, 'synonyms'):
                    for synonym in term.synonyms:
                        if hasattr(synonym, 'scope') and hasattr(synonym, 'description'):
                            Synonym.objects.create(
                                term=term_obj,
                                description=synonym.description,
                                scope=self._get_scope_id(synonym.scope)
                            )
                        elif hasattr(synonym, 'scope') and hasattr(synonym, 'value'):
                            Synonym.objects.create(
                                term=term_obj,
                                description=synonym.value,
                                scope=self._get_scope_id(synonym.scope)
                            )
                
                # Create cross references - adapt to current pronto API
                xrefs = []
                if hasattr(term, 'xrefs'):
                    xrefs = term.xrefs
                elif hasattr(term, 'other') and 'xref' in term.other:
                    xrefs = term.other.get('xref', [])
                
                for xref in xrefs:
                    xref_str = xref.id
                    if ':' in xref_str:
                        xref_data = xref_str.split(':', 1)
                        
                        # Skip malformed xrefs
                        if len(xref_data) != 2 or xref_data[0].upper() == 'HTTP':
                            logger.warning(f'CrossReference: {xref_str} format not supported!')
                            continue
                        
                        CrossReference.objects.create(
                            term=term_obj,
                            source=xref_data[0],
                            source_value=xref_data[1]
                        )
            
            except Exception as e:
                logger.error(f'Error processing term {term_id}: {str(e)}')
                continue
        
        # Second pass: Create relationships
        self.stdout.write('Building relationships...')
        for term_id, term in data.items():
            try:
                if term_id not in term_objects:
                    continue
                    
                current_term = term_objects[term_id]
                
                # Add is_a relationships (superclasses)
                for parent in term.superclasses(distance=1):
                    if parent.id != term_id:  # Skip self-references
                        if parent.id in term_objects:
                            Relationship.objects.create(
                                type=is_a_relationship,
                                term=current_term,
                                related_term=term_objects[parent.id]
                            )
                            # self.stdout.write(f"Added is_a relationship: {term_id} -> {parent.id}")
                
                # Add other relationships
                if hasattr(term, 'relationships'):
                    for rel_type, related_terms in term.relationships.items():
                        rel_type_str = str(rel_type)
                        if "Relationship('" in rel_type_str:
                            rel_type_str = rel_type_str.replace("Relationship('", "").replace("')", "")
                        
                        # Skip is_a relationships as they're handled separately
                        if rel_type_str.lower() == 'is_a':
                            continue
                            
                        # Get or create relationship type
                        rel_type_obj, _ = RelationshipType.objects.get_or_create(
                            label=rel_type_str,
                            defaults={'slug': rel_type_str.lower().replace(' ', '-')}
                        )
                        
                        # Create relationships
                        for related_term in related_terms:
                            related_id = str(related_term.id) if hasattr(related_term, 'id') else str(related_term)
                            if related_id in term_objects:
                                Relationship.objects.create(
                                    type=rel_type_obj,
                                    term=current_term,
                                    related_term=term_objects[related_id]
                                )
                                self.stdout.write(f"Added {rel_type_str} relationship: {term_id} -> {related_id}")
            
            except Exception as e:
                logger.error(f'Error processing relationships for term {term_id}: {str(e)}')
                continue
        
        self.stdout.write(self.style.SUCCESS(
            f'Successfully imported {options["ontology"]} version {version}'
        ))
        
        # Print some statistics
        self.stdout.write(f"Terms created: {Term.objects.filter(ontology=ontology).count()}")
        self.stdout.write(f"Synonyms created: {Synonym.objects.filter(term__ontology=ontology).count()}")
        self.stdout.write(f"Cross-references created: {CrossReference.objects.filter(term__ontology=ontology).count()}")
        self.stdout.write(f"Relationship types: {RelationshipType.objects.count()}")
        self.stdout.write(f"Relationships created: {Relationship.objects.filter(term__ontology=ontology).count()}")

    def _extract_id(self, value):
        """Extract the ID part from an ontology term identifier"""
        value_str = str(value)
        return value_str.strip().split(':')[1] if ':' in value_str else value_str.strip()
    
    def _get_scope_id(self, scope):
        """Map scope string to integer ID"""
        scope_str = str(scope).upper()
        scope_map = {
            'EXACT': 1,
            'BROAD': 2,
            'NARROW': 3,
            'RELATED': 4,
            'ABBREVATION': 5
        }
        return scope_map.get(scope_str, None)
