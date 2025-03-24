from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    due_date = models.DateTimeField(null=True, blank=True)

    # Task management
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default="medium"
    )
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="completed_tasks",
    )

    # Target status that will be set when task is completed
    target_status = models.ForeignKey("Status", on_delete=models.PROTECT)

    notes = GenericRelation("Note")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def complete(self, user, notes=""):
        from django.utils import timezone

        if self.is_completed:
            return False

        self.is_completed = True
        self.completed_at = timezone.now()
        self.completed_by = user

        # Update the related object's status
        if hasattr(self.content_object, "update_status"):
            self.content_object.update_status(
                self.target_status,
                user,
                f"Status updated via task completion: {self.title}",
            )

        self.save()
        return True


class Project(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_projects"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Optional prioritization
    priority = models.CharField(
        max_length=10, choices=Task.PRIORITY_CHOICES, default="medium"
    )

    # Notes for the project
    notes = GenericRelation("Note")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def get_task_count(self):
        return self.tasks.count()

    def get_completed_task_count(self):
        return self.tasks.filter(is_completed=True).count()

    def get_completion_percentage(self):
        total = self.get_task_count()
        if total == 0:
            return 0
        completed = self.get_completed_task_count()
        return int((completed / total) * 100)


class Note(models.Model):
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
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
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return self.name


class SampleType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return self.name


class Institution(models.Model):
    name = models.CharField(max_length=255)
    contact = models.TextField(blank=True)
    notes = GenericRelation("Note")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):
        return self.name


class Family(models.Model):
    family_id = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
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
    created_at = models.DateTimeField(auto_now_add=True)
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
    changed_at = models.DateTimeField(auto_now_add=True)
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


class Individual(StatusMixin, models.Model):
    lab_id = models.CharField(max_length=100, unique=True)
    biobank_id = models.CharField(max_length=100, blank=True)
    full_name = models.CharField(max_length=255)
    tc_identity = models.CharField(max_length=11, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    icd11_code = models.TextField(blank=True)
    hpo_codes = models.TextField(blank=True)
    council_date = models.DateField(null=True, blank=True)
    family = models.ForeignKey(
        Family,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="individuals",
    )
    mother = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='children_as_mother'
    )
    father = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='children_as_father'
    )
    notes = GenericRelation("Note")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_individuals"
    )
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    status_logs = GenericRelation(StatusLog)
    diagnosis = models.TextField(blank=True)
    diagnosis_date = models.DateField(null=True, blank=True)
    sending_institution = models.ForeignKey(Institution, on_delete=models.PROTECT)
    tasks = GenericRelation("Task")

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
        return f"{self.lab_id}"


class Sample(StatusMixin, models.Model):
    individual = models.ForeignKey(
        Individual, on_delete=models.PROTECT, related_name="samples"
    )
    sample_type = models.ForeignKey(SampleType, on_delete=models.PROTECT)
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    status_logs = GenericRelation(StatusLog)

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
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_samples"
    )
    updated_at = models.DateTimeField(auto_now=True)

    tasks = GenericRelation("Task")

    class Meta:
        ordering = ["-receipt_date"]

    def __str__(self):
        return f"{self.individual.lab_id} - {self.sample_type} - {self.receipt_date}"


class Test(StatusMixin, models.Model):
    test_type = models.ForeignKey(TestType, on_delete=models.PROTECT)
    performed_date = models.DateField(null=True, blank=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tests_performed')
    service_send_date = models.DateField(null=True, blank=True, verbose_name='Service Send Date')
    data_receipt_date = models.DateField(null=True, blank=True, verbose_name='Data Receipt Date')
    council_date = models.DateField(null=True, blank=True, verbose_name='Council Date')
    sample = models.ForeignKey('Sample', on_delete=models.CASCADE, related_name='tests')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tests_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    status_logs = GenericRelation(StatusLog)
    tasks = GenericRelation("Task")

    def __str__(self):
        return f"{self.test_type} - {self.sample}"

    class Meta:
        ordering = ['-created_at']


class AnalysisType(models.Model):
    """Model for defining types of analyses that can be performed"""
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    version = models.CharField(max_length=50,blank=True)
    parent_types = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=False,
        related_name='subtypes'
    )
    source_url = models.URLField(
        max_length=500, 
        blank=True, 
        help_text="URL to the analysis source code or documentation"
    )
    results_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="URL to view analysis results"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.PROTECT, 
        related_name="created_analysis_types"
    )

    class Meta:
        ordering = ['name', '-version']

    def __str__(self):
        return f"{self.name} v{self.version}"


class Analysis(StatusMixin, models.Model):
    """Model for tracking analyses performed on sample tests"""
    
    test = models.ForeignKey(Test, on_delete=models.PROTECT, related_name='analyses')
    performed_date = models.DateField()
    performed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    type = models.ForeignKey(AnalysisType, on_delete=models.PROTECT)
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    status_logs = GenericRelation(StatusLog)
    notes = GenericRelation("Note")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_analyses"
    )

    class Meta:
        verbose_name_plural = "analyses"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.test} - {self.type} - {self.performed_date}"
