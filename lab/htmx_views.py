from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django import forms
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.core.paginator import Paginator
from django.views.generic import View
from django.apps import apps
from .models import Individual, Family



class RevealSensitiveFieldView(View):
    def get(self, request, model_name, pk, field_name):
        if not request.user.has_perm("lab.view_sensitive_data"):
            return HttpResponse("<span>(Redacted - Permission Denied)</span>")

        try:
            Model = apps.get_model("lab", model_name)
        except LookupError:
            return HttpResponse("<span>(Error: Invalid Model)</span>")

        obj = get_object_or_404(Model, pk=pk)

        # Basic security check: ensure the field exists
        if not hasattr(obj, field_name):
            return HttpResponse("<span>(Error: Invalid Field)</span>")

        # Determine if we are hiding or revealing
        action = request.GET.get("action", "reveal")

        if action == "hide":
             # Return the masked version
             # We use different masks based on field name conventions
            mask = "**-**-****" if "birth_date" in field_name else "*****"
            
            # The id of the wrapper span must allow for future swaps (reveal)
            # We must target the parent or replace itself. 
            # The initial template has:
            # <span id="...-reveal-..."> *** <button ... hx-target="#...-reveal-..." hx-swap="outerHTML">Reveal</button> </span>
            # So we return the OUTER HTML of that span.
            
            # Construct the ID to match what the template expects.
            # In template: id="name-reveal-{{ individual.pk }}"
            # We don't have the exact ID prefix ('name', 'dob') easily available from just 'field_name' generic view unless we map it.
            # However, HTMX `hx-target="this"` or `hx-target="closest span"` is better.
            # BUT the original template used specific IDs.
            # Let's see: `hx-target="#dob-reveal-{{ individual.pk }}"`.
            # If I return a new span with the SAME ID, it works.
            
            # Map field_name to ID prefix for reconstruction (fragile but matches strict current template)
            prefix = "name" if "name" in field_name else "dob" if "birth" in field_name else "field"
            span_id = f"{prefix}-reveal-{pk}"
            
            html = f"""
            <span id="{span_id}" class="reveal-wrapper">
                {mask}
                <button class="btn btn-xs btn-ghost text-primary" 
                        hx-get="{request.path}"
                        hx-target="closest .reveal-wrapper"
                        hx-swap="outerHTML">
                    <i class="fa-solid fa-eye"></i>
                </button>
            </span>
            """
            return HttpResponse(html)

        # Log access only on REVEAL, not on hide (though hiding is harmless)
        # We also Log if they access the 'reveal' view.
        from django.contrib.contenttypes.models import ContentType

        # Access the field (triggering decryption if it's an EncryptedField)
        value = getattr(obj, field_name)
        
        # Determine ID again
        prefix = "name" if "name" in field_name else "dob" if "birth" in field_name else "field"
        span_id = f"{prefix}-reveal-{pk}"

        # Render value with HIDE button
        # Auto-hide after 30s using Alpine for extra security
        html = f"""
        <span id="{span_id}" class="reveal-wrapper" x-data="{{ shown: true }}" x-init="setTimeout(() => htmx.trigger($el.querySelector('.hide-btn'), 'click'), 30000)">
            {value}
            <button class="btn btn-xs btn-ghost text-base-content/50 hide-btn" 
                    hx-get="{request.path}?action=hide"
                    hx-target="closest .reveal-wrapper"
                    hx-swap="outerHTML">
                <i class="fa-solid fa-eye-slash"></i>
            </button>
        </span>
        """
        return HttpResponse(html)


def add_individual_row(request):
    if not request.user.has_perm("lab.add_individual"):
        return HttpResponse("")
    
    from .forms import IndividualInlineForm
    
    # Get the current number of forms to set the correct prefix
    num_forms = int(request.GET.get("num_forms", 0))
    form = IndividualInlineForm(prefix=f"individuals-{num_forms}")
    
    return render(request, "lab/partials/individual_form_row.html", {"form": form})

