# forms.py
from django import forms
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
    Pipeline, # Added Pipeline
    PipelineType, # Added PipelineType
    Institution,
    Family,
    AnalysisType,
    AnalysisRequestForm,
    AnalysisReport
)
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q


class BaseForm(forms.ModelForm):
    """Base form class with consistent styling for all form fields"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Limit status choices strictly to model-specific statuses
        if "status" in self.fields and hasattr(self, '_meta') and hasattr(self._meta, 'model'):
            from django.contrib.contenttypes.models import ContentType
            from .models import Status
            try:
                model_ct = ContentType.objects.get_for_model(self._meta.model)
                self.fields["status"].queryset = Status.objects.filter(content_type=model_ct).order_by("name")
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

        return obj


class ProjectForm(BaseForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    class Meta:
        model = Project
        fields = ["name", "description", "due_date", "priority", "status"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }


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
        instance = kwargs.get("instance")
        super().__init__(*args, **kwargs)
        # Remove StatusLog filtering logic; just show all Status objects
        self.fields["project"].queryset = Project.objects.all().order_by("name")
        
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


class IndividualForm(BaseForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    class Meta:
        model = Test
        fields = [
            "sample",
            "test_type",
            "performed_date",
            "performed_by",
            "status",
            "service_send_date",
            "data_receipt_date",
        ]
        widgets = {
            "performed_date": forms.DateInput(attrs={"type": "date"}),
            "service_send_date": forms.DateInput(attrs={"type": "date"}),
            "data_receipt_date": forms.DateInput(attrs={"type": "date"}),
        }


class PipelineForm(BaseForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    class Meta:
        model = Pipeline
        fields = [
            "test",
            "type",
            "performed_date",
            "performed_by",
            "status",
        ]
        widgets = {
            "performed_date": forms.DateInput(attrs={"type": "date"}),
        }


class AnalysisForm(BaseForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    class Meta:
        model = Analysis
        fields = [
            "type",
            "performed_date",
            "performed_by",
            "status",
            "pipeline"
        ]
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
    class Meta:
        model = AnalysisReport
        fields = ["file", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


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
        

    class Meta:
        model = Individual
        fields = [
            "full_name",
            "tc_identity",
            "birth_date",
            "sex",
            "status",
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
    lab_id = forms.CharField(required=False, label="Lab ID")
    biobank_id = forms.CharField(required=False, label="Biobank ID")
    tc_identity = forms.IntegerField(required=False, label="TC Identity")
    cross_identifiers_json = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Individual
        fields = ["full_name", "tc_identity"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            lid = self.instance.lab_id
            bid = self.instance.biobank_id
            
            self.fields["lab_id"].initial = lid if "No Lab ID" not in lid else ""
            self.fields["biobank_id"].initial = bid if "No Biobank ID" not in bid else ""

    def save(self, commit=True, **kwargs):
        user = kwargs.get("user")
        instance = super().save(commit=False, **kwargs)
        if commit:
            instance.save()
            from .models import IdentifierType, CrossIdentifier
            import json

            # Helper to update cross ID
            def update_cross_id(type_name, value):
                try:
                    id_type = IdentifierType.objects.get(name=type_name)
                    if not value:
                        # If empty, delete it
                        CrossIdentifier.objects.filter(
                            individual=instance, id_type=id_type
                        ).delete()
                    else:
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
                except IdentifierType.DoesNotExist:
                    pass 
                except Exception:
                    pass

            update_cross_id("RareBoost", self.cleaned_data.get("lab_id"))
            update_cross_id("Biobank", self.cleaned_data.get("biobank_id"))

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

                    # Get existing IDs distinct from RB/Biobank
                    excluded_types = ["RareBoost", "Biobank"]
                    existing_ids = CrossIdentifier.objects.filter(
                        individual=instance
                    ).exclude(id_type__name__in=excluded_types)

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
                            if id_type.name in excluded_types:
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

