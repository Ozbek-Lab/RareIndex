from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import RegexValidator
from simple_history.models import HistoricalRecords
from taggit.managers import TaggableManager
from lab.models import Analysis, Individual, HistoryMixin, TaggedStatus


VARIANT_TYPE_DEFINITIONS = (
    {"key": "snv", "value": "SNV", "label": "SNV", "relation": "snv"},
    {"key": "delins", "value": "delins", "label": "Delins", "relation": "delins"},
    {"key": "cnv", "value": "CNV", "label": "CNV", "relation": "cnv"},
    {"key": "sv", "value": "SV", "label": "SV", "relation": "sv"},
    {"key": "repeat", "value": "Repeat", "label": "Repeat", "relation": "repeat"},
)

VARIANT_TYPE_CHOICES = tuple(
    (definition["value"], definition["label"])
    for definition in VARIANT_TYPE_DEFINITIONS
)
VARIANT_CREATE_TYPE_CHOICES = tuple(
    (definition["key"], definition["label"])
    for definition in VARIANT_TYPE_DEFINITIONS
)
VARIANT_TYPE_RELATION_LOOKUPS = {
    definition["value"]: definition["relation"]
    for definition in VARIANT_TYPE_DEFINITIONS
}


def normalize_variant_type_value(value):
    text = str(value or "").strip()
    for definition in VARIANT_TYPE_DEFINITIONS:
        aliases = {
            definition["key"].lower(),
            definition["value"].lower(),
            definition["label"].lower(),
        }
        if text.lower() in aliases:
            return definition["value"]
    return text


def normalize_chromosome(value):
    text = str(value or "").strip()
    if not text:
        return text

    suffix = text[3:] if text.lower().startswith("chr") else text
    if suffix.upper() == "MT":
        suffix = "M"
    elif suffix.upper() in {"X", "Y", "M"}:
        suffix = suffix.upper()
    return f"chr{suffix}"


