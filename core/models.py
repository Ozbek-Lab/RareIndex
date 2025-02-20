from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Institution(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Clinician(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    institution = models.ForeignKey(Institution, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.name

class Family(models.Model):
    family_id = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.family_id

    class Meta:
        verbose_name_plural = "Families"

class Individual(models.Model):
    # PED file compatible fields
    GENDER_CHOICES = [
        ('1', 'Male'),
        ('2', 'Female'),
        ('0', 'Unknown')
    ]
    AFFECTED_STATUS = [
        ('1', 'Unaffected'),
        ('2', 'Affected'),
        ('0', 'Unknown')
    ]

    # Lab specific fields
    lab_id = models.CharField(max_length=50, unique=True)  # Özbek Lab. ID
    biobank_id = models.CharField(max_length=50, blank=True)  # Biyobanka ID
    
    # Personal information
    name = models.CharField(max_length=200)
    national_id = models.CharField(max_length=20, blank=True)  # TC Kimlik No
    date_of_birth = models.DateField(null=True, blank=True)
    
    # PED file fields
    family = models.ForeignKey(Family, on_delete=models.PROTECT)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    father = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='father_children')
    mother = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='mother_children')
    affected = models.CharField(max_length=1, choices=AFFECTED_STATUS)

    # Clinical information
    icd11_codes = models.TextField(blank=True)
    referring_clinician = models.ForeignKey(Clinician, on_delete=models.SET_NULL, null=True, blank=True)
    referring_institution = models.ForeignKey(Institution, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.lab_id} - {self.name}"

class SampleType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Sample(models.Model):
    STATUS_CHOICES = [
        ('received', 'Received'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed')
    ]

    individual = models.ForeignKey(Individual, on_delete=models.PROTECT)
    sample_type = models.ForeignKey(SampleType, on_delete=models.PROTECT)
    collection_date = models.DateField()
    received_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    isolated_by = models.CharField(max_length=200, blank=True)
    isolation_values = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.individual.lab_id} - {self.sample_type}"

class Test(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed')
    ]

    name = models.CharField(max_length=200)
    sample = models.ForeignKey(Sample, on_delete=models.PROTECT)
    test_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    sent_date = models.DateField(null=True, blank=True)
    data_received_date = models.DateField(null=True, blank=True)
    council_date = models.DateField(null=True, blank=True)
    follow_up_notes = models.TextField(blank=True)
    results = models.TextField(blank=True)
    planned_tests = models.TextField(blank=True)
    completed_tests = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} - {self.sample}"

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
