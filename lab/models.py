from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.conf import settings
from encrypted_model_fields.fields import (
    EncryptedCharField,
    EncryptedBigIntegerField,
    EncryptedDateField,
)
from simple_history.models import HistoricalRecords
from django.utils import timezone
from pathlib import Path
import re
from taggit.managers import TaggableManager
from taggit.models import GenericTaggedItemBase
from .middleware import get_current_user


RAREBOOST_ID_VALUE_REGEX = r"^RB_20[0-9][0-9]_[0-9]+(\.1)?\.[0-9]+$"
validate_rareboost_id_value = RegexValidator(
    regex=RAREBOOST_ID_VALUE_REGEX,
    message=(
        "RareBoost ID must match RB_20YY_<n>[.1].<n> "
        "(e.g. RB_2025_12.2 or RB_2025_12.1.3)."
    ),
    code="invalid",
)

BIOBANK_ID_VALUE_REGEX = r"^RD[0-9]+\.F[0-9]+(\.1)?\.[0-9]+$"
validate_biobank_id_value = RegexValidator(
    regex=BIOBANK_ID_VALUE_REGEX,
    message=(
        "Biobank ID must match RD3.F<n>[.1].<n> "
        "(e.g. RD3.F12.2 or RD3.F12.1.3)."
    ),
    code="invalid",
)


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
    statuses = TaggableManager(through="TaggedStatus", blank=True, verbose_name="Statuses")
    previous_status = models.ForeignKey(
        "Status",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks_previous_status",
        help_text="Stores the primary task status before it was last completed",
    )
    notes = GenericRelation("Note")
    history = HistoricalRecords()

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.title

    def complete(self, user, notes=""):
        task_ct = ContentType.objects.get_for_model(Task)
        completed_status = Status.objects.filter(
            content_type=task_ct,
            name__iexact="completed",
        ).first()
        if not completed_status:
            raise ValueError("No 'completed' status found in Status model.")
        if self.statuses.filter(pk=completed_status.pk).exists():
            return False
        # Store the first current status as "previous" for possible restoration
        first_prev = self.statuses.first()
        if first_prev:
            self.previous_status = first_prev
            self.save(update_fields=["previous_status"])
        self.statuses.set([completed_status])
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
    statuses = TaggableManager(through="TaggedStatus", blank=True, verbose_name="Statuses")
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
        task_ct = ContentType.objects.get_for_model(Task)
        completed_status = Status.objects.filter(
            content_type=task_ct,
            name__iexact="completed",
        ).first()
        if not completed_status:
            return 0
        completed_task_ids = TaggedStatus.objects.filter(
            content_type=task_ct,
            tag=completed_status,
            object_id__in=self.tasks.values_list("id", flat=True),
        ).values_list("object_id", flat=True)
        return len(set(completed_task_ids))

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
    positive_report_template = models.CharField(max_length=255, blank=True, default="")
    negative_report_template = models.CharField(max_length=255, blank=True, default="")
    default_positive_comment_text = models.TextField(blank=True, default="")
    default_negative_result_text = models.TextField(blank=True, default="")
    default_method_text = models.TextField(blank=True, default="")
    default_total_reads_text = models.CharField(max_length=255, blank=True, default="")
    default_coverage_20x_text = models.CharField(max_length=255, blank=True, default="")
    default_mean_depth_text = models.CharField(max_length=255, blank=True, default="")
    default_filtering_text = models.TextField(blank=True, default="")
    default_limitations_text = models.TextField(blank=True, default="")
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