class Variant(HistoryMixin, models.Model):
    """Base class for all variant types"""
    assembly_version = models.CharField(max_length=10, default="hg38")
    chromosome = models.CharField(max_length=10)
    start = models.IntegerField()
    end = models.IntegerField()
    
    # Linkage
    individual = models.ForeignKey(
        Individual,
        on_delete=models.PROTECT,
        related_name="variants",
    )
    analysis = models.ForeignKey(
        Analysis,
        on_delete=models.PROTECT,
        related_name="found_variants",
        null=True,
        blank=True,
    )
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = GenericRelation("lab.Note")
    tasks = GenericRelation("lab.Task")
    genes = models.ManyToManyField("Gene", related_name="variants", blank=True)
    history = HistoricalRecords(inherit=True)

    class Meta:
        ordering = ["chromosome", "start"]

    def __str__(self):
        return self.display_name

    statuses = TaggableManager(through=TaggedStatus, blank=True, verbose_name="Statuses")

    ZYGOSITY_CHOICES = [
        ("het", "Heterozygous"),
        ("hom", "Homozygous"),
        ("hemi", "Hemizygous"),
        ("hetpl", "Heteroplasmy"), #Check if chromosome is "MT"
        ("homoplasmy", "Homoplasmy"), #Check if chromosome is "MT"
        ("unknown", "Unknown"),
    ]
    zygosity = models.CharField(max_length=20, choices=ZYGOSITY_CHOICES)

    def save(self, *args, **kwargs):
        if self.chromosome:
            self.chromosome = normalize_chromosome(self.chromosome)
        super().save(*args, **kwargs)

    def _subtype_data(self):
        cached = getattr(self, "_variant_subtype_cache", None)
        if cached is not None:
            return cached

        model_name = self._meta.model_name
        for definition in VARIANT_TYPE_DEFINITIONS:
            relation = definition["relation"]
            if model_name == relation:
                subtype_data = (definition, self)
                break
            try:
                subtype = getattr(self, relation)
            except (ObjectDoesNotExist, AttributeError):
                continue
            else:
                subtype_data = (definition, subtype)
                break
        else:
            subtype_data = (None, self)

        self._variant_subtype_cache = subtype_data
        return subtype_data

    @property
    def concrete_variant(self):
        return self._subtype_data()[1]

    @property
    def type_label(self):
        definition = self._subtype_data()[0]
        return definition["label"] if definition else "Variant"

    @property
    def hgvs_name(self):
        return self.display_name

    @property
    def type(self):
        definition = self._subtype_data()[0]
        return definition["value"] if definition else "Variant"

    @property
    def coordinates_display(self):
        if self.start == self.end:
            return f"{self.chromosome}:{self.start}"
        return f"{self.chromosome}:{self.start}-{self.end}"

    @property
    def sequence_variant(self):
        concrete = self.concrete_variant
        if self.type in {"SNV", "delins"}:
            return concrete
        return None

    @property
    def is_sequence_variant(self):
        return self.sequence_variant is not None

    @property
    def change_display(self):
        concrete = self.concrete_variant
        if self.type in {"SNV", "delins"}:
            return f"{concrete.reference}>{concrete.alternate}"
        if self.type == "CNV":
            value = concrete.get_cnv_type_display()
            if concrete.copy_number is not None:
                value = f"{value} (copy number {concrete.copy_number})"
            return value
        if self.type == "SV":
            return concrete.get_sv_type_display()
        if self.type == "Repeat":
            return f"({concrete.repeat_unit})x{concrete.repeat_count}"
        return ""

    @property
    def display_name(self):
        change = self.change_display
        if change:
            return f"{self.coordinates_display} {change}"
        return self.coordinates_display

    @property
    def sequence_variant_id(self):
        sequence_variant = self.sequence_variant
        if not sequence_variant:
            return ""
        return (
            f"{self.chromosome}-{self.start}-"
            f"{sequence_variant.reference}-{sequence_variant.alternate}"
        )

    @property
    def pipeline(self):
        return self.analysis.pipeline if self.analysis and self.analysis.pipeline_id else None

    @property
    def pipeline_id(self):
        pipeline = self.pipeline
        return pipeline.pk if pipeline else None

allele_validator = RegexValidator(
    regex=r"^[ATGC]+$",
    message="Alleles must consist only of the uppercase characters A, T, G, or C.",
    code="invalid_allele",
)

class SNV(Variant):
    """Single Nucleotide Variant"""
    reference = models.CharField(max_length=255, validators=[allele_validator])
    alternate = models.CharField(max_length=255, validators=[allele_validator])
    
    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        # For SNVs we always normalize to end == start so the interval API
        # stays consistent across all Variant subclasses.
        if self.start is not None:
            self.end = self.start
        super().save(*args, **kwargs)

class delins(Variant):
    """Simple deletion/insertion anchored at a single position."""
    reference = models.CharField(max_length=255, validators=[allele_validator])
    alternate = models.CharField(max_length=255, validators=[allele_validator])
    
    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        # For basic delins we also keep end == start.
        if self.start is not None:
            self.end = self.start
        super().save(*args, **kwargs)

class CNV(Variant):
    """Copy Number Variant"""
    TYPE_CHOICES = [
        ("loss", "Loss"),
        ("gain", "Gain"),
    ]
    cnv_type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    copy_number = models.IntegerField(null=True, blank=True)
    
    def __str__(self):
        return self.display_name

class SV(Variant):
    """Structural Variant"""
    TYPE_CHOICES = [
        ("inversion", "Inversion"),
        ("translocation", "Translocation"),
        ("insertion", "Insertion"),
        ("deletion", "Deletion"),
        ("duplication", "Duplication"),
    ]
    sv_type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    breakpoints = models.JSONField(null=True, blank=True, help_text="Detailed breakpoint coordinates")

    def __str__(self):
        return self.display_name

class Repeat(Variant):
    """Repeat Expansion"""
    repeat_unit = models.CharField(max_length=50)
    repeat_count = models.IntegerField()
    
    def __str__(self):
        return self.display_name

