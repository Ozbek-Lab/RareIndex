# forms.py
from django import forms
from .models import (
    Task,
    StatusLog,
    Individual,
    Sample,
    Note,
    TestType,
    SampleType,
    Status,
    Project,
    Test,
)
from django.contrib.contenttypes.models import ContentType


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "due_date", "priority"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }


# Update the TaskForm to include project field
class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "assigned_to",
            "due_date",
            "priority",
            "target_status",
            "project",  # Add this field
        ]
        widgets = {
            "due_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, content_object=None, **kwargs):
        super().__init__(*args, **kwargs)

        # If we have a content object, filter statuses accordingly
        if content_object:
            content_type = ContentType.objects.get_for_model(content_object.__class__)

            # Get all statuses that have been used with this content type
            used_status_ids = (
                StatusLog.objects.filter(
                    content_type=content_type,
                )
                .values_list("new_status_id", flat=True)
                .distinct()
            )

            self.fields["target_status"].queryset = Status.objects.filter(
                id__in=used_status_ids
            )

        # Always sort projects by name
        self.fields["project"].queryset = Project.objects.all().order_by("name")


class IndividualForm(forms.ModelForm):
    class Meta:
        model = Individual
        fields = [
            "lab_id",
            "biobank_id",
            "full_name",
            "tc_identity",
            "birth_date",
            "icd11_code",
            "hpo_terms",
            "council_date",
            "family",
            "mother",
            "father",
            "diagnosis",
            "diagnosis_date",
            "sending_institution",
            "status",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "council_date": forms.DateInput(attrs={"type": "date"}),
            "diagnosis_date": forms.DateInput(attrs={"type": "date"}),
            "hpo_terms": forms.SelectMultiple(attrs={"class": "form-select"}),
        }


class SampleForm(forms.ModelForm):
    class Meta:
        model = Sample
        fields = [
            "individual",
            "sample_type",
            "receipt_date",
            "processing_date",
            "isolation_by",
            "sample_measurements",
            "status",
            "created_by",
        ]
        widgets = {
            "receipt_date": forms.DateInput(attrs={"type": "date"}),
            "processing_date": forms.DateInput(attrs={"type": "date"}),
        }


class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "class": "flex-1 px-2 py-1 text-xs shadow-sm rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500 resize-none h-[32px]",
                    "placeholder": "Add a note...",
                    "required": True,
                }
            ),
        }


class TestTypeForm(forms.ModelForm):
    class Meta:
        model = TestType
        fields = ["name", "description"]


class SampleTypeForm(forms.ModelForm):
    class Meta:
        model = SampleType
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm",
                }
            ),
        }


class TestForm(forms.ModelForm):
    class Meta:
        model = Test
        fields = [
            "test_type",
            "performed_date",
            "performed_by",
            "service_send_date",
            "data_receipt_date",
            "sample",
            "created_by",
        ]
        widgets = {
            "performed_date": forms.DateInput(attrs={"type": "date"}),
        }