class Contact(HistoryMixin, models.Model):
    full_name = models.CharField(max_length=255, db_index=True)
    emails = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered email addresses associated with this contact.",
    )
    phones = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered phone numbers associated with this contact.",
    )
    notes = models.TextField(blank=True, default="")
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="created_contacts",
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class Institution(HistoryMixin, models.Model):
    staff = models.ManyToManyField(
        "Contact",
        blank=True,
        related_name="institutions_as_staff",
    )
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
    def is_solved(self):
        """True if every index individual has at least one solved status tag."""
        index_ids = list(self.individuals.filter(is_index=True).values_list("id", flat=True))
        total_index = len(index_ids)
        if total_index == 0:
            return False
        individual_ct = ContentType.objects.get_for_model(Individual)
        solved_individual_ids = set(
            TaggedStatus.objects.filter(
                content_type=individual_ct,
                object_id__in=index_ids,
                tag__name__iexact="Solved",
            ).values_list("object_id", flat=True)
        )
        return len(solved_individual_ids) == total_index

class StatusGroup(HistoryMixin, models.Model):
    """A named group of mutually exclusive statuses scoped to a content type."""

    name = models.CharField(max_length=100)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    history = HistoricalRecords()

    class Meta:
        unique_together = [("name", "content_type")]
        ordering = ["content_type__model", "name"]
        verbose_name = "Status Group"
        verbose_name_plural = "Status Groups"

    def __str__(self):
        if self.content_type:
            return f"{self.name} ({self.content_type.model.title()})"
        return self.name


class Status(HistoryMixin, models.Model):
    name = models.CharField(max_length=100)
    short_name = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        help_text="Optional abbreviated label shown in table badges (falls back to full name).",
    )
    description = models.TextField(blank=True)
    color = models.CharField(max_length=50, default="gray")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    connected_classes = models.ManyToManyField(
        ContentType,
        blank=True,
        related_name="connected_statuses",
        help_text="Connected object types whose statuses should also be surfaced on the individual row.",
    )
    icon = models.CharField(max_length=255, null=True)
    group = models.ForeignKey(
        "StatusGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="statuses",
        help_text="Statuses in the same group are mutually exclusive — selecting one removes the others.",
    )
    history = HistoricalRecords()

    @property
    def display_name(self):
        """Returns short_name when set, otherwise falls back to name."""
        return self.short_name if self.short_name else self.name

    class Meta:
        verbose_name_plural = "statuses"
        ordering = ["name"]

    def __str__(self):
        return self.name