class Annotation(models.Model):
    """Stores annotations for variants from external sources"""
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, related_name="annotations")
    source = models.CharField(max_length=100, help_text="e.g. myvariant, vep, genebe")
    source_version = models.CharField(max_length=100, null=True, blank=True)
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ["variant", "source", "source_version"]

    def __str__(self):
        return f"{self.source} for {self.variant}"

    history = HistoricalRecords()


class ACMGEvidenceOverride(models.Model):
    """Imported GeneBe evidence plus manual overrides for a variant gene row."""

    SOURCE_CHOICES = [
        ("genebe", "GeneBe Import"),
        ("manual", "Manual Override"),
    ]

    variant = models.ForeignKey(
        Variant,
        on_delete=models.CASCADE,
        related_name="acmg_evidence_overrides",
    )
    gene_symbol = models.CharField(max_length=100, blank=True, db_index=True)
    transcript = models.CharField(max_length=100, blank=True)
    criterion = models.CharField(max_length=20, db_index=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, db_index=True)
    included = models.BooleanField(default=True)
    strength = models.CharField(max_length=20, blank=True, default="")
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["gene_symbol", "transcript", "criterion", "source"]
        unique_together = ["variant", "gene_symbol", "transcript", "criterion", "source"]

    def save(self, *args, **kwargs):
        self.gene_symbol = (self.gene_symbol or "").strip()
        self.transcript = (self.transcript or "").strip()
        if self.criterion:
            self.criterion = self.criterion.strip().replace(" ", "_").upper()
        if self.strength:
            self.strength = self.strength.strip().replace(" ", "_").lower()
        super().save(*args, **kwargs)

    def __str__(self):
        state = "included" if self.included else "excluded"
        scope = self.gene_symbol or "variant"
        return f"{self.variant} {scope} {self.criterion} ({self.source}, {state})"

class Classification(HistoryMixin, models.Model):
    """ACMG Classification for a Variant"""
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, related_name="classifications")
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    
    CLASSIFICATION_CHOICES = [
        ("pathogenic", "Pathogenic"),
        ("likely_pathogenic", "Likely Pathogenic"),
        ("vus", "VUS"),
        ("likely_benign", "Likely Benign"),
        ("benign", "Benign"),
    ]
    classification = models.CharField(max_length=50, choices=CLASSIFICATION_CHOICES)
    
    INHERITANCE_CHOICES = [
        ("ad", "Autosomal Dominant"),
        ("ar", "Autosomal Recessive"),
        ("x_linked", "X-linked"),
        ("mitochondrial", "Mitochondrial"),
        ("de_novo", "De Novo"),
        ("unknown", "Unknown"),
    ]
    inheritance = models.CharField(max_length=50, choices=INHERITANCE_CHOICES, default="unknown")
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.classification} ({self.inheritance}) by {self.user}"

class Gene(models.Model):
    """HGNC Gene Data"""
    hgnc_id = models.CharField(max_length=50, unique=True)
    symbol = models.CharField(max_length=50, db_index=True)
    name = models.CharField(max_length=255)
    alias_symbol = models.TextField(blank=True)
    alias_name = models.TextField(blank=True)
    ensembl_gene_id = models.CharField(max_length=50, blank=True)
    entrez_id = models.CharField(max_length=50, blank=True)
    omim_id = models.CharField(max_length=50, blank=True)
    location = models.CharField(max_length=50, blank=True)
    prev_symbol = models.TextField(blank=True)
    prev_name = models.TextField(blank=True)
    locus_type = models.CharField(max_length=50, blank=True)
    locus_group = models.CharField(max_length=50, blank=True)
    gene_family = models.TextField(blank=True)
    uniprot_ids = models.TextField(blank=True)
    pubmed_id = models.TextField(blank=True)
    refseq_accession = models.TextField(blank=True)
    
    def __str__(self):
        return self.symbol
