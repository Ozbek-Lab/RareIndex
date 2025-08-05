from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from encrypted_model_fields.fields import (
    EncryptedCharField,
    EncryptedBigIntegerField,
    EncryptedDateField,
)
from simple_history.models import HistoricalRecords
from django.utils import timezone

class Task(models.Model):
    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]
    # Add this field to your existing Task model
    project = models.ForeignKey(
        "Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Generic relation to allow tasks for any model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.PositiveIntegerField(null=True)
    content_object = GenericForeignKey("content_type", "object_id")

    # Task assignment and status
    assigned_to = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="assigned_tasks"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_tasks"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    due_date = models.DateTimeField(null=True, blank=True)

    # Task management
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default="medium"
    )
    status = models.ForeignKey("Status", on_delete=models.PROTECT)
    notes = GenericRelation("Note")
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def complete(self, user, notes=""):

        # Set status to a 'completed' Status instance
        completed_status = Status.objects.filter(name__iexact="completed").first()
        if not completed_status:
            raise ValueError("No 'completed' status found in Status model.")
        if self.status == completed_status:
            return False
        self.status = completed_status
        # Update the related object's status
        if hasattr(self.content_object, "update_status"):
            self.content_object.update_status(
                completed_status,
                user,
                f"Status updated via task completion: {self.title}",
            )
        self.save()
        return True


class Project(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.ForeignKey("Status", on_delete=models.PROTECT)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_projects"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    # Optional prioritization
    priority = models.CharField(
        max_length=10, choices=Task.PRIORITY_CHOICES, default="medium"
    )
    individuals = models.ManyToManyField("Individual", related_name="projects")
    # Notes for the project
    notes = GenericRelation("Note")
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def get_task_count(self):
        return self.tasks.count()

    def get_completed_task_count(self):
        completed_status = Status.objects.filter(name__iexact="completed").first()
        if not completed_status:
            return 0
        return self.tasks.filter(status=completed_status).count()

    def get_completion_percentage(self):
        total = self.get_task_count()
        if total == 0:
            return 0
        completed = self.get_completed_task_count()
        return int((completed / total) * 100)


class Note(models.Model):
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(User, on_delete=models.PROTECT)

    # Generic foreign key fields
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class TestType(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return self.name


class SampleType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return self.name


class Institution(models.Model):
    name = models.CharField(max_length=255)
    contact = models.TextField(blank=True)
    notes = GenericRelation("Note")
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return self.name


class Family(models.Model):
    family_id = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        verbose_name_plural = "families"
        ordering = ["-created_at"]

    def __str__(self):
        return self.family_id


class Status(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=50, default="gray")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )

    class Meta:
        verbose_name_plural = "statuses"
        ordering = ["name"]

    def __str__(self):
        return self.name


class StatusLog(models.Model):
    # Generic foreign key fields
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    # Status change info
    changed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    changed_at = models.DateTimeField(default=timezone.now)
    previous_status = models.ForeignKey(
        Status, on_delete=models.PROTECT, related_name="+"
    )
    new_status = models.ForeignKey(Status, on_delete=models.PROTECT, related_name="+")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-changed_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]


class StatusMixin:
    def update_status(self, new_status, changed_by, notes=""):
        if new_status != self.status:
            StatusLog.objects.create(
                content_object=self,
                changed_by=changed_by,
                previous_status=self.status,
                new_status=new_status,
                notes=notes,
            )
            self.status = new_status
            self.save()


