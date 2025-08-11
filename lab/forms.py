# forms.py
from django import forms
from .models import (
    Task,
    Individual,
    Sample,
    Note,
    TestType,
    SampleType,
    Status,
    Project,
    Test,
    Analysis,
    AnalysisType,
    Institution,
    Family,
)
from django.contrib.contenttypes.models import ContentType


class BaseForm(forms.ModelForm):
    """Base form class with consistent styling for all form fields"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Apply consistent styling to all fields
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.TextInput):
                field.widget.attrs.update({
                    'class': 'w-[95%] px-3 py-2 ml-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:focus:ring-blue-400 dark:focus:border-blue-400 transition-colors duration-200'
                })
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({
                    'class': 'w-[95%] px-3 py-2 ml-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:focus:ring-blue-400 dark:focus:border-blue-400 transition-colors duration-200 resize-vertical min-h-[80px]'
                })
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({
                    'class': 'w-[95%] px-3 py-2 ml-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:focus:ring-blue-400 dark:focus:border-blue-400 transition-colors duration-200 appearance-none bg-no-repeat bg-right pr-10'
                })
            elif isinstance(field.widget, forms.DateInput):
                field.widget.attrs.update({
                    'class': 'w-[95%] px-3 py-2 ml-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:focus:ring-blue-400 dark:focus:border-blue-400 transition-colors duration-200'
                })
            elif isinstance(field.widget, forms.NumberInput):
                field.widget.attrs.update({
                    'class': 'w-[95%] px-3 py-2 ml-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:focus:ring-blue-400 dark:focus:border-blue-400 transition-colors duration-200'
                })


class ProjectForm(BaseForm):
    class Meta:
        model = Project
        fields = ["name", "description", "due_date", "priority"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }


# Update the TaskForm to include project field
class TaskForm(BaseForm):
    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "assigned_to",
            "due_date",
            "priority",
            "status",
            "project",
        ]
        widgets = {
            "due_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, content_object=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove StatusLog filtering logic; just show all Status objects
        self.fields["project"].queryset = Project.objects.all().order_by("name")


class IndividualForm(BaseForm):
    class Meta:
        model = Individual
        fields = [
            "id",
            "full_name",
            "tc_identity",
            "birth_date",
            "icd11_code",
            "council_date",
            "family",
            "mother",
            "father",
            "diagnosis",
            "diagnosis_date",
            "institution",
            "status",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "council_date": forms.DateInput(attrs={"type": "date"}),
            "diagnosis_date": forms.DateInput(attrs={"type": "date"}),
            "hpo_terms": forms.SelectMultiple(attrs={"class": "form-select"}),
        }


class SampleForm(BaseForm):
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
        ]
        widgets = {
            "receipt_date": forms.DateInput(attrs={"type": "date"}),
            "processing_date": forms.DateInput(attrs={"type": "date"}),
        }


class NoteForm(BaseForm):
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


class TestTypeForm(BaseForm):
    class Meta:
        model = TestType
        fields = ["name", "description"]


class SampleTypeForm(BaseForm):
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


class TestForm(BaseForm):
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


class AnalysisForm(BaseForm):
    class Meta:
        model = Analysis
        fields = [
            "test",
            "performed_date",
            "performed_by",
            "type",
            "status",
        ]
        widgets = {
            "performed_date": forms.DateInput(attrs={"type": "date"}),
        }


class AnalysisTypeForm(BaseForm):
    class Meta:
        model = AnalysisType
        fields = [
            "name",
            "description",
            "version",
            "parent_types",
            "source_url",
            "results_url",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "source_url": forms.URLInput(attrs={"placeholder": "https://..."}),
            "results_url": forms.URLInput(attrs={"placeholder": "https://..."}),
        }


class InstitutionForm(BaseForm):
    class Meta:
        model = Institution
        fields = [
            "name",
            "contact",
        ]
        widgets = {
            "contact": forms.Textarea(attrs={"rows": 3}),
        }


class FamilyForm(BaseForm):
    class Meta:
        model = Family
        fields = [
            "family_id",
            "description",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class StatusForm(BaseForm):
    class Meta:
        model = Status
        fields = [
            "name",
            "description",
            "color",
            "icon",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "color": forms.Select(choices=[
                ("gray", "Gray"),
                ("red", "Red"),
                ("yellow", "Yellow"),
                ("green", "Green"),
                ("blue", "Blue"),
                ("indigo", "Indigo"),
                ("purple", "Purple"),
                ("pink", "Pink"),
            ]),
        }


# Forms mapping for generic views
FORMS_MAPPING = {
    'Individual': IndividualForm,
    'Sample': SampleForm,
    'Test': TestForm,
    'Analysis': AnalysisForm,
    'Note': NoteForm,
    'Task': TaskForm,
    'Project': ProjectForm,
    'TestType': TestTypeForm,
    'SampleType': SampleTypeForm,
    'AnalysisType': AnalysisTypeForm,
    'Institution': InstitutionForm,
    'Family': FamilyForm,
    'Status': StatusForm,
}
