# models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType


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


class Test(models.Model):
    name = models.CharField(max_length=255)
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
    notes = GenericRelation(Note)
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
        ordering = ['-created_at']

    def __str__(self):
        return self.family_id


class Status(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=50, default='gray')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "statuses"
        ordering = ['name']

    def __str__(self):
        return self.name


class StatusLog(models.Model):
    # Generic foreign key fields
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Status change info
    changed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    changed_at = models.DateTimeField(auto_now_add=True)
    previous_status = models.ForeignKey(Status, on_delete=models.PROTECT, related_name='+')
    new_status = models.ForeignKey(Status, on_delete=models.PROTECT, related_name='+')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]


class StatusMixin:
    def update_status(self, new_status, changed_by, notes=''):
        if new_status != self.status:
            StatusLog.objects.create(
                content_object=self,
                changed_by=changed_by,
                previous_status=self.status,
                new_status=new_status,
                notes=notes
            )
            self.status = new_status
            self.save()


class Individual(StatusMixin, models.Model):
    lab_id = models.CharField(max_length=100, unique=True)
    biobank_id = models.CharField(max_length=100, blank=True)
    full_name = models.CharField(max_length=255)
    tc_identity = models.CharField(max_length=11, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    icd11_code = models.CharField(max_length=255, blank=True)
    hpo_codes = models.TextField(blank=True)
    family = models.ForeignKey(Family, on_delete=models.PROTECT, null=True, blank=True, related_name='individuals')
    notes = GenericRelation(Note)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_individuals')
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    status_logs = GenericRelation(StatusLog)
    diagnosis = models.TextField(blank=True)
    diagnosis_date = models.DateField(null=True, blank=True)
    
    @property
    def sensitive_fields(self):
        return {
            'full_name': self.full_name,
            'tc_identity': self.tc_identity,
            'birth_date': self.birth_date,
        }
    
    def __str__(self):
        return f"{self.lab_id}"


class Sample(StatusMixin, models.Model):
    STATUS_CHOICES = [
        ('received', 'Received'),
        ('in_processing', 'In Processing'),
        ('completed', 'Completed'),
        ('archived', 'Archived')
    ]
    
    individual = models.ForeignKey(Individual, on_delete=models.PROTECT, related_name='samples')
    sample_type = models.ForeignKey(SampleType, on_delete=models.PROTECT)
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    status_logs = GenericRelation(StatusLog)
    
    # Dates
    receipt_date = models.DateField()
    processing_date = models.DateField(null=True, blank=True)
    service_send_date = models.DateField(null=True, blank=True)
    data_receipt_date = models.DateField(null=True, blank=True)
    council_date = models.DateField(null=True, blank=True)
    
    # Relations
    sending_institution = models.ForeignKey(Institution, on_delete=models.PROTECT)
    tests = models.ManyToManyField(Test, through='SampleTest')
    
    # Sample details
    isolation_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='isolated_samples')
    sample_measurements = models.CharField(max_length=255, blank=True)
    
    # Notes and tracking
    notes = GenericRelation(Note)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_samples')
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-receipt_date']
    
    def __str__(self):
        return f"{self.individual.lab_id} - {self.sample_type} - {self.receipt_date}"


class SampleTest(StatusMixin, models.Model):
    """Through model for tracking tests performed on samples"""
    sample = models.ForeignKey(Sample, on_delete=models.PROTECT)
    test = models.ForeignKey(Test, on_delete=models.PROTECT)
    performed_date = models.DateField()
    performed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    status_logs = GenericRelation(StatusLog)
    notes = GenericRelation(Note)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.test.name} - {self.performed_date}"