class Individual(models.Model):
    id = models.AutoField(primary_key=True)
    full_name = EncryptedCharField(max_length=255)
    tc_identity = EncryptedBigIntegerField(null=True, blank=True)
    birth_date = EncryptedDateField(null=True, blank=True)
    icd11_code = models.TextField(null=True, blank=True)
    is_index = models.BooleanField(default=False)
    hpo_terms = models.ManyToManyField(
        "ontologies.Term",
        related_name="individuals",
        blank=True,
        limit_choices_to={"ontology__type": 1},  # 1 is HP in ONTOLOGY_CHOICES
    )
    is_affected = models.BooleanField(default=False)
    council_date = models.DateField(null=True, blank=True)
    family = models.ForeignKey(
        Family,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="individuals",
    )
    mother = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children_as_mother",
    )
    father = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children_as_father",
    )
    notes = GenericRelation("Note")
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_individuals"
    )
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    history = HistoricalRecords()
    diagnosis = models.TextField(blank=True)
    diagnosis_date = models.DateField(null=True, blank=True)
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT)
    tasks = GenericRelation("Task")

    class Meta:
        permissions = [
            ("view_sensitive_data", "Can view sensitive data"),
        ]

    @property
    def all_ids(self):
        return [
            f"{id_temp.id_type.name}: {id_temp.id_value}"
            for id_temp in self.cross_ids.all()
        ]

    @property
    def lab_id(self):
        if self.cross_ids.filter(id_type__name="RareBoost").exists():
            return self.cross_ids.get(id_type__name="RareBoost").id_value
        else:
            return f"No Lab ID"

    @property
    def biobank_id(self):
        if self.cross_ids.filter(id_type__name="Biobank").exists():
            return self.cross_ids.get(id_type__name="Biobank").id_value
        else:
            return f"No Biobank ID"

    @property
    def individual_id(self):
        if self.cross_ids.filter(id_type__name="RareBoost").exists():
            return self.cross_ids.filter(id_type__name="RareBoost").first().id_value
        elif self.cross_ids.filter(id_type__name="Biobank").exists():
            return self.cross_ids.filter(id_type__name="Biobank").first().id_value
        elif self.cross_ids.filter(individual=self).exists():
            return f"{self.cross_ids.filter(individual=self).first().id_value} - {self.full_name}"
        else:
            return f"{self.id} - {self.full_name}"

    @property
    def sensitive_fields(self):
        return {
            "full_name": self.full_name,
            "tc_identity": self.tc_identity,
            "birth_date": self.birth_date,
        }

    def get_all_tests(self):
        """Get all unique tests associated with this individual's samples"""

        # Get all sample IDs for this individual
        sample_ids = self.samples.values_list("id", flat=True)

        return Test.objects.filter(sample_id__in=sample_ids).distinct()

    def __str__(self):
        return f"{self.individual_id}"


class Sample(models.Model):
    individual = models.ForeignKey(
        Individual, on_delete=models.PROTECT, related_name="samples"
    )
    sample_type = models.ForeignKey(SampleType, on_delete=models.PROTECT)
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    history = HistoricalRecords()

    # Dates
    receipt_date = models.DateField(null=True, blank=True)
    processing_date = models.DateField(null=True, blank=True)

    # Sample details
    isolation_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="isolated_samples"
    )
    sample_measurements = models.CharField(max_length=255, blank=True)

    # Notes and tracking
    notes = GenericRelation("Note")
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_samples"
    )
    updated_at = models.DateTimeField(default=timezone.now)

    tasks = GenericRelation("Task")

    class Meta:
        ordering = ["-receipt_date"]

    def __str__(self):
        return f"{self.individual.lab_id} - {self.sample_type} - {self.receipt_date}"


class Test(models.Model):
    """Through model for tracking tests performed on samples"""

    sample = models.ForeignKey(Sample, on_delete=models.PROTECT, related_name="tests",null=True, blank=True)
    test_type = models.ForeignKey(TestType, on_delete=models.PROTECT)
    performed_date = models.DateField(null=True, blank=True)
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tests_performed",
    )
    service_send_date = models.DateField(
        null=True, blank=True, verbose_name="Service Send Date"
    )
    data_receipt_date = models.DateField(
        null=True, blank=True, verbose_name="Data Receipt Date"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_tests"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    notes = GenericRelation("Note")
    tasks = GenericRelation("Task")
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.test_type} - {self.sample}"

    class Meta:
        ordering = ["-created_at"]


class AnalysisType(models.Model):
    """Model for defining types of analyses that can be performed"""

    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    version = models.CharField(max_length=50, null=True, blank=True)
    parent_types = models.ManyToManyField(
        "self", blank=True, symmetrical=False, related_name="subtypes"
    )
    source_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        help_text="URL to the analysis source code or documentation",
    )
    results_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        help_text="URL to view analysis results",
    )
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_analysis_types"
    )

    class Meta:
        ordering = ["name", "-version"]

    def __str__(self):
        return f"{self.name} v{self.version}"


class Analysis(models.Model):
    """Model for tracking analyses performed on sample tests"""

    test = models.ForeignKey(Test, on_delete=models.PROTECT, related_name="analyses")
    performed_date = models.DateField()
    performed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    type = models.ForeignKey(AnalysisType, on_delete=models.PROTECT)
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    notes = GenericRelation("Note")
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_analyses"
    )
    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = "analyses"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.test} - {self.type} - {self.performed_date}"


class IdentifierType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_id_types"
    )

    def __str__(self):
        return self.name


class CrossIdentifier(models.Model):
    individual = models.ForeignKey(
        Individual, on_delete=models.PROTECT, related_name="cross_ids"
    )
    id_type = models.ForeignKey(IdentifierType, on_delete=models.PROTECT)
    id_value = models.CharField(max_length=100)
    id_description = models.TextField(blank=True)
    institution = models.ForeignKey(
        Institution, on_delete=models.PROTECT, blank=True, null=True
    )
    link = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return f"{self.individual} - {self.id_type} - {self.id_value}"
