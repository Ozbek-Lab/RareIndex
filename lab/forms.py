# forms.py
from django import forms
from django.contrib.auth.models import User
from django.utils import timezone
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
    Pipeline,
    PipelineType,
    Institution,
    Family,
    AnalysisType,
    AnalysisRequestForm,
    AnalysisReport,
    IdentifierType,
    StatusGroup,
    validate_rareboost_id_value,
    validate_biobank_id_value,
)
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q


class BaseForm(forms.ModelForm):
    """Base form class with consistent styling for all form fields"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Limit statuses choices strictly to model-specific statuses
        if "statuses" in self.fields and hasattr(self, '_meta') and hasattr(self._meta, 'model'):
            from django.contrib.contenttypes.models import ContentType
            from .models import Status
            try:
                model_ct = ContentType.objects.get_for_model(self._meta.model)
                self.fields["statuses"].queryset = Status.objects.filter(content_type=model_ct).order_by("name")
            except Exception:
                pass
                

        # Apply consistent styling to all fields
        # Apply consistent styling to all fields using DaisyUI
        for field_name, field in self.fields.items():
            current_classes = field.widget.attrs.get("class", "")
            
            if isinstance(field.widget, forms.TextInput):
                if "input" not in current_classes:
                    field.widget.attrs["class"] = f"input input-bordered w-full {current_classes}"
            elif isinstance(field.widget, forms.Textarea):
                if "textarea" not in current_classes:
                    field.widget.attrs["class"] = f"textarea textarea-bordered w-full h-24 {current_classes}"
            elif isinstance(field.widget, forms.Select):
                if "select" not in current_classes:
                    field.widget.attrs["class"] = f"select select-bordered w-full {current_classes}"
            elif isinstance(field.widget, forms.SelectMultiple):
                if "select" not in current_classes:
                    field.widget.attrs["class"] = f"select select-bordered w-full h-32 {current_classes}"
            elif isinstance(field.widget, forms.DateInput):
                 if "input" not in current_classes:
                    field.widget.attrs["class"] = f"input input-bordered w-full {current_classes}"
            elif isinstance(field.widget, forms.NumberInput):
                 if "input" not in current_classes:
                    field.widget.attrs["class"] = f"input input-bordered w-full {current_classes}"
            elif isinstance(field.widget, forms.CheckboxInput):
                if "checkbox" not in current_classes:
                    field.widget.attrs["class"] = f"checkbox {current_classes}"

    def save(self, commit=True, **kwargs):
        """Override save to handle created_by field automatically"""
        obj = super().save(commit=False)

        # Set created_by if the model has this field and it's not already set
        if hasattr(obj, "created_by") and not getattr(obj, "created_by_id", None):
            # Get the user from kwargs or try to get it from the request
            user = kwargs.get("user")
            if user:
                obj.created_by = user

        if commit:
            obj.save()
            self.save_m2m()
            # Handle statuses (TaggableManager) which isn't part of standard save_m2m
            if "statuses" in self.cleaned_data and hasattr(obj, "statuses"):
                obj.statuses.set(self.cleaned_data["statuses"])

        return obj


class ProjectForm(BaseForm):
    statuses = forms.ModelMultipleChoiceField(
        queryset=Status.objects.all(),
        required=False,
        label="Statuses",
        widget=forms.SelectMultiple(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["statuses"] = self.instance.statuses.all()

    class Meta:
        model = Project
        fields = ["name", "description", "due_date", "priority"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class ProjectCreateWithCopyForm(ProjectForm):
    """Project create form with optional 'copy individuals from other projects'."""

    copy_from_projects = forms.ModelMultipleChoiceField(
        queryset=Project.objects.all().order_by("name"),
        required=False,
        label="Copy Individuals From Projects",
        help_text="Individuals from the selected projects will be added to this new project after creation.",
        widget=forms.SelectMultiple(attrs={"size": 6}),
    )


# Update the TaskForm to include project field
class TaskForm(BaseForm):
    # Add fields for selecting the associated object
    content_type = forms.ModelChoiceField(
        queryset=ContentType.objects.none(),
        required=False,
        label="Associated Type",
        help_text="Select the type of object this task is for",
    )
    object_id = forms.IntegerField(
        required=False,
        label="Associated Object",
        help_text="Select the specific object",
    )

    statuses = forms.ModelMultipleChoiceField(
        queryset=Status.objects.all(),
        required=False,
        label="Statuses",
        widget=forms.SelectMultiple(),
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "assigned_to",
            "due_date",
            "priority",
            "project",
        ]
        widgets = {
            "due_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, content_object=None, individual=None, project=None, **kwargs):
        instance = kwargs.get("instance")
        super().__init__(*args, **kwargs)

        # Limit available projects based on context
        project_qs = Project.objects.all()
        if project is not None:
            # Task explicitly attached to a single Project: fix and lock the field
            project_qs = project_qs.filter(pk=project.pk)
            self.initial.setdefault("project", project)
            self.fields["project"].required = False  # value will be set in the view
            self.fields["project"].disabled = True
        elif individual is not None:
            # Only show projects the individual belongs to
            project_qs = project_qs.filter(individuals=individual)
        self.fields["project"].queryset = project_qs.order_by("name")

        # Populate statuses initial value when editing
        if instance and getattr(instance, "pk", None):
            self.initial["statuses"] = instance.statuses.all()

        # Default Task statuses to "Active" on creation (when not editing).
        if not getattr(instance, "pk", None) and not self.initial.get("statuses"):
            active_status = Status.objects.filter(name__iexact="Active").first()
            if active_status:
                self.initial["statuses"] = [active_status]
        
        # Set up content_type choices - models that can have tasks
        from variant.models import Variant
        taskable_models = [Individual, Sample, Test, Analysis, Project, Variant]
        content_types = ContentType.objects.filter(
            model__in=[m._meta.model_name for m in taskable_models],
            app_label__in=["lab", "variant"]
        ).order_by("model")
        self.fields["content_type"].queryset = content_types
        
        # If content_object is provided, set initial values
        if content_object is not None:
            ct = ContentType.objects.get_for_model(content_object.__class__)
            self.fields["content_type"].initial = ct.pk
            self.fields["object_id"].initial = content_object.pk
        # When editing an existing Task, prefill the form-only fields from the instance
        elif isinstance(instance, Task) and instance.content_type_id and instance.object_id:
            self.fields["content_type"].initial = instance.content_type_id
            self.fields["object_id"].initial = instance.object_id


class TaskEditForm(forms.ModelForm):
    statuses = forms.ModelMultipleChoiceField(
        queryset=Status.objects.all(),
        required=False,
        label="Statuses",
        widget=forms.SelectMultiple(),
    )

    class Meta:
        model = Task
        fields = ["title", "description", "assigned_to", "due_date", "priority"]
        widgets = {
            "due_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["statuses"] = self.instance.statuses.all()
            if self.instance.due_date:
                self.initial["due_date"] = self.instance.due_date.strftime("%Y-%m-%dT%H:%M")


class IndividualForm(BaseForm):
    statuses = forms.ModelMultipleChoiceField(
        queryset=Status.objects.all(),
        required=False,
        label="Statuses",
        widget=forms.SelectMultiple(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["statuses"] = self.instance.statuses.all()

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
            "hpo_terms",
            "sex",
            "is_index",
            "is_affected",
            "is_alive",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "council_date": forms.DateInput(attrs={"type": "date"}),
            "diagnosis_date": forms.DateInput(attrs={"type": "date"}),
            "hpo_terms": forms.SelectMultiple(attrs={"class": "form-select"}),
            "tc_identity": forms.NumberInput(
                attrs={
                    "type": "number",
                    "min": "10000000000",
                    "max": "99999999999",
                    "step": "1",
                    "placeholder": "Enter TC identity (11 digits)",
                }
            ),
        }


class SampleForm(BaseForm):
    statuses = forms.ModelMultipleChoiceField(
        queryset=Status.objects.all(),
        required=False,
        label="Statuses",
        widget=forms.SelectMultiple(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["statuses"] = self.instance.statuses.all()

    class Meta:
        model = Sample
        fields = [
            "individual",
            "sample_type",
            "receipt_date",
            "processing_date",
            "isolation_by",
            "sample_measurements",
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
                    "class": "textarea textarea-bordered w-full h-[32px] px-2 py-1 text-xs resize-none",
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
            "name": forms.TextInput(attrs={}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class TestForm(BaseForm):
    statuses = forms.ModelMultipleChoiceField(
        queryset=Status.objects.all(),
        required=False,
        label="Statuses",
        widget=forms.SelectMultiple(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["statuses"] = self.instance.statuses.all()

    class Meta:
        model = Test
        fields = [
            "sample",
            "test_type",
            "performed_date",
            "performed_by",
            "service_send_date",
            "data_receipt_date",
        ]
        widgets = {
            "performed_date": forms.DateInput(attrs={"type": "date"}),
            "service_send_date": forms.DateInput(attrs={"type": "date"}),
            "data_receipt_date": forms.DateInput(attrs={"type": "date"}),
        }


class PipelineForm(BaseForm):
    statuses = forms.ModelMultipleChoiceField(
        queryset=Status.objects.all(),
        required=False,
        label="Statuses",
        widget=forms.SelectMultiple(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["statuses"] = self.instance.statuses.all()

    class Meta:
        model = Pipeline
        fields = [
            "test",
            "type",
            "performed_date",
            "performed_by",
        ]
        widgets = {
            "performed_date": forms.DateInput(attrs={"type": "date"}),
        }


class AnalysisForm(BaseForm):
    statuses = forms.ModelMultipleChoiceField(
        queryset=Status.objects.all(),
        required=False,
        label="Statuses",
        widget=forms.SelectMultiple(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["statuses"] = self.instance.statuses.all()

    class Meta:
        model = Analysis
        fields = [
            "type",
            "performed_date",
            "performed_by",
            "pipeline",
        ]
        widgets = {
            "performed_date": forms.DateInput(attrs={"type": "date"}),
            "pipeline": forms.HiddenInput(),
        }
        widgets = {
            "performed_date": forms.DateInput(attrs={"type": "date"}),
            "pipeline": forms.HiddenInput(),
        }


class PipelineTypeForm(BaseForm):
    class Meta:
        model = PipelineType
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


class AnalysisTypeForm(BaseForm):
    class Meta:
        model = AnalysisType
        fields = ["name", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class AnalysisRequestFormForm(BaseForm):
    class Meta:
        model = AnalysisRequestForm
        fields = ["file", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class AnalysisReportForm(BaseForm):
    variants = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "select select-bordered w-full h-32"}),
    )

    class Meta:
        model = AnalysisReport
        fields = ["file", "variants", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, analysis=None, **kwargs):
        super().__init__(*args, **kwargs)
        from variant.models import Variant
        
        self.fields["variants"].queryset = Variant.objects.none()
        
        if analysis and analysis.pipeline and analysis.pipeline.test and analysis.pipeline.test.sample:
            individual = analysis.pipeline.test.sample.individual
            if individual:
                self.fields["variants"].queryset = Variant.objects.filter(individual=individual)


class AnalysisReportReplaceForm(BaseForm):
    class Meta:
        model = AnalysisReport
        fields = ["file"]


class AnalysisReportGenerateForm(forms.Form):
    report_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    template_location = forms.CharField(
        required=False,
        label="Report template",
        widget=forms.HiddenInput(),
    )
    default_positive_comment_text = forms.CharField(
        required=False,
        label="Positive comment text",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    default_negative_result_text = forms.CharField(
        required=False,
        label="Negative result text",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    default_method_text = forms.CharField(
        required=False,
        label="Method text",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    default_total_reads_text = forms.CharField(
        required=False,
        label="Total reads",
    )
    default_coverage_20x_text = forms.CharField(
        required=False,
        label="Coverage (20x)",
    )
    default_mean_depth_text = forms.CharField(
        required=False,
        label="Mean depth",
    )
    default_filtering_text = forms.CharField(
        required=False,
        label="Filtering text",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    default_limitations_text = forms.CharField(
        required=False,
        label="Limitations text",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    signers = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Signers",
        help_text="Only users with a saved signer block are listed.",
        widget=forms.SelectMultiple(),
    )
    authorized_signer = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="No authorized signer",
        label="Authorized signer",
        help_text="Only users with a saved signer block are listed.",
    )

    def __init__(self, *args, test_type=None, report_mode="positive", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["signers"].queryset = (
            User.objects.filter(profile__signer_block_text__isnull=False)
            .exclude(profile__signer_block_text="")
            .order_by("first_name", "last_name", "username")
        )
        self.fields["authorized_signer"].queryset = (
            User.objects.filter(profile__signer_block_text__isnull=False)
            .exclude(profile__signer_block_text="")
            .order_by("first_name", "last_name", "username")
        )
        self.fields["signers"].label_from_instance = (
            lambda user: user.get_full_name().strip() or user.username
        )
        self.fields["authorized_signer"].label_from_instance = (
            lambda user: user.get_full_name().strip() or user.username
        )

        if test_type is not None:
            self.fields["template_location"].initial = (
                getattr(test_type, "negative_report_template", "")
                if report_mode == "negative"
                else getattr(test_type, "positive_report_template", "")
            ) or ""
            self.fields["default_positive_comment_text"].initial = getattr(test_type, "default_positive_comment_text", "") or ""
            self.fields["default_negative_result_text"].initial = getattr(test_type, "default_negative_result_text", "") or ""
            self.fields["default_method_text"].initial = getattr(test_type, "default_method_text", "") or ""
            self.fields["default_total_reads_text"].initial = getattr(test_type, "default_total_reads_text", "") or ""
            self.fields["default_coverage_20x_text"].initial = getattr(test_type, "default_coverage_20x_text", "") or ""
            self.fields["default_mean_depth_text"].initial = getattr(test_type, "default_mean_depth_text", "") or ""
            self.fields["default_filtering_text"].initial = getattr(test_type, "default_filtering_text", "") or ""
            self.fields["default_limitations_text"].initial = getattr(test_type, "default_limitations_text", "") or ""

        if report_mode == "negative":
            self.fields.pop("default_positive_comment_text")
        else:
            self.fields.pop("default_negative_result_text")

        field_order = [
            "report_date",
            "default_negative_result_text" if report_mode == "negative" else "default_positive_comment_text",
            "default_method_text",
            "default_total_reads_text",
            "default_coverage_20x_text",
            "default_mean_depth_text",
            "default_filtering_text",
            "default_limitations_text",
            "signers",
            "authorized_signer",
            "template_location",
        ]
        self.order_fields([name for name in field_order if name in self.fields])

        # Match BaseForm styling without turning this into a ModelForm.
        self.fields["report_date"].widget.attrs["class"] = "input input-bordered w-full"
        if "default_positive_comment_text" in self.fields:
            self.fields["default_positive_comment_text"].widget.attrs["class"] = "textarea textarea-bordered w-full h-24"
        if "default_negative_result_text" in self.fields:
            self.fields["default_negative_result_text"].widget.attrs["class"] = "textarea textarea-bordered w-full h-24"
        self.fields["default_method_text"].widget.attrs["class"] = "textarea textarea-bordered w-full h-24"
        self.fields["default_total_reads_text"].widget.attrs["class"] = "input input-bordered w-full"
        self.fields["default_coverage_20x_text"].widget.attrs["class"] = "input input-bordered w-full"
        self.fields["default_mean_depth_text"].widget.attrs["class"] = "input input-bordered w-full"
        self.fields["default_filtering_text"].widget.attrs["class"] = "textarea textarea-bordered w-full h-24"
        self.fields["default_limitations_text"].widget.attrs["class"] = "textarea textarea-bordered w-full h-24"
        self.fields["signers"].widget.attrs["class"] = "select select-bordered w-full h-32"
        self.fields["authorized_signer"].widget.attrs["class"] = "select select-bordered w-full"


class InstitutionForm(BaseForm):
    class Meta:
        model = Institution
        fields = [
            "name",
            "official_name",
            "center_name",
            "speciality",
            "city",
            "latitude",
            "longitude",
            "contact",
            "staff",
        ]
        widgets = {
            "contact": forms.Textarea(attrs={"rows": 3}),
            "latitude": forms.NumberInput(attrs={"step": "any"}),
            "longitude": forms.NumberInput(attrs={"step": "any"}),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Create choices for existing families plus option for new family
        from .models import Family

        existing_families = Family.objects.all().order_by("family_id")
        choices = [("", "-- Select existing family or type new ID --")]
        choices.extend(
            [
                (
                    family.family_id,
                    f"{family.family_id} ({family.individuals.count()} members)",
                )
                for family in existing_families
            ]
        )

        # Replace the family_id field with a choice field
        self.fields["family_id"] = forms.ChoiceField(
            choices=choices,
            required=True,
            widget=forms.Select(
                attrs={
                    "data-family-select": "true",
                }
            ),
        )


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
            "color": forms.Select(
                choices=[
                    ("gray", "Gray"),
                    ("red", "Red"),
                    ("yellow", "Yellow"),
                    ("green", "Green"),
                    ("blue", "Blue"),
                    ("indigo", "Indigo"),
                    ("purple", "Purple"),
                    ("pink", "Pink"),
                ]
            ),
        }


class CreateFamilyForm(BaseForm):
    class Meta:
        model = Family
        fields = [
            "family_id",
            "description",
            "is_consanguineous",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "family_id": forms.TextInput(
                attrs={
                    "placeholder": "e.g. FAM001",
                }
            ),
        }


class FamilyMemberForm(BaseForm):
    # Hidden fields to handle client-side references
    father_ref = forms.CharField(required=False, widget=forms.HiddenInput())
    mother_ref = forms.CharField(required=False, widget=forms.HiddenInput())
    
    # JSON field for dynamic cross identifiers
    # Expected format: [{"type_id": 1, "value": "123"}, ...]
    cross_identifiers_json = forms.CharField(required=False, widget=forms.HiddenInput())
    
    # Simple text field for initial note
    note_content = forms.CharField(
        required=False, 
        widget=forms.Textarea(attrs={
            "rows": 2, 
            "placeholder": "Add initial notes...",
            # BaseForm will inject textarea-bordered, we just add resize-none or specific sizing if needed
            "class": "resize-none"
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure institutions are selectable
        self.fields["institution"].queryset = Institution.objects.all()
        # Set HPO terms widget attributes
        self.fields["hpo_terms"].widget.attrs.update({
             # "class": "hidden", # Standard select for now
             "data-hpo-picker": "true",
             "class": "select select-bordered w-full h-32"
        })
        # Override birth_date and council_date to use standard date input
        self.fields["birth_date"].widget = forms.DateInput(attrs={"type": "date"})
        self.fields["council_date"].widget = forms.DateInput(attrs={"type": "date"})
        

    statuses = forms.ModelMultipleChoiceField(
        queryset=Status.objects.all(),
        required=False,
        label="Statuses",
        widget=forms.SelectMultiple(),
    )

    class Meta:
        model = Individual
        fields = [
            "full_name",
            "tc_identity",
            "birth_date",
            "sex",
            "is_index",
            "is_affected",
            "council_date",
            "institution",
            "hpo_terms",
            "diagnosis",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "council_date": forms.DateInput(attrs={"type": "date"}),
            "full_name": forms.TextInput(attrs={"placeholder": "Full Name"}),
            "tc_identity": forms.NumberInput(
                attrs={
                    "type": "number",
                    "min": "10000000000",
                    "max": "99999999999",
                    "step": "1",
                    "placeholder": "TC Identity (11 digits)",
                }
            ),
        }

# Forms mapping for generic views
FORMS_MAPPING = {
    "Individual": IndividualForm,
    "Sample": SampleForm,
    "Test": TestForm,
    "Pipeline": PipelineForm,
    "Note": NoteForm,
    "Task": TaskForm,
    "Project": ProjectForm,
    "TestType": TestTypeForm,
    "SampleType": SampleTypeForm,
    "PipelineType": PipelineTypeForm,
    "AnalysisType": AnalysisTypeForm,
    "Institution": InstitutionForm,
    "Family": FamilyForm,
    "Status": StatusForm,
    "AnalysisRequestForm": AnalysisRequestFormForm,
    "AnalysisReport": AnalysisReportForm,
}


class IndividualIdentificationForm(BaseForm):
    primary_id = forms.CharField(required=False, label="Primary ID")
    secondary_id = forms.CharField(required=False, label="Secondary ID")

    def _get_id_labels(self):
        from .models import IdentifierType
        p = IdentifierType.objects.filter(use_priority=1).order_by("id").first()
        s = IdentifierType.objects.filter(use_priority=2).order_by("id").first()
        return (
            f"{p.name} ID" if p else "Primary ID",
            f"{s.name} ID" if s else "Secondary ID",
        )
    tc_identity = forms.IntegerField(required=False, label="TC Identity")
    cross_identifiers_json = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Individual
        fields = ["full_name", "tc_identity"]

    def clean(self):
        cleaned_data = super().clean()
        from django.core.exceptions import ValidationError as DjangoValidationError
        import json

        def _validate_by_type_name(id_type_name: str, value: str, field_name: str):
            if id_type_name == "RareBoost":
                try:
                    validate_rareboost_id_value(value)
                except DjangoValidationError as e:
                    self.add_error(field_name, " ".join(e.messages))
            elif id_type_name == "Biobank":
                try:
                    validate_biobank_id_value(value)
                except DjangoValidationError as e:
                    self.add_error(field_name, " ".join(e.messages))

        primary_id_val = cleaned_data.get("primary_id") or ""
        secondary_id_val = cleaned_data.get("secondary_id") or ""

        # Validate primary/secondary IDs based on their configured IdentifierType
        if primary_id_val:
            primary_type = IdentifierType.objects.filter(use_priority=1).order_by("id").first()
            if primary_type:
                _validate_by_type_name(primary_type.name, primary_id_val, "primary_id")

        if secondary_id_val:
            secondary_type = IdentifierType.objects.filter(use_priority=2).order_by("id").first()
            if secondary_type:
                _validate_by_type_name(secondary_type.name, secondary_id_val, "secondary_id")

        # Validate any dynamic cross IDs that are RareBoost
        cross_ids_json = cleaned_data.get("cross_identifiers_json")
        if cross_ids_json:
            try:
                cross_ids_data = json.loads(cross_ids_json)
            except json.JSONDecodeError:
                # Hidden field, ignore parse errors (existing behavior)
                return cleaned_data

            type_ids = [
                item.get("type_id")
                for item in cross_ids_data
                if item.get("type_id") and item.get("value")
            ]
            if type_ids:
                id_types_by_id = IdentifierType.objects.in_bulk(type_ids)
                for item in cross_ids_data:
                    type_id = item.get("type_id")
                    value = item.get("value")
                    if not type_id or not value:
                        continue
                    id_type = id_types_by_id.get(int(type_id)) if str(type_id).isdigit() else id_types_by_id.get(type_id)
                    if id_type:
                        # attach the error to the hidden field; the UI can show a generic message
                        _validate_by_type_name(id_type.name, value, "cross_identifiers_json")

        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        primary_label, secondary_label = self._get_id_labels()
        self.fields["primary_id"].label = primary_label
        self.fields["secondary_id"].label = secondary_label
        if self.instance and self.instance.pk:
            pid = self.instance.primary_id
            sid = self.instance.secondary_id
            
            self.fields["primary_id"].initial = (
                pid if pid and not pid.upper().startswith("NO ") else ""
            )
            self.fields["secondary_id"].initial = (
                sid if sid and not sid.upper().startswith("NO ") else ""
            )

    def save(self, commit=True, **kwargs):
        user = kwargs.get("user")
        instance = super().save(commit=False, **kwargs)
        if commit:
            instance.save()
            from .models import IdentifierType, CrossIdentifier
            import json

            # Helper to update cross ID
            def update_priority_cross_id(priority, value):
                try:
                    if not value:
                        # If empty, delete it
                        CrossIdentifier.objects.filter(
                            individual=instance, id_type__use_priority=priority
                        ).delete()
                    else:
                        id_type = (
                            IdentifierType.objects.filter(use_priority=priority)
                            .order_by("id")
                            .first()
                        )
                        if not id_type:
                            return

                        # Enforce a single ID for a given priority
                        CrossIdentifier.objects.filter(
                            individual=instance, id_type__use_priority=priority
                        ).exclude(id_type=id_type).delete()

                        defaults = {"id_value": value}
                        if user:
                            defaults["created_by"] = user

                        obj, created = CrossIdentifier.objects.get_or_create(
                            individual=instance,
                            id_type=id_type,
                            defaults=defaults
                        )
                        if not created and obj.id_value != value:
                            obj.id_value = value
                            obj.save()
                except Exception:
                    pass

            update_priority_cross_id(1, self.cleaned_data.get("primary_id"))
            update_priority_cross_id(2, self.cleaned_data.get("secondary_id"))

            # Handle dynamic cross IDs
            cross_ids_json = self.cleaned_data.get("cross_identifiers_json")
            if cross_ids_json:
                try:
                    cross_ids_data = json.loads(cross_ids_json)
                    # {type_id: value} mapping
                    current_ids_map = {
                        str(item["type_id"]): item["value"] 
                        for item in cross_ids_data 
                        if item.get("value")
                    }

                    # Get existing IDs distinct from primary/secondary
                    excluded_priorities = [1, 2]
                    existing_ids = CrossIdentifier.objects.filter(
                        individual=instance
                    ).exclude(id_type__use_priority__in=excluded_priorities)

                    # Update/Delete existing
                    for xid in existing_ids:
                        type_str = str(xid.id_type.id)
                        if type_str in current_ids_map:
                            if xid.id_value != current_ids_map[type_str]:
                                xid.id_value = current_ids_map[type_str]
                                xid.save()
                            del current_ids_map[type_str]
                        else:
                            xid.delete()

                    # Create new
                    for type_id, value in current_ids_map.items():
                        try:
                            id_type = IdentifierType.objects.get(id=type_id)
                            if id_type.use_priority in excluded_priorities:
                                continue
                            
                            CrossIdentifier.objects.create(
                                individual=instance,
                                id_type=id_type,
                                id_value=value,
                                created_by=user if user else instance.created_by
                            )
                        except IdentifierType.DoesNotExist:
                            pass
                except json.JSONDecodeError:
                    pass
            
        return instance


class IndividualDemographicsForm(BaseForm):
    # Map is_alive (boolean) to Vital Status selection
    vital_status = forms.ChoiceField(
        choices=[("alive", "Alive"), ("deceased", "Deceased")],
        required=True,
        widget=forms.Select(attrs={"class": "select select-bordered w-full"})
    )

    class Meta:
        model = Individual
        fields = ["sex", "birth_date", "family"]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["vital_status"].initial = "alive" if self.instance.is_alive else "deceased"
        
        # Family field - use standard select but filter slightly? 
        # Or just allow all. BaseForm styles it.

    def save(self, commit=True, **kwargs):
        # Consume user if passed, as views pass it
        user = kwargs.get("user")
        instance = super().save(commit=False)
        instance.is_alive = (self.cleaned_data.get("vital_status") == "alive")
        if commit:
            instance.save()
        return instance


class ClinicalSummaryForm(BaseForm):
    class Meta:
        model = Individual
        fields = [
            "diagnosis",
            "diagnosis_date",
            "age_of_onset",
            "is_affected",
            "icd11_code",
        ]
        widgets = {
            "diagnosis_date": forms.DateInput(attrs={"type": "date"}),
            "diagnosis": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": "textarea textarea-bordered",
                    "placeholder": "Enter diagnosis...",
                }
            ),
            "icd11_code": forms.TextInput(
                attrs={
                    "placeholder": "e.g. LDBS",
                }
            ),
        }


# ---------------------------------------------------------------------------
# Configuration model forms
# ---------------------------------------------------------------------------

class SampleTypeForm(BaseForm):
    class Meta:
        model = SampleType
        fields = ["name", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class TestTypeForm(BaseForm):
    class Meta:
        model = TestType
        fields = [
            "name",
            "description",
            "positive_report_template",
            "negative_report_template",
            "default_positive_comment_text",
            "default_negative_result_text",
            "default_method_text",
            "default_total_reads_text",
            "default_coverage_20x_text",
            "default_mean_depth_text",
            "default_filtering_text",
            "default_limitations_text",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "default_positive_comment_text": forms.Textarea(attrs={"rows": 6, "class": "textarea textarea-bordered w-full h-40"}),
            "default_negative_result_text": forms.Textarea(attrs={"rows": 6, "class": "textarea textarea-bordered w-full h-40"}),
            "default_method_text": forms.Textarea(attrs={"rows": 6, "class": "textarea textarea-bordered w-full h-40"}),
            "default_filtering_text": forms.Textarea(attrs={"rows": 6, "class": "textarea textarea-bordered w-full h-40"}),
            "default_limitations_text": forms.Textarea(attrs={"rows": 6, "class": "textarea textarea-bordered w-full h-40"}),
        }
        labels = {
            "positive_report_template": "Positive report template",
            "negative_report_template": "Negative report template",
            "default_positive_comment_text": "Default positive comment text",
            "default_negative_result_text": "Default negative result text",
            "default_method_text": "Method text",
            "default_total_reads_text": "Total reads",
            "default_coverage_20x_text": "Coverage (20x)",
            "default_mean_depth_text": "Mean depth",
            "default_filtering_text": "Filtering text",
            "default_limitations_text": "Limitations text",
        }
        help_texts = {
            "default_positive_comment_text": "Supports report placeholders like {{GENE_TRANSCRIPT_BLOCK}}, {{VARIANT_DETAILS_BLOCK}}, {{ZYGOSITY}}, {{CLASSIFICATION_BLOCK}}, and {{HPO_TERMS}}.",
            "default_negative_result_text": "Supports report placeholders like {{HPO_TERMS}} and other report tokens.",
        }


class InstitutionConfigForm(BaseForm):
    class Meta:
        model = Institution
        fields = [
            "name", "official_name", "center_name",
            "speciality", "city", "contact",
            "latitude", "longitude",
        ]
        widgets = {
            "contact": forms.Textarea(attrs={"rows": 3}),
        }


class PipelineTypeForm(BaseForm):
    class Meta:
        model = PipelineType
        fields = ["name", "description", "version", "source_url", "results_url", "parent_types"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class AnalysisTypeForm(BaseForm):
    class Meta:
        model = AnalysisType
        fields = ["name", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class IdentifierTypeForm(BaseForm):
    class Meta:
        model = IdentifierType
        fields = ["name", "description", "use_priority", "is_shown_in_table"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class StatusGroupConfigForm(BaseForm):
    class Meta:
        model = StatusGroup
        fields = ["name", "content_type"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["content_type"].queryset = (
            ContentType.objects.filter(app_label__in=["lab", "variant"])
            .exclude(model__startswith="historical")
            .order_by("app_label", "model")
        )
        self.fields["content_type"].required = False
        self.fields["content_type"].empty_label = "— Global (applies to all) —"


class StatusConfigForm(BaseForm):
    color = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"type": "color", "class": "input input-bordered w-16 h-10 p-1 cursor-pointer"}),
        help_text="Pick a colour for this status badge.",
        initial="#6b7280",
    )

    class Meta:
        model = Status
        fields = ["name", "short_name", "description", "color", "content_type", "icon", "group"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "icon": forms.TextInput(attrs={"placeholder": "e.g. fa-solid fa-check"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show a human-readable label for the content_type choices
        self.fields["content_type"].queryset = (
            ContentType.objects.filter(app_label__in=["lab", "variant"])
            .exclude(model__startswith="historical")
            .order_by("app_label", "model")
        )
        self.fields["content_type"].required = False
        self.fields["content_type"].empty_label = "— Global (applies to all) —"
        # Filter group dropdown to match the current content_type
        instance = self.instance
        if instance and instance.pk and instance.content_type_id:
            self.fields["group"].queryset = StatusGroup.objects.filter(
                content_type_id=instance.content_type_id
            )
        else:
            self.fields["group"].queryset = StatusGroup.objects.all()
        self.fields["group"].required = False
        self.fields["group"].empty_label = "— No group (freely toggleable) —"
        # If the stored value is a hex string, the color input handles it natively
        if instance and instance.pk:
            raw = instance.color or ""
            if raw and not raw.startswith("#"):
                # Stored as a named colour – keep as-is; color input might not show it
                self.fields["color"].widget = forms.TextInput(
                    attrs={"class": "input input-bordered w-full", "placeholder": "e.g. #6b7280 or gray"}
                )


class FamilyConfigForm(BaseForm):
    class Meta:
        model = Family
        fields = ["family_id", "is_consanguineous", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class QuickAddMemberForm(forms.ModelForm):
    """Minimal form for adding a new individual to a family from the manage-members modal."""

    primary_id = forms.CharField(required=False, label="Primary ID")
    secondary_id = forms.CharField(required=False, label="Secondary ID")

    statuses = forms.ModelMultipleChoiceField(
        queryset=Status.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "select select-bordered select-sm w-full", "size": "3"}),
    )

    class Meta:
        model = Individual
        fields = ["full_name", "sex", "is_index", "is_affected"]
        widgets = {
            "full_name": forms.TextInput(attrs={
                "class": "input input-bordered input-sm w-full",
                "placeholder": "Full name",
            }),
            "sex": forms.Select(attrs={"class": "select select-bordered select-sm w-full"}),
            "is_index": forms.CheckboxInput(attrs={"class": "checkbox checkbox-sm checkbox-primary"}),
            "is_affected": forms.CheckboxInput(attrs={"class": "checkbox checkbox-sm checkbox-warning"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Individual)
        self.fields["statuses"].queryset = Status.objects.filter(content_type=ct).order_by("name")
        self.fields["full_name"].required = True
        # Set dynamic labels from IdentifierType
        primary_type = IdentifierType.objects.filter(use_priority=1).order_by("id").first()
        secondary_type = IdentifierType.objects.filter(use_priority=2).order_by("id").first()
        self.fields["primary_id"].label = f"{primary_type.name} ID" if primary_type else "Primary ID"
        self.fields["secondary_id"].label = f"{secondary_type.name} ID" if secondary_type else "Secondary ID"
        self.fields["primary_id"].widget = forms.TextInput(attrs={
            "class": "input input-bordered input-sm w-full",
            "placeholder": self.fields["primary_id"].label,
        })
        self.fields["secondary_id"].widget = forms.TextInput(attrs={
            "class": "input input-bordered input-sm w-full",
            "placeholder": self.fields["secondary_id"].label,
        })
