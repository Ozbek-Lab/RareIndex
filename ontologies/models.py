from django.core.validators import validate_comma_separated_integer_list
from django.db import models
from django.utils.translation import gettext_lazy as _

from django.contrib.auth.models import User

# Choices for ontology types and synonym scopes
ONTOLOGY_CHOICES = (
    (1, 'HP'),     # Human Phenotype Ontology
    (2, 'MONDO'),  # Mondo Disease Ontology
    (3, 'ONCOTREE'),  # OncoTree Ontology
)

SYNONYM_SCOPE_CHOICES = (
    (1, 'EXACT'),
    (2, 'BROAD'),
    (3, 'NARROW'),
    (4, 'RELATED'),
    (5, 'ABBREVATION'),
)

class Ontology(models.Model):
    """Model to keep track of Ontology and version."""
    type = models.PositiveSmallIntegerField(choices=ONTOLOGY_CHOICES)
    label = models.CharField(max_length=100)
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Ontology')
        verbose_name_plural = _('Ontologies')

    def __str__(self):
        return f'{self.get_type_display()} {self.label}'


class Term(models.Model):
    """Ontology Terms."""
    ontology = models.ForeignKey('Ontology', on_delete=models.CASCADE)
    identifier = models.CharField(max_length=25, db_index=True)
    label = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    alternate_ids = models.CharField(
        max_length=2500,
        blank=True,
        validators=[validate_comma_separated_integer_list]
    )
    created_by = models.CharField(max_length=50, blank=True, null=True)
    created = models.CharField(max_length=25, blank=True, null=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Term')
        verbose_name_plural = _('Terms')
        indexes = [
            models.Index(fields=['ontology', 'identifier']),
        ]

    def __str__(self):
        return self.term

    @property
    def source(self):
        return self.ontology.get_type_display()

    @property
    def term(self):
        if self.source == 'MONDO':
            return f'MONDO:{self.identifier}'
        elif self.source == 'HP':
            return f'HP:{self.identifier}'
        elif self.source == 'ONCOTREE':
            return f'NCIT:{self.identifier}'

    @property
    def url(self):
        if self.source == 'MONDO':
            return f'https://monarchinitiative.org/disease/{self.term}'
        elif self.source == 'HP':
            return f'http://compbio.charite.de/hpoweb/showterm?id={self.term}'
        elif self.source == 'ONCOTREE':
            return f'http://purl.obolibrary.org/obo/NCIT_{self.identifier}'


class Synonym(models.Model):
    """Synonyms for ontology terms."""
    term = models.ForeignKey(
        'Term',
        related_name='synonyms',
        on_delete=models.CASCADE,
    )
    description = models.TextField(blank=True)
    scope = models.PositiveSmallIntegerField(choices=SYNONYM_SCOPE_CHOICES, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Synonym')
        verbose_name_plural = _('Synonyms')

    def __str__(self):
        return str(self.term)


class CrossReference(models.Model):
    """Cross-references for ontology terms."""
    term = models.ForeignKey(
        'Term',
        related_name='xrefs',
        on_delete=models.CASCADE,
    )
    source = models.CharField(max_length=25, db_index=True)
    source_value = models.CharField(max_length=255)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Cross Reference')
        verbose_name_plural = _('Cross References')

    def __str__(self):
        return str(self.term)


class RelationshipType(models.Model):
    """Types of relationships between terms."""
    label = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=255, blank=True)
    slug = models.SlugField(unique=True)
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Relationship Type')
        verbose_name_plural = _('Relationship Types')

    def __str__(self):
        return self.label


class Relationship(models.Model):
    """Relationships between ontology terms."""
    type = models.ForeignKey(
        'RelationshipType',
        related_name='relationships',
        on_delete=models.CASCADE,
    )
    term = models.ForeignKey(
        'Term',
        related_name='relationships',
        on_delete=models.CASCADE,
    )
    related_term = models.ForeignKey(
        'Term',
        related_name='relationships_related',
        on_delete=models.CASCADE,
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Relationship')
        verbose_name_plural = _('Relationships')

    def __str__(self):
        return str(self.term)
