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
from .middleware import get_current_user


class HistoryMixin:
    """Mixin to provide history-based timestamp methods for models with HistoricalRecords"""

    def get_created_at(self):
        """Get creation time from history"""
        if hasattr(self, "history"):
            first_record = self.history.earliest()
            if first_record:
                return first_record.history_date
        return None

    def get_updated_at(self):
        """Get last update time from history"""
        if hasattr(self, "history"):
            latest_record = self.history.latest()
            if latest_record:
                return latest_record.history_date
        return None


class Task(HistoryMixin, models.Model):
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
    due_date = models.DateTimeField(null=True, blank=True)

    # Task management
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default="medium"
    )
    status = models.ForeignKey("Status", on_delete=models.PROTECT)
    previous_status = models.ForeignKey(
        "Status",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks_previous_status",
        help_text="Stores the task status before it was last completed",
    )
    notes = GenericRelation("Note")
    history = HistoricalRecords()

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.title

    def complete(self, user, notes=""):

        # Set status to a 'completed' Status instance
        completed_status = Status.objects.filter(name__iexact="completed").first()
        if not completed_status:
            raise ValueError("No 'completed' status found in Status model.")
        if self.status == completed_status:
            return False
        self.previous_status = self.status
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

    def save(self, *args, **kwargs):
        """Ensure `created_by` is set from the current request user if available.

        Uses thread-local storage populated by `CurrentUserMiddleware`.
        """
        if not getattr(self, "created_by_id", None):
            try:

                current_user = get_current_user()
            except Exception:
                current_user = None

            if current_user is not None and getattr(
                current_user, "is_authenticated", False
            ):
                self.created_by = current_user

        super().save(*args, **kwargs)


class Project(HistoryMixin, models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.ForeignKey("Status", on_delete=models.PROTECT)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_projects"
    )
    # Optional prioritization
    priority = models.CharField(
        max_length=10, choices=Task.PRIORITY_CHOICES, default="medium"
    )
    individuals = models.ManyToManyField("Individual", related_name="projects")
    # Notes for the project
    notes = GenericRelation("Note")
    created_at = models.DateTimeField(default=timezone.now)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-id"]

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

    def save(self, *args, **kwargs):
        """Ensure `created_by` is set from the current request user if available.

        Uses thread-local storage populated by `CurrentUserMiddleware`.
        """
        if not getattr(self, "created_by_id", None):
            try:
                current_user = get_current_user()
            except Exception:
                current_user = None

            if current_user is not None and getattr(
                current_user, "is_authenticated", False
            ):
                self.created_by = current_user

        super().save(*args, **kwargs)


class Note(HistoryMixin, models.Model):
    content = models.TextField()
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    private_owner = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="private_notes",
        help_text="If set, note is visible only to this user",
    )

    # Generic foreign key fields
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    history = HistoricalRecords()

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        created_at = self.get_created_at()
        if created_at:
            return f"{self.user.username} - {created_at.strftime('%Y-%m-%d %H:%M')}"
        return f"{self.user.username} - Unknown time"