class IndividualHPOEditView(View):
    def get(self, request, pk):
        individual = get_object_or_404(Individual, pk=pk)
        return render(request, "lab/partials/tabs/_phenotype.html#hpo_edit", {"individual": individual})

@login_required
@require_POST
def manage_hpo_term(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    action = request.POST.get("action")
    term_id = request.POST.get("term_id")
    
    from ontologies.models import Term
    term = get_object_or_404(Term, pk=term_id)
    
    if action == "add":
        individual.hpo_terms.add(term)
    elif action == "remove":
        individual.hpo_terms.remove(term)
        
    return render(request, "lab/partials/tabs/_phenotype.html#hpo_edit_list", {"individual": individual})
    return render(request, "lab/partials/tabs/_phenotype.html#hpo_edit_list", {"individual": individual})

# Note Views

@login_required
@require_POST
def note_create(request):
    """Create a new note for a specific object"""
    from .models import Note
    from django.contrib.contenttypes.models import ContentType
    
    content_type_str = request.POST.get("content_type")
    object_id = request.POST.get("object_id")
    
    try:
        model = None
        if "." in content_type_str:
            app_label, model_name = content_type_str.split(".")
            model = apps.get_model(app_label, model_name)
        else:
             try:
                 # Try 'lab' first
                 model = apps.get_model("lab", content_type_str)
             except LookupError:
                 # Try by model name via ContentType
                 try:
                     ct = ContentType.objects.get(model=content_type_str.lower())
                     model = ct.model_class()
                 except ContentType.DoesNotExist:
                     pass

        if not model:
             return HttpResponse(f"Error: Invalid content type '{content_type_str}'", status=400)

        content_type = ContentType.objects.get_for_model(model)
        
        # Create the note
        is_private = request.POST.get("private") in ["1", "true", "on", "True"]
        Note.objects.create(
            content=request.POST.get("content"),
            user=request.user,
            private_owner=request.user if is_private else None,
            content_type=content_type,
            object_id=object_id,
        )
        
        # Handle HTMX response
        notes = Note.objects.filter(
            content_type=content_type, 
            object_id=object_id
        ).select_related('user', 'private_owner')
        
        visible_notes = []
        for n in notes:
            if n.private_owner and n.private_owner != request.user:
                continue
            visible_notes.append(n)
            
        context = {
            "notes": visible_notes,
            "content_type": content_type_str,
            "object": {"id": object_id},
            "user": request.user,
        }
        
        response = render(request, "lab/partials/notes/list.html", context)
        response["HX-Trigger"] = f"noteCountUpdate-{content_type_str}-{object_id}"
        return response

    except Exception as e:
        import traceback
        traceback.print_exc()
        return HttpResponse(f"Error creating note: {str(e)}", status=500)

@login_required
@require_POST
def note_update(request, pk):
    """Update an existing note"""
    from .models import Note
    note = get_object_or_404(Note, id=pk)

    # Only allow the note creator or staff to edit
    if request.user == note.user or request.user.is_staff:
        note.content = request.POST.get("content")
        note.save()
        
        # Return the updated item
        return render(request, "lab/partials/notes/item.html", {"note": note, "user": request.user})

    return HttpResponseForbidden()

@login_required
def note_delete(request, pk):
    from .models import Note
    if request.method == "DELETE":
        note = get_object_or_404(Note, id=pk)
        
        content_type = note.content_type
        content_type_str = content_type.model
        object_id = note.object_id

        # Only allow the note creator or staff to delete
        if request.user == note.user or request.user.is_staff:
            note.delete()
            
            # Fetch remaining notes
            notes = Note.objects.filter(
                content_type=content_type, 
                object_id=object_id
            ).select_related('user', 'private_owner')
            
            visible_notes = [n for n in notes if not n.private_owner or n.private_owner == request.user]
            
            context = {
                "notes": visible_notes,
                "content_type": content_type_str,
                "object": {"id": object_id},
                "user": request.user
            }
            
            response = render(request, "lab/partials/notes/list.html", context)
            response["HX-Trigger"] = f"noteCountUpdate-{content_type_str}-{object_id}"
            return response

        return HttpResponseForbidden()
    return HttpResponseForbidden()

@login_required
def note_list(request):
    """Return the list of notes (e.g. for modal)"""
    from .models import Note
    from django.contrib.contenttypes.models import ContentType
    
    content_type_str = request.GET.get("content_type")
    object_id = request.GET.get("object_id")
    
    if not content_type_str or not object_id:
        return HttpResponse("Missing params")
        
    try:
        model = apps.get_model("lab", content_type_str) # defaults to lab for simplicity
        content_type = ContentType.objects.get_for_model(model)
        
        notes = Note.objects.filter(
            content_type=content_type, 
            object_id=object_id
        ).select_related('user', 'private_owner')
        
        visible_notes = [n for n in notes if not n.private_owner or n.private_owner == request.user]
        
        context = {
            "notes": visible_notes,
            "content_type": content_type_str,
            "object": {"id": object_id}, # Mock
            "user": request.user
        }
        return render(request, "lab/partials/notes/list.html", context)
    except Exception:
        return HttpResponse("Error loading notes")

@login_required
def note_count(request):
    """Return the summary badge"""
    from .models import Note
    from django.contrib.contenttypes.models import ContentType
    
    content_type_str = request.GET.get("content_type")
    object_id = request.GET.get("object_id")
    
    try:
        model = apps.get_model("lab", content_type_str)
        content_type = ContentType.objects.get_for_model(model)
        
        notes = Note.objects.filter(
            content_type=content_type, 
            object_id=object_id
        )
        
        # Count visible
        count = 0
        for n in notes:
            if not n.private_owner or n.private_owner == request.user:
                count += 1
        
        template_name = request.GET.get("template", "lab/partials/notes/summary_content.html")
        context = {
            "note_count": count,
            "object": {"id": object_id},
            "content_type": content_type_str
        }
        return render(request, template_name, context)
    except Exception:
         return HttpResponse("")

@login_required
def individual_identification_edit(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    from .forms import IndividualIdentificationForm
    from .models import IdentifierType
    form = IndividualIdentificationForm(instance=individual)
    
    # Exclude RareBoost and Biobank from general choices if desired, or keep all
    # The plan said to filter them out from the dropdown to avoid confusion
    identifier_types = IdentifierType.objects.exclude(name__in=["RareBoost", "Biobank"])
    
    context = {
        "individual": individual, 
        "form": form, 
        "edit_mode": True,
        "identifier_types": identifier_types
    }
    return render(request, "lab/partials/tabs/_info.html#identification_content", context)

@login_required
@require_POST
def individual_identification_save(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    from .forms import IndividualIdentificationForm
    form = IndividualIdentificationForm(request.POST, instance=individual)
    
    if form.is_valid():
        form.save(user=request.user)
        # Render display mode
        context = {"individual": individual, "edit_mode": False}
        return render(request, "lab/partials/tabs/_info.html#identification_content", context)
    
    # Render edit mode with errors
    context = {"individual": individual, "form": form, "edit_mode": True}
    return render(request, "lab/partials/tabs/_info.html#identification_content", context)

@login_required
def individual_demographics_edit(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    from .forms import IndividualDemographicsForm
    form = IndividualDemographicsForm(instance=individual)
    context = {"individual": individual, "form": form, "edit_mode": True}
    return render(request, "lab/partials/tabs/_info.html#demographics_content", context)

@login_required
@require_POST
def individual_demographics_save(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    from .forms import IndividualDemographicsForm
    form = IndividualDemographicsForm(request.POST, instance=individual)
    
    if form.is_valid():
        form.save(user=request.user)
        # Render display mode
        context = {"individual": individual, "edit_mode": False}
        return render(request, "lab/partials/tabs/_info.html#demographics_content", context)
    
    # Render edit mode with errors
    context = {"individual": individual, "form": form, "edit_mode": True}
    return render(request, "lab/partials/tabs/_info.html#demographics_content", context)


@login_required
def individual_identification_display(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    context = {"individual": individual, "edit_mode": False}
    return render(request, "lab/partials/tabs/_info.html#identification_content", context)


@login_required
def individual_demographics_display(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    context = {"individual": individual, "edit_mode": False}
    return render(request, "lab/partials/tabs/_info.html#demographics_content", context)
@login_required
def individual_demographics_display(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    context = {"individual": individual, "edit_mode": False}
    return render(request, "lab/partials/tabs/_info.html#demographics_content", context)


@login_required
def family_search(request):
    query = request.GET.get("q", "")
    page_number = request.GET.get("page", 1)
    
    families = Family.objects.all()
    if query:
        families = families.filter(
            Q(family_id__icontains=query) | Q(description__icontains=query)
        )
    
    # Simple pagination
    paginator = Paginator(families.order_by("-id"), 10)
    page_obj = paginator.get_page(page_number)
    
    context = {"page_obj": page_obj, "query": query}
    return render(request, "lab/partials/family_picker_results.html", context)


@login_required
def individual_clinical_summary_edit(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    from .forms import ClinicalSummaryForm
    form = ClinicalSummaryForm(instance=individual)
    context = {"individual": individual, "form": form, "edit_mode": True}
    return render(request, "lab/partials/tabs/_phenotype.html#clinical_summary_content", context)


@login_required
@require_POST
def individual_clinical_summary_save(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    from .forms import ClinicalSummaryForm
    form = ClinicalSummaryForm(request.POST, instance=individual)
    
    if form.is_valid():
        form.save(user=request.user)
        # Render display mode
        context = {"individual": individual, "edit_mode": False}
        return render(request, "lab/partials/tabs/_phenotype.html#clinical_summary_content", context)
    
    # Render edit mode with errors
    context = {"individual": individual, "form": form, "edit_mode": True}
    return render(request, "lab/partials/tabs/_phenotype.html#clinical_summary_content", context)


@login_required
def individual_clinical_summary_display(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    context = {"individual": individual, "edit_mode": False}
    return render(request, "lab/partials/tabs/_phenotype.html#clinical_summary_content", context)


@login_required
@require_POST
def update_status(request, content_type_id, object_id, status_id):
    """
    Update the status of an object.
    Targets Sample, Test, or Pipeline in this context.
    """
    from django.contrib.contenttypes.models import ContentType
    from .models import Status
    
    ct = get_object_or_404(ContentType, pk=content_type_id)
    Model = ct.model_class()
    obj = get_object_or_404(Model, pk=object_id)
    new_status = get_object_or_404(Status, pk=status_id)
    
    # Permission check (generic for now, can be specialized)
    # Check if user can change the specific model
    perm = f"{ct.app_label}.change_{ct.model}"
    if not request.user.has_perm(perm):
         return HttpResponseForbidden("You do not have permission to change this status.")
    
    obj.status = new_status
    obj.save()
    
    # Return the updated badge partial. 
    # Since the badge depends on the object type (Sample vs Test vs Pipeline),
    # we need to know which partial to render.
    # In _workflow.html, we'll define partialdefs for these badges to make it easy.
    
    context = {
        ct.model: obj, # e.g. 'sample': obj
        "status": new_status,
        "individual": obj if isinstance(obj, Individual) else (
            getattr(obj, "individual", None) or 
            getattr(getattr(obj, "sample", None), "individual", None) or 
            getattr(getattr(getattr(obj, "test", None), "sample", None), "individual", None)
        )
    }
    
    # Determine which partial to return
    partial_name = f"{ct.model}_status_badge"
    
    # We need a template that has these partialdefs. _workflow.html is perfect.
    response = render(request, f"lab/partials/tabs/_workflow.html#{partial_name}", context)
    
    # If updating an Individual, also trigger an OOB swap for the table row
    if isinstance(obj, Individual):
        from lab.tables import IndividualTable
        table = IndividualTable([])
        status_html = table.render_status(obj.status.name, obj)
        # The span needs hx-swap-oob="true" for HTMX to match it by ID
        oob_html = status_html.replace('<span ', '<span hx-swap-oob="true" ')
        # Append to response content
        response.content += oob_html.encode("utf-8")
        
    return response

@login_required
def sample_create_modal(request, individual_id):
    """Render a sample creation form or handle submission"""
    from .forms import SampleForm
    from .models import Individual, Status
    
    individual = get_object_or_404(Individual, pk=individual_id)
    
    if request.method == "POST":
        form = SampleForm(request.POST)
        form.fields["individual"].queryset = Individual.objects.filter(pk=individual.pk)
        form.fields["individual"].required = False  # disabled fields are not submitted
        if form.is_valid():
            sample = form.save(commit=False)
            sample.individual = individual
            sample.created_by = request.user
            # Ensure status is set if not in form
            if not sample.status_id:
                status = Status.objects.filter(name__iexact="Registered").first() or Status.objects.first()
                sample.status = status
            sample.save()
            
            response = HttpResponse(status=204)
            response["HX-Trigger"] = '{"workflowRefreshed": true, "closeModal": true}'
            return response
    else:
        # Initial form: pre-set individual and default status
        initial = {"individual": individual}
        status = Status.objects.filter(name__iexact="Registered").first() or Status.objects.first()
        if status:
            initial["status"] = status
            
        form = SampleForm(initial=initial)
        form.fields["individual"].queryset = Individual.objects.filter(pk=individual.pk)
        # Individual is fixed – show it but make it non-interactable
        form.fields["individual"].disabled = True
        form.fields["individual"].widget.attrs["class"] = (
            form.fields["individual"].widget.attrs.get("class", "")
            + " pointer-events-none bg-base-200/60"
        )

    context = {
        "form": form,
        "individual": individual,
        "title": "Add New Sample",
        "action_url": request.path,
    }
    return render(request, "lab/partials/generic_modal_form.html", context)


@login_required
def test_create_modal(request, sample_id):
    """Render a test creation form or handle submission"""
    from .forms import TestForm
    from .models import Sample, Status
    
    sample = get_object_or_404(Sample, pk=sample_id)
    individual = sample.individual
    
    if request.method == "POST":
        form = TestForm(request.POST)
        form.fields["sample"].queryset = Sample.objects.filter(pk=sample.pk)
        form.fields["sample"].required = False  # disabled fields are not submitted
        if form.is_valid():
            test = form.save(commit=False)
            test.sample = sample
            test.created_by = request.user
            # Ensure status is set
            if not test.status_id:
                status = Status.objects.filter(name__iexact="Registered").first() or Status.objects.first()
                test.status = status
            test.save()
            
            response = HttpResponse(status=204)
            response["HX-Trigger"] = '{"workflowRefreshed": true, "closeModal": true}'
            return response
    else:
        initial = {"sample": sample}
        status = Status.objects.filter(name__iexact="Registered").first() or Status.objects.first()
        if status:
            initial["status"] = status
            
        form = TestForm(initial=initial)
        form.fields["sample"].queryset = Sample.objects.filter(pk=sample.pk)
        # Sample is fixed – show it but make it non-interactable
        form.fields["sample"].disabled = True
        form.fields["sample"].widget.attrs["class"] = (
            form.fields["sample"].widget.attrs.get("class", "")
            + " pointer-events-none bg-base-200/60"
        )
        # Hide created_by if it's in the form (TestForm has it)
        if "created_by" in form.fields:
            form.fields["created_by"].widget = forms.HiddenInput()

    context = {
        "form": form,
        "individual": individual,
        "sample": sample,
        "title": f"Add Test for Sample {sample.id}",
        "action_url": request.path,
    }
    return render(request, "lab/partials/generic_modal_form.html", context)


@login_required
def pipeline_create_modal(request, test_id):
    """Render a pipeline creation form or handle submission"""
    from .forms import PipelineForm
    from .models import Test, Status
    
    test = get_object_or_404(Test, pk=test_id)
    individual = test.sample.individual
    
    if request.method == "POST":
        form = PipelineForm(request.POST)
        form.fields["test"].queryset = Test.objects.filter(pk=test.pk)
        form.fields["test"].required = False  # disabled fields are not submitted
        if form.is_valid():
            pipeline = form.save(commit=False)
            pipeline.test = test
            pipeline.created_by = request.user
            # Ensure status is set
            if not pipeline.status_id:
                status = Status.objects.filter(name__iexact="Registered").first() or Status.objects.first()
                pipeline.status = status
            pipeline.save()
            
            response = HttpResponse(status=204)
            response["HX-Trigger"] = '{"workflowRefreshed": true, "closeModal": true}'
            return response
    else:
        initial = {"test": test}
        status = Status.objects.filter(name__iexact="Registered").first() or Status.objects.first()
        if status:
            initial["status"] = status
            
        form = PipelineForm(initial=initial)
        form.fields["test"].queryset = Test.objects.filter(pk=test.pk)
        # Test is fixed – show it but make it non-interactable
        form.fields["test"].disabled = True
        form.fields["test"].widget.attrs["class"] = (
            form.fields["test"].widget.attrs.get("class", "")
            + " pointer-events-none bg-base-200/60"
        )

    context = {
        "form": form,
        "individual": individual,
        "test": test,
        "title": f"Add Pipeline for Test {test.id}",
        "action_url": request.path,
    }
    return render(request, "lab/partials/generic_modal_form.html", context)


@login_required
def analysis_create_modal(request, pipeline_id):
    """Render an analysis creation form or handle submission"""
    from .forms import AnalysisForm
    from .models import Pipeline, Status
    
    pipeline = get_object_or_404(Pipeline, pk=pipeline_id)
    individual = pipeline.test.sample.individual
    
    if request.method == "POST":
        form = AnalysisForm(request.POST)
        form.fields["pipeline"].queryset = Pipeline.objects.filter(pk=pipeline.pk)
        form.fields["pipeline"].required = False  # disabled fields are not submitted
        if form.is_valid():
            analysis = form.save(commit=False)
            analysis.pipeline = pipeline
            analysis.created_by = request.user
            # Ensure status is set
            if not analysis.status_id:
                status = Status.objects.filter(name__iexact="Registered").first() or Status.objects.first()
                analysis.status = status
            analysis.save()
            
            response = HttpResponse(status=204)
            response["HX-Trigger"] = '{"workflowRefreshed": true, "closeModal": true}'
            return response
    else:
        initial = {"pipeline": pipeline}
        status = Status.objects.filter(name__iexact="Registered").first() or Status.objects.first()
        if status:
            initial["status"] = status
            
        form = AnalysisForm(initial=initial)
        form.fields["pipeline"].queryset = Pipeline.objects.filter(pk=pipeline.pk)
        # Pipeline is fixed – show it but make it non-interactable
        form.fields["pipeline"].disabled = True
        form.fields["pipeline"].widget.attrs["class"] = (
            form.fields["pipeline"].widget.attrs.get("class", "")
            + " pointer-events-none bg-base-200/60"
        )

    context = {
        "form": form,
        "individual": individual,
        "pipeline": pipeline,
        "title": f"Add Analysis for Pipeline {pipeline.id}",
        "action_url": request.path,
    }
    return render(request, "lab/partials/generic_modal_form.html", context)
@login_required
def task_create_modal(request, content_type_id, object_id):
    """Render a task creation form or handle submission"""
    from .forms import TaskForm
    from .models import Status, Individual, Sample, Test, Pipeline
    from django.contrib.contenttypes.models import ContentType
    
    ct = get_object_or_404(ContentType, pk=content_type_id)
    Model = ct.model_class()
    obj = get_object_or_404(Model, pk=object_id)
    
    
    # Determine target ID and partial name
    target_id = "#workflow-content" # fallback
    partial_name = ""
    count_id = ""
    
    individual = None
    if isinstance(obj, Individual):
        target_id = f"#individual-tasks-{obj.id}"
        partial_name = "individual_tasks"
        count_id = f"task-count-individual-{obj.id}"
        individual = obj
    elif isinstance(obj, Sample):
        target_id = f"#sample-tasks-{obj.id}"
        partial_name = "sample_tasks"
        count_id = f"task-count-sample-{obj.id}"
        individual = obj.individual
    elif isinstance(obj, Test):
        target_id = f"#test-tasks-{obj.id}"
        partial_name = "test_tasks"
        count_id = f"task-count-test-{obj.id}"
        individual = obj.sample.individual
    elif isinstance(obj, Pipeline):
        # Pipeline tasks might need similar handling if added to the view
        individual = obj.test.sample.individual
        pass

    if request.method == "POST":
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.content_type = ct
            task.object_id = object_id
            task.created_by = request.user
            # Ensure status is set
            if not task.status_id:
                status = Status.objects.filter(name__iexact="Registered").first() or Status.objects.first()
                task.status = status
            task.save()
            
            # Targeted update for task list
            context = {
                "individual": individual, 
                "sample": obj if isinstance(obj, Sample) else None,
                "test": obj if isinstance(obj, Test) else None,
            }
            
            # Render the specific partial for the list
            response = render(request, f"lab/partials/tabs/_workflow.html#{partial_name}", context)
            
            # OOB Swap for Task Count
            count = obj.tasks.count()
            oob_html = f'''
            <div id="{count_id}" hx-swap-oob="true" 
                 class="flex items-center gap-1.5 tooltip tooltip-bottom" 
                 data-tip="{count} Tasks">
                <i class="fa-solid fa-list-check"></i> {count}
            </div>
            '''
            response.content += oob_html.encode("utf-8")
            return response
            
    else:
        initial = {"content_type": ct.pk, "object_id": object_id}
        status = Status.objects.filter(name__iexact="Registered").first() or Status.objects.filter(content_type__model="task").first() or Status.objects.first()
        if status:
            initial["status"] = status
            
        form = TaskForm(initial=initial, content_object=obj)
        # Hide generic fields
        form.fields["content_type"].widget = forms.HiddenInput()
        form.fields["object_id"].widget = forms.HiddenInput()

    # Make associated type & object visible, descriptive, and non-interactable
    from django import forms as dj_forms
    form.fields["content_type"].disabled = True
    form.fields["content_type"].label = "Associated Type"
    form.fields["content_type"].initial = Model._meta.verbose_name.title()
    form.fields["content_type"].widget = dj_forms.TextInput(
        attrs={
            "class": "input input-bordered w-full pointer-events-none bg-base-200/60",
            "readonly": True,
        }
    )

    form.fields["object_id"].disabled = True
    form.fields["object_id"].label = "Associated Object"
    form.fields["object_id"].initial = str(obj)
    form.fields["object_id"].widget = dj_forms.TextInput(
        attrs={
            "class": "input input-bordered w-full pointer-events-none bg-base-200/60",
            "readonly": True,
        }
    )

    context = {
        "form": form,
        "individual": individual,
        "title": f"Add Task for {obj}",
        "action_url": request.path,
        "hx_target": target_id,
    }
    return render(request, "lab/partials/generic_modal_form.html", context)


@login_required
def individual_projects_edit(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    if request.GET.get("display"):
        return render(request, "lab/partials/tabs/_info.html#projects_display", {"individual": individual})
    return render(request, "lab/partials/tabs/_info.html#projects_edit", {"individual": individual})


@login_required
@require_POST
def individual_projects_save(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    # Expecting a list of project IDs
    project_ids = request.POST.getlist("projects")
    from .models import Project
    individual.projects.set(Project.objects.filter(id__in=project_ids))
    return render(request, "lab/partials/tabs/_info.html#projects_display", {"individual": individual})


@login_required
def project_search(request):
    from .models import Project
    query = request.GET.get("q", "")
    projects = Project.objects.all()
    if query:
        projects = projects.filter(name__icontains=query)
    return render(request, "lab/partials/project_picker_results.html", {"projects": projects[:10]})


@login_required
def document_preview(request, model_name, pk):
    """Render a document preview in the side drawer."""
    from django.apps import apps
    try:
        Model = apps.get_model("lab", model_name)
        obj = get_object_or_404(Model, pk=pk)
    except (LookupError, ValueError):
        return HttpResponse("Invalid model or object.")

    # Check permission (generic)
    if not request.user.has_perm("lab.view_analysisrequestform") and not request.user.is_staff:
        # A more complex permission check could be done here if needed
        return HttpResponseForbidden("You do not have permission to view this document.")

    context = {
        "object": obj,
        "model_name": model_name,
    }
    response = render(request, "lab/partials/preview_drawer.html", context)
    response["HX-Trigger"] = "open-preview"
    return response


@login_required
def request_form_create_modal(request, individual_id):
    """Render an analysis request form creation modal or handle submission"""
    from .forms import AnalysisRequestFormForm
    from .models import Individual
    
    individual = get_object_or_404(Individual, pk=individual_id)
    
    if request.method == "POST":
        form = AnalysisRequestFormForm(request.POST, request.FILES)
        if form.is_valid():
            req_form = form.save(commit=False)
            req_form.individual = individual
            req_form.created_by = request.user
            req_form.save()
            
            # Refresh the info tab's request forms display
            return render(request, "lab/partials/tabs/_info.html#request_forms_display", {"individual": individual})
    else:
        form = AnalysisRequestFormForm()

    context = {
        "form": form,
        "title": f"Upload Analysis Request Form for {individual.lab_id}",
        "action_url": request.path,
        "hx_target": f"#request-forms-card-{individual.pk} .card-body"
    }
    return render(request, "lab/partials/modals/upload_modal_form.html", context)


@login_required
def report_create_modal(request, pipeline_id):
    """Render an analysis report creation modal or handle submission"""
    from .forms import AnalysisReportForm
    from .models import Pipeline
    
    pipeline = get_object_or_404(Pipeline, pk=pipeline_id)
    individual = pipeline.test.sample.individual
    
    if request.method == "POST":
        form = AnalysisReportForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)
            report.pipeline = pipeline
            report.created_by = request.user
            report.save()
            
            # Refresh the workflow tab
            return render(request, "lab/partials/tabs/_workflow.html", {"individual": individual})
    else:
        form = AnalysisReportForm()

    context = {
        "form": form,
        "title": f"Upload Analysis Report for {pipeline.type.name}",
        "action_url": request.path,
    }
    return render(request, "lab/partials/modals/upload_modal_form.html", context)


@login_required
def variant_create_modal(request, pipeline_id):
    """Render a basic SNV variant creation modal or handle submission"""
    from variant.forms import SNVForm
    from lab.models import Pipeline
    
    pipeline = get_object_or_404(Pipeline, pk=pipeline_id)
    individual = pipeline.test.sample.individual
    
    if request.method == "POST":
        form = SNVForm(request.POST) # SNV formulation doesn't expect FILES currently but standard structure
        if form.is_valid():
            variant = form.save(commit=False)
            variant.pipeline = pipeline
            variant.individual = individual
            variant.created_by = request.user
            variant.save()
            
            # Refresh the workflow tab
            return render(request, "lab/partials/tabs/_workflow.html", {"individual": individual})
    else:
        form = SNVForm()

    # We need to manually inject some styling because Variant forms don't inherit BaseForm
    for field_name, field in form.fields.items():
        current_classes = field.widget.attrs.get("class", "")
        if isinstance(field.widget, forms.TextInput) or isinstance(field.widget, forms.NumberInput) or isinstance(field.widget, forms.Select):
            if "select" not in current_classes and "input" not in current_classes:
                # Basic daisyUI mapping
                if isinstance(field.widget, forms.Select):
                    field.widget.attrs["class"] = f"select select-bordered w-full {current_classes}"
                else:
                    field.widget.attrs["class"] = f"input input-bordered w-full {current_classes}"

    context = {
        "form": form,
        "title": f"Add SNV for {pipeline.type.name}",
        "action_url": request.path,
    }
    return render(request, "lab/partials/generic_modal_form.html", context)
