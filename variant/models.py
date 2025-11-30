from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from simple_history.models import HistoricalRecords
from lab.models import Analysis, Individual, HistoryMixin

class Variant(HistoryMixin, models.Model):
    """Base class for all variant types"""
    assembly_version = models.CharField(max_length=10, default="hg38")
    chromosome = models.CharField(max_length=10)
    start = models.IntegerField()
    end = models.IntegerField()
    
    # Linkage
    individual = models.ForeignKey(Individual, on_delete=models.PROTECT, related_name="variants")
    analysis = models.ForeignKey(Analysis, on_delete=models.PROTECT, related_name="found_variants", null=True, blank=True)
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = GenericRelation("lab.Note")
    genes = models.ManyToManyField("Gene", related_name="variants", blank=True)
    history = HistoricalRecords(inherit=True)

    class Meta:
        ordering = ["chromosome", "start"]

    def __str__(self):
        return f"{self.chromosome}:{self.start}-{self.end}"

    status = models.ForeignKey("lab.Status", on_delete=models.PROTECT, null=True, blank=True)

    ZYGOSITY_CHOICES = [
        ("het", "Heterozygous"),
        ("hom", "Homozygous"),
        ("hemi", "Hemizygous"),
        ("unknown", "Unknown"),
    ]
    zygosity = models.CharField(max_length=20, choices=ZYGOSITY_CHOICES, default="unknown")

    def save(self, *args, **kwargs):
        if self.chromosome and not self.chromosome.startswith("chr"):
            self.chromosome = f"chr{self.chromosome}"
        super().save(*args, **kwargs)

    @property
    def hgvs_name(self):
        if hasattr(self, 'snv'):
            return f"{self.chromosome}:{self.start}{self.snv.reference}>{self.snv.alternate}"
        return str(self)

    @property
    def type(self):
        if hasattr(self, 'snv'):
            return "SNV"
        if hasattr(self, 'cnv'):
            return "CNV"
        if hasattr(self, 'sv'):
            return "SV"
        if hasattr(self, 'repeat'):
            return "Repeat"
        return "Variant"

class SNV(Variant):
    """Single Nucleotide Variant"""
    reference = models.CharField(max_length=255)
    alternate = models.CharField(max_length=255)
    
    def __str__(self):
        return f"{self.chromosome}:{self.start} {self.reference}>{self.alternate}"

class CNV(Variant):
    """Copy Number Variant"""
    TYPE_CHOICES = [
        ("loss", "Loss"),
        ("gain", "Gain"),
    ]
    cnv_type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    copy_number = models.IntegerField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.chromosome}:{self.start}-{self.end} {self.cnv_type}"

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
        return f"{self.chromosome}:{self.start}-{self.end} {self.sv_type}"

class Repeat(Variant):
    """Repeat Expansion"""
    repeat_unit = models.CharField(max_length=50)
    repeat_count = models.IntegerField()
    
    def __str__(self):
        return f"{self.chromosome}:{self.start} ({self.repeat_unit})x{self.repeat_count}"

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