class TaggedStatus(GenericTaggedItemBase):
    """Through model linking any object to a Status tag via a generic FK."""

    tag = models.ForeignKey(
        Status,
        on_delete=models.CASCADE,
        related_name="tagged_items",
    )

    class Meta:
        unique_together = [("content_type", "object_id", "tag")]
        verbose_name = "Tagged Status"
        verbose_name_plural = "Tagged Statuses"


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
    age_of_onset_in_months = models.IntegerField(null=True, blank=True)
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
    statuses = TaggableManager(through="TaggedStatus", blank=True, verbose_name="Statuses")
    history = HistoricalRecords()
    diagnosis = models.TextField(blank=True)
    diagnosis_date = models.DateField(null=True, blank=True)
    institution = models.ManyToManyField(Institution, related_name="individuals")
    physicians = models.ManyToManyField("Contact", blank=True, related_name="patients")
    tasks = GenericRelation("Task")
    registration_date = models.DateField(null=True, blank=True)

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

    def _prefetched_cross_ids(self):
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        if "cross_ids" in prefetched:
            return list(prefetched["cross_ids"])
        return None

    @property
    def other_table_ids(self):
        """All non-primary/secondary IDs that are marked as visible for tables."""
        prefetched_cross_ids = self._prefetched_cross_ids()
        if prefetched_cross_ids is not None:
            ids = [
                f"{x.id_type.name}: {x.id_value}"
                for x in prefetched_cross_ids
                if x.id_type.use_priority not in (1, 2) and x.id_type.is_shown_in_table
            ]
            return ", ".join(ids) if ids else ""

        ids = [
            f"{x.id_type.name}: {x.id_value}"
            for x in self.cross_ids.select_related("id_type").all()
            if x.id_type.use_priority not in (1, 2) and x.id_type.is_shown_in_table
        ]
        return ", ".join(ids) if ids else ""

    @property
    def primary_id(self):
        prefetched_cross_ids = self._prefetched_cross_ids()
        if prefetched_cross_ids is not None:
            matches = [
                x for x in prefetched_cross_ids
                if x.id_type.use_priority == 1
            ]
            if matches:
                matches.sort(key=lambda x: x.id_type.id)
                return matches[0].id_value

        primary_type = IdentifierType.objects.filter(use_priority=1).order_by("id").first()
        if not primary_type:
            return "NO PRIMARY ID SET"

        if prefetched_cross_ids is not None:
            return f"No {primary_type.name} ID"

        xid = (
            self.cross_ids.filter(id_type=primary_type)
            .order_by("id_type__id")
            .first()
        )
        if xid:
            return xid.id_value
        return f"No {primary_type.name} ID"

    @property
    def secondary_id(self):
        prefetched_cross_ids = self._prefetched_cross_ids()
        if prefetched_cross_ids is not None:
            matches = [
                x for x in prefetched_cross_ids
                if x.id_type.use_priority == 2
            ]
            if matches:
                matches.sort(key=lambda x: x.id_type.id)
                return matches[0].id_value

        secondary_type = IdentifierType.objects.filter(use_priority=2).order_by("id").first()
        if not secondary_type:
            return "NO SECONDARY ID SET"

        if prefetched_cross_ids is not None:
            return f"No {secondary_type.name} ID"

        xid = (
            self.cross_ids.filter(id_type=secondary_type)
            .order_by("id_type__id")
            .first()
        )
        if xid:
            return xid.id_value
        return f"No {secondary_type.name} ID"

    # Backwards-compatible aliases (deprecated): prefer primary_id/secondary_id
    @property
    def lab_id(self):
        return self.primary_id

    @property
    def biobank_id(self):
        return self.secondary_id

    @property
    def individual_id(self):
        # Prefer the ID with the lowest non-zero priority
        preferred = (
            self.cross_ids.filter(id_type__use_priority__gt=0)
            .order_by("id_type__use_priority", "id_type__id")
            .first()
        )
        if preferred:
            return preferred.id_value

        # Otherwise show pk - any priority-0 IDs - name
        zero_priority_ids = list(
            self.cross_ids.filter(id_type__use_priority=0)
            .order_by("id_type__name", "id_type__id")
            .values_list("id_value", flat=True)
        )
        parts = [str(self.id), *zero_priority_ids]
        return " - ".join([p for p in parts if p])

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

    @staticmethod
    def age_of_onset_has_month_or_year_unit(age_of_onset):
        if not age_of_onset:
            return False

        tokens = [
            token.strip().strip(".,;:()[]{}").lower()
            for token in str(age_of_onset).split()
        ]
        year_tokens = {"year", "years", "yıl", "yaş"}
        month_tokens = {"month", "months", "ay", "aylık"}
        return any(token in year_tokens or token in month_tokens for token in tokens)

    @staticmethod
    def parse_age_of_onset_in_months(age_of_onset):
        if not age_of_onset:
            return None

        tokens = [
            token.strip().strip(".,;:()[]{}").lower()
            for token in str(age_of_onset).split()
        ]
        year_tokens = {"year", "years", "yıl", "yaş"}
        month_tokens = {"month", "months", "ay", "aylık"}

        multiplier = None
        if any(token in year_tokens for token in tokens):
            multiplier = 12
        elif any(token in month_tokens for token in tokens):
            multiplier = 1

        if multiplier is None:
            return None

        for token in tokens:
            normalized = token.replace(",", ".")
            if re.fullmatch(r"-?\d+(?:\.\d+)?", normalized):
                return int(float(normalized) * multiplier)

        return None

    def save(self, *args, **kwargs):
        should_update_onset_months = self.pk is None
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "age_of_onset" in update_fields:
            should_update_onset_months = True
        elif self.pk is not None:
            try:
                old_age_of_onset = type(self).objects.only("age_of_onset").get(
                    pk=self.pk
                ).age_of_onset
                should_update_onset_months = old_age_of_onset != self.age_of_onset
            except type(self).DoesNotExist:
                should_update_onset_months = True

        if should_update_onset_months and self.age_of_onset_has_month_or_year_unit(
            self.age_of_onset
        ):
            self.age_of_onset_in_months = self.parse_age_of_onset_in_months(
                self.age_of_onset
            )
        else:
            should_update_onset_months = False

        update_fields = kwargs.get("update_fields")
        if should_update_onset_months and update_fields is not None and "age_of_onset" in update_fields:
            kwargs["update_fields"] = set(update_fields) | {"age_of_onset_in_months"}
        super().save(*args, **kwargs)