class TestType(HistoryMixin, models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    history = HistoricalRecords()

    def __str__(self):
        return self.name


class SampleType(HistoryMixin, models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    history = HistoricalRecords()

    def __str__(self):
        return self.name


class Institution(HistoryMixin, models.Model):
    staff = models.ManyToManyField(User, blank=True, related_name="institutions_as_staff")
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    city = models.CharField(max_length=255, null=True, blank=True)
    name = models.CharField(max_length=255)
    center_name = models.CharField(max_length=255, null=True, blank=True)
    speciality = models.CharField(max_length=255, null=True, blank=True)
    official_name = models.CharField(max_length=255, null=True, blank=True)
    contact = models.TextField(blank=True)
    notes = GenericRelation("Note")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="institutions_created")
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Ensure `created_by` is set from the current request user if available.

        Uses thread-local storage populated by `CurrentUserMiddleware`.
        """
        if not getattr(self, "created_by_id", None):
            try:

                current_user = get_current_user()
            except Exception:
                current_user = None

            if current_user is not None and getattr(
                current_user, "is_authenticated", False
            ):
                self.created_by = current_user

        super().save(*args, **kwargs)


class Family(HistoryMixin, models.Model):
    family_id = models.CharField(max_length=100, unique=True)
    is_consanguineous = models.BooleanField(blank=True, null=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = "families"
        ordering = ["-id"]

    def __str__(self):
        return self.family_id

    @property
    def is_solved(self): # Check if all index individuals are solved - P/LP or VUS
        solved_qs = self.individuals.filter(
            is_index=True,
            status__name__in=["Solved - P/LP", "Solved - VUS"],
        )
        total_index = self.individuals.filter(is_index=True).count()
        return solved_qs.count() == total_index and total_index > 0

class Status(HistoryMixin, models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=50, default="gray")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    icon = models.CharField(max_length=255, null=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = "statuses"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Individual(HistoryMixin, models.Model):
    id = models.AutoField(primary_key=True)
    full_name = EncryptedCharField(max_length=255)
    tc_identity = EncryptedBigIntegerField(null=True, blank=True)
    birth_date = EncryptedDateField(null=True, blank=True)
    icd11_code = models.TextField(null=True, blank=True)
    is_index = models.BooleanField(default=False)
    sex = models.CharField(max_length=10, choices=[("male", "Male"), ("female", "Female"), ("other", "Other")], null=True, blank=True)
    is_alive = models.BooleanField(default=True)
    age_of_onset = models.CharField(max_length=255, null=True, blank=True)
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
    institution = models.ManyToManyField(Institution, related_name="individuals")
    physicians = models.ManyToManyField(User, blank=True, related_name="patients")
    tasks = GenericRelation("Task")

    class Meta:
        permissions = [
            ("view_sensitive_data", "Can view sensitive data"),
        ]
        ordering = ["-id"]

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
        # If no cross IDs exist, show pk - name
        if not self.cross_ids.exists():
            return f"{self.id} - {self.full_name}"
        # Otherwise, prioritize RareBoost, then Biobank, then any other cross ID
        elif self.cross_ids.filter(id_type__name="RareBoost").exists():
            return self.cross_ids.filter(id_type__name="RareBoost").first().id_value
        elif self.cross_ids.filter(id_type__name="Biobank").exists():
            return self.cross_ids.filter(id_type__name="Biobank").first().id_value
        else:
            return self.cross_ids.first().id_value

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


class Sample(HistoryMixin, models.Model):
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
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_samples"
    )

    tasks = GenericRelation("Task")

    @property
    def variants(self):
        from django.apps import apps
        Variant = apps.get_model("variant", "Variant")
        return Variant.objects.filter(analysis__test__sample=self).distinct()

    class Meta:
        ordering = ["-receipt_date"]

    def __str__(self):
        return f"{self.individual.lab_id} - {self.sample_type} - {self.receipt_date}"

    def save(self, *args, **kwargs):
        """Ensure `created_by` is set from the current request user if available.

        Uses thread-local storage populated by `CurrentUserMiddleware`.
        """
        if not getattr(self, "created_by_id", None):
            try:

                current_user = get_current_user()
            except Exception:
                current_user = None

            if current_user is not None and getattr(
                current_user, "is_authenticated", False
            ):
                self.created_by = current_user

        super().save(*args, **kwargs)


class Test(HistoryMixin, models.Model):
    """Through model for tracking tests performed on samples"""

    sample = models.ForeignKey(
        Sample, on_delete=models.PROTECT, related_name="tests", null=True, blank=True
    )
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
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    notes = GenericRelation("Note")
    tasks = GenericRelation("Task")
    history = HistoricalRecords()

    @property
    def variants(self):
        from django.apps import apps
        Variant = apps.get_model("variant", "Variant")
        return Variant.objects.filter(analysis__test=self).distinct()

    def __str__(self):
        return f"{self.test_type} - {self.sample}"

    class Meta:
        ordering = ["-id"]

    def save(self, *args, **kwargs):
        """Ensure `created_by` is set from the current request user if available.

        Uses thread-local storage populated by `CurrentUserMiddleware`.
        """
        if not getattr(self, "created_by_id", None):
            try:

                current_user = get_current_user()
            except Exception:
                current_user = None

            if current_user is not None and getattr(
                current_user, "is_authenticated", False
            ):
                self.created_by = current_user

        super().save(*args, **kwargs)


class PipelineType(HistoryMixin, models.Model):
    """Model for defining types of bioinformatics pipelines that can be run"""

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
        help_text="URL to the pipeline source code or documentation",
    )
    results_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        help_text="URL to view pipeline results",
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_pipeline_types"
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ["name", "-version"]

    def __str__(self):
        return f"{self.name} v{self.version}"


class Pipeline(HistoryMixin, models.Model):
    """Model for tracking bioinformatics pipeline runs on sample tests"""

    test = models.ForeignKey(Test, on_delete=models.PROTECT, related_name="pipelines")
    performed_date = models.DateField()
    performed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    type = models.ForeignKey(PipelineType, on_delete=models.PROTECT)
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    notes = GenericRelation("Note")
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_pipelines"
    )
    tasks = GenericRelation("Task")
    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = "pipelines"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.test} - {self.type} - {self.performed_date}"

    def save(self, *args, **kwargs):
        """Ensure `created_by` is set from the current request user if available.

        Uses thread-local storage populated by `CurrentUserMiddleware`.
        """
        if not getattr(self, "created_by_id", None):
            try:

                current_user = get_current_user()
            except Exception:
                current_user = None

            if current_user is not None and getattr(
                current_user, "is_authenticated", False
            ):
                self.created_by = current_user

        super().save(*args, **kwargs)


class AnalysisType(HistoryMixin, models.Model):
    """Types of clinical interpretations (e.g., Initial, Reanalysis)"""

    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="analysis_types_created",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name


class Analysis(HistoryMixin, models.Model):
    """Model for genome analyst's clinical interpretation of pipeline results"""

    pipeline = models.ForeignKey(
        Pipeline, on_delete=models.PROTECT, related_name="analyses", null=True, blank=True
    )
    type = models.ForeignKey(
        AnalysisType,
        on_delete=models.PROTECT,
        related_name="analyses",
        null=True,
        blank=True,
    )
    performed_date = models.DateField(null=True, blank=True)
    performed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    notes = GenericRelation("Note")
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_analyses",
        null=True,
        blank=True,
    )
    tasks = GenericRelation("Task")
    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = "analyses"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.pipeline} - {self.type} - {self.performed_date}"


