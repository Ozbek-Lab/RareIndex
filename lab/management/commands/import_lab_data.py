import random
from datetime import datetime, timedelta
from django.contrib.auth.models import User
from django.utils.timezone import now
from django.contrib.contenttypes.models import ContentType
from myapp.models import (
    Task, Project, Note, Test, SampleType, Institution, Family, Status,
    StatusLog, Individual, Sample, SampleTest, AnalysisType, SampleTestAnalysis
)

# Create Users
users = [User(username=f"user_{i}", email=f"user_{i}@example.com") for i in range(1, 6)]
User.objects.bulk_create(users)
users = User.objects.all()

# Create Statuses
statuses = [
    Status(name=f"Status {i}", description=f"Status Description {i}", created_by=random.choice(users))
    for i in range(1, 6)
]
Status.objects.bulk_create(statuses)
statuses = Status.objects.all()

# Create Projects
projects = [
    Project(name=f"Project {i}", description=f"Project Description {i}", created_by=random.choice(users))
    for i in range(3)
]
Project.objects.bulk_create(projects)
projects = Project.objects.all()

# Create Institutions
institutions = [
    Institution(name=f"Institution {i}", created_by=random.choice(users))
    for i in range(3)
]
Institution.objects.bulk_create(institutions)
institutions = Institution.objects.all()

# Create Families
families = [
    Family(family_id=f"FAM{i}", description=f"Family Description {i}", created_by=random.choice(users))
    for i in range(3)
]
Family.objects.bulk_create(families)
families = Family.objects.all()

# Create Individuals
individuals = [
    Individual(
        lab_id=f"IND{i}",
        full_name=f"Person {i}",
        tc_identity=str(10000000000 + i),
        birth_date=datetime(1990, 1, 1) + timedelta(days=i * 365),
        status=random.choice(statuses),
        family=random.choice(families),
        created_by=random.choice(users)
    )
    for i in range(5)
]
Individual.objects.bulk_create(individuals)
individuals = Individual.objects.all()

# Create Sample Types
sample_types = [
    SampleType(name=f"SampleType {i}", created_by=random.choice(users))
    for i in range(3)
]
SampleType.objects.bulk_create(sample_types)
sample_types = SampleType.objects.all()

# Create Samples
samples = [
    Sample(
        individual=random.choice(individuals),
        sample_type=random.choice(sample_types),
        status=random.choice(statuses),
        receipt_date=now() - timedelta(days=random.randint(1, 100)),
        sending_institution=random.choice(institutions),
        isolation_by=random.choice(users),
        created_by=random.choice(users)
    )
    for i in range(10)
]
Sample.objects.bulk_create(samples)
samples = Sample.objects.all()

# Create Tests
tests = [
    Test(name=f"Test {i}", description=f"Test Description {i}", created_by=random.choice(users))
    for i in range(3)
]
Test.objects.bulk_create(tests)
tests = Test.objects.all()

# Create Sample Tests
sample_tests = [
    SampleTest(
        sample=random.choice(samples),
        test=random.choice(tests),
        performed_date=now() - timedelta(days=random.randint(1, 30)),
        performed_by=random.choice(users),
        status=random.choice(statuses)
    )
    for i in range(10)
]
SampleTest.objects.bulk_create(sample_tests)
sample_tests = SampleTest.objects.all()

# Create Analysis Types
analysis_types = [
    AnalysisType(name=f"AnalysisType {i}", version=f"v{i}.0", created_by=random.choice(users))
    for i in range(2)
]
AnalysisType.objects.bulk_create(analysis_types)
analysis_types = AnalysisType.objects.all()

# Create Sample Test Analyses
sample_test_analyses = [
    SampleTestAnalysis(
        sample_test=random.choice(sample_tests),
        performed_date=now() - timedelta(days=random.randint(1, 20)),
        performed_by=random.choice(users),
        type=random.choice(analysis_types),
        status=random.choice(statuses),
        created_by=random.choice(users)
    )
    for i in range(5)
]
SampleTestAnalysis.objects.bulk_create(sample_test_analyses)

# Create Notes
notes = [
    Note(
        content=f"Note {i} for {random.choice(users).username}",
        user=random.choice(users),
        content_type=ContentType.objects.get_for_model(random.choice([Project, Individual, Sample])),
        object_id=random.choice(individuals).id
    )
    for i in range(5)
]
Note.objects.bulk_create(notes)

# Create Tasks
tasks = [
    Task(
        project=random.choice(projects),
        title=f"Task {i}",
        description=f"Task Description {i}",
        assigned_to=random.choice(users),
        created_by=random.choice(users),
        priority=random.choice(["low", "medium", "high", "urgent"]),
        target_status=random.choice(statuses)
    )
    for i in range(5)
]
Task.objects.bulk_create(tasks)

print("Test data created successfully!")