class Sample(HistoryMixin, models.Model):
    individual = models.ForeignKey(
        Individual, on_delete=models.PROTECT, related_name="samples"
    )
    sample_type = models.ForeignKey(SampleType, on_delete=models.PROTECT)
    statuses = TaggableManager(through="TaggedStatus", blank=True, verbose_name="Statuses")
    history = HistoricalRecords()

    # Dates
    receipt_date = models.DateField(null=True, blank=True)
    processing_date = models.DateField(null=True, blank=True)

    # Sample details
    isolation_by = models.ForeignKey(
        "Contact",
        on_delete=models.PROTECT,
        related_name="isolated_samples",
        null=True,
        blank=True,
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
        return Variant.objects.filter(analysis__pipeline__test__sample=self).distinct()

    class Meta:
        ordering = ["-receipt_date"]

    def __str__(self):
        return f"{self.individual.primary_id} - {self.sample_type} - {self.receipt_date}"

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
        "Institution",
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
    statuses = TaggableManager(through="TaggedStatus", blank=True, verbose_name="Statuses")
    notes = GenericRelation("Note")
    tasks = GenericRelation("Task")
    history = HistoricalRecords()

    @property
    def variants(self):
        from django.apps import apps
        Variant = apps.get_model("variant", "Variant")
        return Variant.objects.filter(analysis__pipeline__test=self).distinct()

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
    statuses = TaggableManager(through="TaggedStatus", blank=True, verbose_name="Statuses")
    input_location = models.TextField(blank=True, help_text="Path to the input file(s) used by this pipeline run")
    output_location = models.TextField(blank=True, help_text="Path to the output directory or file(s) produced by this pipeline run")
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
    performed_by = models.ManyToManyField(
        User,
        blank=True,
        related_name="analyses_performed",
    )
    statuses = TaggableManager(through="TaggedStatus", blank=True, verbose_name="Statuses")
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

    @property
    def unreported_variants(self):
        """Variants linked to this individual but not linked to any report for this analysis."""
        from variant.models import Variant
        
        # We need the individual linked to this analysis
        individual = self.pipeline.test.sample.individual if self.pipeline and self.pipeline.test and self.pipeline.test.sample else None
        
        if not individual:
            return Variant.objects.none()
            
        return (
            Variant.objects.filter(individual=individual)
            .exclude(reports__analysis=self)
            .distinct()
        )

    @property
    def has_connected_variants(self):
        """Whether this analysis has any variants to show in report-related sections."""
        return self.unreported_variants.exists() or self.reports.exists()


class IdentifierType(HistoryMixin, models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    example = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Example of a valid identifier value for this type.",
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_id_types"
    )
    # 0 = not used, 1 = Primary ID, 2 = Secondary ID, 3 = Tertiary ID etc.
    use_priority = models.IntegerField(default=0) # 0 = not used, 1 = RB ID, 2 = BioBank ID, 3 = Erdera ID etc.
    is_shown_in_table = models.BooleanField(default=True)
    history = HistoricalRecords()

    def clean(self):
        super().clean()
        self.name = (self.name or "").strip()
        self.example = (self.example or "").strip()
        if not self.name:
            raise ValidationError({"name": "This field is required."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def validation_error_message(self):
        if self.example:
            return f"ID with type {self.name} is invalid. Correct example: {self.example}"
        return f"ID with type {self.name} is invalid."

    def __str__(self):
        return self.name

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="unique_identifiertype_name_ci",
            ),
            models.UniqueConstraint(
                fields=["use_priority"],
                condition=Q(use_priority__gt=0),
                name="unique_identifiertype_use_priority_nonzero",
            ),
        ]


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

    def clean(self):
        super().clean()
        if not self.id_type_id or not self.id_type:
            return

        validator = None
        if self.id_type.name == "RareBoost":
            validator = validate_rareboost_id_value
        elif self.id_type.name == "Biobank":
            validator = validate_biobank_id_value

        if validator is not None:
            try:
                validator(self.id_value)
            except ValidationError:
                raise ValidationError({"id_value": self.id_type.validation_error_message()})

    class Meta:
        unique_together = ["individual", "id_type"]

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    contact_info = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered clinician contact values imported from spreadsheets.",
    )
    email_notifications = models.JSONField(
        default=dict, help_text="Email notification settings"
    )
    display_preferences = models.JSONField(
        default=dict, help_text="UI and display preference settings"
    )
    signer_block_text = models.TextField(
        blank=True,
        default="",
        help_text="Multiline signer block inserted into generated reports.",
    )

    def __str__(self):
        return f"{self.user.username}'s Profile"