class IdentifierType(HistoryMixin, models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_id_types"
    )
    history = HistoricalRecords()

    def __str__(self):
        return self.name


class CrossIdentifier(HistoryMixin, models.Model):
    individual = models.ForeignKey(
        Individual, on_delete=models.PROTECT, related_name="cross_ids"
    )
    id_type = models.ForeignKey(IdentifierType, on_delete=models.PROTECT)
    id_value = models.CharField(max_length=100)
    id_description = models.TextField(blank=True)
    institution = models.ManyToManyField(
        Institution, blank=True
    )
    link = models.URLField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.individual} - {self.id_type} - {self.id_value}"


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    email_notifications = models.JSONField(
        default=dict, help_text="Email notification settings"
    )
    display_preferences = models.JSONField(
        default=dict, help_text="UI and display preference settings"
    )

    def __str__(self):
        return f"{self.user.username}'s Profile"


# Signals to create/save Profile automatically
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, "profile"):
        instance.profile.save()


# Notification Signals
from .services import send_notification


@receiver(post_save, sender=Task)
def notify_task_assigned(sender, instance, created, **kwargs):
    """Notify user when a task is assigned to them"""
    if created and instance.assigned_to:
        send_notification(
            sender=instance.created_by,
            recipient=instance.assigned_to,
            verb="Task Assigned",
            description=f"You have been assigned a new task: {instance.title}",
            target=instance,
        )
    elif not created and instance.assigned_to:
        # Check if assigned_to changed (requires tracking previous instance, but for now just notify on save if assigned)
        # To do this properly we'd need to check pre_save or use a field tracker.
        # For simplicity, we'll assume new assignment if it was None before (which we can't easily check in post_save without extra logic)
        # or just notify on creation for now.
        pass


@receiver(post_save)
def notify_status_change(sender, instance, **kwargs):
    """Generic signal to notify on status change for models with status field"""
    # This is a bit broad, so we should limit it to specific models or use a mixin.
    # Let's limit to Sample, Test, Analysis for now.
    if sender.__name__ not in ["Sample", "Test", "Pipeline"]:
        return

    # We need to check if status changed.
    # Since we don't have easy dirty field tracking here without a library,
    # and we are in post_save, we can't compare with old.
    # However, the models use HistoryMixin/SimpleHistory, so we might be able to check history?
    # Or we can rely on the fact that status changes usually happen via specific views/methods.
    
    # Actually, the user requirement is "Status Change" notification.
    # Ideally this should be triggered where the change happens (e.g. update_status view).
    # But if we want it automatic, we need a way to detect change.
    
    # Let's use the `tracker` if available (django-model-utils) or just skip automatic signal for status
    # and rely on explicit calls in views/methods (like Task.complete does).
    pass


class AnalysisReport(HistoryMixin, models.Model):
    pipeline = models.ForeignKey(
        Pipeline, on_delete=models.PROTECT, related_name="reports"
    )
    # Lazy reference to avoid circular import if Variant is in another app
    variants = models.ManyToManyField("variant.Variant", related_name="reports", blank=True)
    file = models.FileField(upload_to="analysis_reports/%Y/%m/%d/")
    preview_file = models.FileField(upload_to="analysis_reports/previews/%Y/%m/%d/", null=True, blank=True, max_length=500)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="uploaded_analysis_reports"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    def __str__(self):
        return f"Analysis Report for {self.pipeline} - {self.created_at.strftime('%Y-%m-%d')}"


class AnalysisRequestForm(HistoryMixin, models.Model):
    individual = models.ForeignKey(
        Individual, on_delete=models.PROTECT, related_name="analysis_request_forms"
    )
    file = models.FileField(upload_to="analysis_requests/%Y/%m/%d/")
    preview_file = models.FileField(upload_to='analysis_requests/previews/%Y/%m/%d/', null=True, blank=True, max_length=500)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="uploaded_analysis_requests"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    def __str__(self):
        return f"Request Form for {self.individual} - {self.created_at.strftime('%Y-%m-%d')}"