# Signals to create/save Profile automatically
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Automatically create a Profile when a User is created.

    Skip when `raw=True` (e.g. during loaddata) to avoid creating
    duplicate profiles that conflict with fixture data.
    """
    if kwargs.get("raw", False):
        return
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    Profile.objects.get_or_create(user=instance)
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
    analysis = models.ForeignKey(
        Analysis, on_delete=models.PROTECT, related_name="reports", null=True, blank=True
    )
    statuses = TaggableManager(through="TaggedStatus", blank=True, verbose_name="Statuses")
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
        return f"Analysis Report for {self.analysis} - {self.created_at.strftime('%Y-%m-%d')}"


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


class PlotTemplate(HistoryMixin, models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    target_model = models.CharField(max_length=100)
    query_config = models.JSONField(default=dict)
    notebook_filename = models.CharField(max_length=255)
    default_col_span = models.PositiveSmallIntegerField(default=1)
    show_download_menu = models.BooleanField(
        default=True,
        help_text="Show Marimo's notebook actions/download menu on notebook pages.",
    )
    slug = models.SlugField(unique=True)
    is_published = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_plot_templates"
    )
    history = HistoricalRecords()

    def clean(self):
        super().clean()
        if self.target_model not in settings.PLOT_ALLOWED_MODELS:
            raise ValidationError({"target_model": f"Must be one of: {settings.PLOT_ALLOWED_MODELS}"})

        raw = (self.notebook_filename or "").strip()
        if not raw:
            raise ValidationError({"notebook_filename": "This field is required."})
        safe_name = Path(raw).name
        if safe_name != raw:
            raise ValidationError(
                {"notebook_filename": "Must be a bare filename (e.g. sunburst.py), no folders or path segments."}
            )
        self.notebook_filename = safe_name

        notebook_path = settings.MARIMO_NOTEBOOKS_DIR / safe_name
        if not notebook_path.exists():
            raise ValidationError({"notebook_filename": f"Notebook {safe_name} not found in {settings.MARIMO_NOTEBOOKS_DIR}."})

    def save(self, *args, **kwargs):
        if not getattr(self, "created_by_id", None):
            try:
                current_user = get_current_user()
            except Exception:
                current_user = None

            if current_user is not None and getattr(current_user, "is_authenticated", False):
                self.created_by = current_user
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class DashboardWidget(HistoryMixin, models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="dashboard_widgets")
    template = models.ForeignKey(PlotTemplate, on_delete=models.CASCADE)
    order = models.IntegerField(default=0)
    col_span = models.IntegerField(default=1)
    row_span = models.IntegerField(default=1)
    history = HistoricalRecords()

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.user.username} - {self.template.name}"
