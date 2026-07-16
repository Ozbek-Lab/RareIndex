from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseForbidden, FileResponse, Http404
from django.contrib.auth.decorators import login_required
from django import forms
from django.views.decorators.http import require_POST, require_http_methods
from django.db.models import Q
from django.core.paginator import Paginator
from django.views.generic import View
from django.urls import reverse
from django.apps import apps
from pathlib import Path
from .models import Family, Individual, Project, Task
from .search_utils import filter_normalized_contains


def _get_status_for_model(model, *names):
    from django.contrib.contenttypes.models import ContentType
    from .models import Status

    ct = ContentType.objects.get_for_model(model)
    qs = Status.objects.filter(content_type=ct)
    for name in names:
        status = qs.filter(name__iexact=name).first()
        if status:
            return status
    return qs.first()


def _resolve_workflow_individual(obj):
    if isinstance(obj, Individual):
        return obj

    for path in (
        ("individual",),
        ("sample", "individual"),
        ("test", "sample", "individual"),
        ("pipeline", "test", "sample", "individual"),
        ("analysis", "pipeline", "test", "sample", "individual"),
    ):
        current = obj
        for attr in path:
            current = getattr(current, attr, None)
            if current is None:
                break
        if isinstance(current, Individual):
            return current

    content_object = getattr(obj, "content_object", None)
    if content_object is not None and content_object is not obj:
        return _resolve_workflow_individual(content_object)

    return None


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
    if not request.user.has_perm("lab.change_individual"):
        return HttpResponseForbidden("You do not have permission to edit this individual.")
    from .forms import IndividualIdentificationForm
    from .models import IdentifierType
    can_edit_sensitive = request.user.has_perm("lab.view_sensitive_data")
    form = IndividualIdentificationForm(
        instance=individual,
        can_edit_sensitive=can_edit_sensitive,
    )
    
    # Exclude primary/secondary identifier types from the "other IDs" dropdown
    identifier_types = IdentifierType.objects.exclude(use_priority__in=[1, 2])
    primary_id_type = IdentifierType.objects.filter(use_priority=1).order_by("id").first()
    secondary_id_type = IdentifierType.objects.filter(use_priority=2).order_by("id").first()
    
    context = {
        "individual": individual, 
        "form": form, 
        "edit_mode": True,
        "can_edit_sensitive": can_edit_sensitive,
        "identifier_types": identifier_types,
        "primary_id_type": primary_id_type,
        "secondary_id_type": secondary_id_type,
    }
    return render(request, "lab/partials/tabs/_info.html#identification_content", context)

@login_required
@require_POST
def individual_identification_save(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    if not request.user.has_perm("lab.change_individual"):
        return HttpResponseForbidden("You do not have permission to edit this individual.")
    from .forms import IndividualIdentificationForm
    can_edit_sensitive = request.user.has_perm("lab.view_sensitive_data")
    form = IndividualIdentificationForm(
        request.POST,
        instance=individual,
        can_edit_sensitive=can_edit_sensitive,
    )
    
    if form.is_valid():
        form.save(user=request.user)
        # Render display mode
        context = {"individual": individual, "edit_mode": False}
        return render(request, "lab/partials/tabs/_info.html#identification_content", context)
    
    # Render edit mode with errors
    from .models import IdentifierType
    identifier_types = IdentifierType.objects.exclude(use_priority__in=[1, 2])
    primary_id_type = IdentifierType.objects.filter(use_priority=1).order_by("id").first()
    secondary_id_type = IdentifierType.objects.filter(use_priority=2).order_by("id").first()
    context = {
        "individual": individual,
        "form": form,
        "edit_mode": True,
        "can_edit_sensitive": can_edit_sensitive,
        "identifier_types": identifier_types,
        "primary_id_type": primary_id_type,
        "secondary_id_type": secondary_id_type,
    }
    return render(request, "lab/partials/tabs/_info.html#identification_content", context)

@login_required
def individual_demographics_edit(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    if not request.user.has_perm("lab.change_individual"):
        return HttpResponseForbidden("You do not have permission to edit this individual.")
    from .forms import IndividualDemographicsForm
    can_edit_sensitive = request.user.has_perm("lab.view_sensitive_data")
    form = IndividualDemographicsForm(
        instance=individual,
        can_edit_sensitive=can_edit_sensitive,
    )
    context = {
        "individual": individual,
        "form": form,
        "edit_mode": True,
        "can_edit_sensitive": can_edit_sensitive,
    }
    return render(request, "lab/partials/tabs/_info.html#demographics_content", context)

@login_required
@require_POST
def individual_demographics_save(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    if not request.user.has_perm("lab.change_individual"):
        return HttpResponseForbidden("You do not have permission to edit this individual.")
    from .forms import IndividualDemographicsForm
    can_edit_sensitive = request.user.has_perm("lab.view_sensitive_data")
    form = IndividualDemographicsForm(
        request.POST,
        instance=individual,
        can_edit_sensitive=can_edit_sensitive,
    )
    
    if form.is_valid():
        form.save(user=request.user)
        # Render display mode
        context = {"individual": individual, "edit_mode": False}
        return render(request, "lab/partials/tabs/_info.html#demographics_content", context)
    
    # Render edit mode with errors
    context = {
        "individual": individual,
        "form": form,
        "edit_mode": True,
        "can_edit_sensitive": can_edit_sensitive,
    }
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


def _individual_contact_context(individual, form=None, edit_mode=False):
    import json

    from .models import Contact, Institution

    if form is None and edit_mode:
        from .forms import IndividualContactInformationForm

        form = IndividualContactInformationForm(instance=individual)

    institutions = Institution.objects.prefetch_related("staff").order_by("name")
    contacts = Contact.objects.order_by("full_name")

    return {
        "individual": individual,
        "form": form,
        "edit_mode": edit_mode,
        "institutions_json": json.dumps(
            [
                {
                    "id": str(institution.id),
                    "name": institution.name,
                    "staffIds": [str(contact.id) for contact in institution.staff.all()],
                }
                for institution in institutions
            ]
        ),
        "contacts_json": json.dumps(
            [
                {
                    "id": str(contact.id),
                    "name": contact.full_name,
                }
                for contact in contacts
            ]
        ),
    }


@login_required
def individual_contact_information_display(request, pk):
    individual = get_object_or_404(
        Individual.objects.prefetch_related("institution", "physicians"),
        pk=pk,
    )
    return render(
        request,
        "lab/partials/tabs/_info.html#contact_information_content",
        _individual_contact_context(individual),
    )


@login_required
def individual_contact_information_edit(request, pk):
    individual = get_object_or_404(
        Individual.objects.prefetch_related("institution", "physicians"),
        pk=pk,
    )
    return render(
        request,
        "lab/partials/tabs/_info.html#contact_information_content",
        _individual_contact_context(individual, edit_mode=True),
    )


@login_required
@require_POST
def individual_contact_information_save(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    from .forms import IndividualContactInformationForm

    form = IndividualContactInformationForm(request.POST, instance=individual)
    if form.is_valid():
        form.save()
        individual = get_object_or_404(
            Individual.objects.prefetch_related("institution", "physicians"),
            pk=pk,
        )
        return render(
            request,
            "lab/partials/tabs/_info.html#contact_information_content",
            _individual_contact_context(individual),
        )

    return render(
        request,
        "lab/partials/tabs/_info.html#contact_information_content",
        _individual_contact_context(individual, form=form, edit_mode=True),
    )


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
        families = filter_normalized_contains(families, ["family_id", "description"], query)
    
    # Simple pagination
    paginator = Paginator(families.order_by("-id"), 10)
    page_obj = paginator.get_page(page_number)
    
    context = {"page_obj": page_obj, "query": query}
    return render(request, "lab/partials/family_picker_results.html", context)


@login_required
def individual_parents_edit(request, pk):
    if not request.user.has_perm("lab.change_family"):
        return HttpResponseForbidden("You do not have permission to edit family relationships.")
    member = get_object_or_404(Individual, pk=pk)
    individual_pk = request.GET.get("individual_pk")
    individual = get_object_or_404(Individual, pk=individual_pk) if individual_pk else member
    family_members = member.family.individuals.exclude(pk=pk) if member.family else Individual.objects.none()
    context = {"member": member, "individual": individual, "family_members": family_members, "edit_mode": True}
    return render(request, "lab/partials/family_member_row.html", context)


@login_required
def family_id_edit(request, pk):
    """Render inline edit form, or display mode when cancel=1."""
    from .models import Family
    family = get_object_or_404(Family, pk=pk)
    individual_pk = request.GET.get("individual_pk", "")
    if request.GET.get("cancel"):
        individual = get_object_or_404(Individual, pk=individual_pk) if individual_pk else family.individuals.first()
        return render(request, "lab/partials/family_title_display.html", {
            "family": family,
            "individual": individual,
        })
    return render(request, "lab/partials/family_id_edit.html", {
        "family": family,
        "individual_pk": individual_pk,
    })


@login_required
@require_POST
def family_id_save(request, pk):
    """Save the new family_id and re-render the title row."""
    from .models import Family
    from django.core.exceptions import ValidationError
    family = get_object_or_404(Family, pk=pk)
    if not request.user.has_perm("lab.change_family"):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    individual_pk = request.POST.get("individual_pk", "")
    individual = get_object_or_404(Individual, pk=individual_pk) if individual_pk else None
    new_id = request.POST.get("family_id", "").strip()
    consanguinity_value = request.POST.get("is_consanguineous", "")
    error = None
    if not new_id:
        error = "Family name cannot be empty."
    elif Family.objects.filter(family_id=new_id).exclude(pk=pk).exists():
        error = f'"{new_id}" is already used by another family.'
    if error:
        return render(request, "lab/partials/family_id_edit.html", {
            "family": family,
            "individual_pk": individual_pk,
            "error": error,
            "value": new_id,
            "consanguinity_value": consanguinity_value,
        })
    family.family_id = new_id
    if consanguinity_value == "true":
        family.is_consanguineous = True
    elif consanguinity_value == "false":
        family.is_consanguineous = False
    else:
        family.is_consanguineous = None
    family.save(update_fields=["family_id", "is_consanguineous"])
    # Re-render the title div (display mode)
    ctx = {
        "family": family,
        "individual": individual or (family.individuals.first()),
    }
    return render(request, "lab/partials/family_title_display.html", ctx)


@login_required
def family_manage_members(request, pk):
    """Render the manage-members modal content for a family."""
    from .models import Family
    from .forms import QuickAddMemberForm
    family = get_object_or_404(Family, pk=pk)
    individual_pk = request.GET.get("individual_pk", "")
    form = QuickAddMemberForm()
    members = family.individuals.select_related("family").prefetch_related("statuses").order_by("pk")
    return render(request, "lab/partials/family_manage_members.html", {
        "family": family,
        "members": members,
        "individual_pk": individual_pk,
        "form": form,
    })


@login_required
@require_POST
def family_add_member(request, pk):
    """Create a new individual and assign to the family."""
    from .models import Family
    from .forms import QuickAddMemberForm
    from django.http import HttpResponseForbidden
    family = get_object_or_404(Family, pk=pk)
    if not request.user.has_perm("lab.add_individual"):
        return HttpResponseForbidden()
    individual_pk = request.POST.get("individual_pk", "")
    form = QuickAddMemberForm(request.POST)
    if form.is_valid():
        member = form.save(commit=False)
        member.family = family
        member.created_by = request.user
        member.save()
        # Save statuses
        selected_statuses = form.cleaned_data.get("statuses")
        if selected_statuses:
            member.statuses.set(selected_statuses)
        # Save primary and secondary IDs as CrossIdentifier objects
        from .models import IdentifierType, CrossIdentifier
        def _save_priority_id(priority, value):
            if not value:
                return
            id_type = IdentifierType.objects.filter(use_priority=priority).order_by("id").first()
            if not id_type:
                return
            CrossIdentifier.objects.get_or_create(
                individual=member,
                id_type=id_type,
                defaults={"id_value": value, "created_by": request.user},
            )
        _save_priority_id(1, form.cleaned_data.get("primary_id"))
        _save_priority_id(2, form.cleaned_data.get("secondary_id"))
        form = QuickAddMemberForm()
        members = family.individuals.select_related("family").prefetch_related("statuses").order_by("pk")
        response = render(request, "lab/partials/family_manage_members.html", {
            "family": family,
            "members": members,
            "individual_pk": individual_pk,
            "form": form,
            "success_msg": f"Added {member.primary_id or member.full_name or 'new member'} to the family.",
        })
        response["HX-Trigger"] = "familyUpdated"
        return response
    members = family.individuals.select_related("family").prefetch_related("statuses").order_by("pk")
    return render(request, "lab/partials/family_manage_members.html", {
        "family": family,
        "members": members,
        "individual_pk": individual_pk,
        "form": form,
    })


@login_required
@require_POST
def family_remove_member(request, pk):
    """Remove an individual from their family (set family=None)."""
    from django.http import HttpResponseForbidden
    member = get_object_or_404(Individual, pk=pk)
    if not request.user.has_perm("lab.change_individual"):
        return HttpResponseForbidden()
    member.family = None
    member.save(update_fields=["family"])
    response = HttpResponse("")
    response["HX-Trigger"] = "familyUpdated"
    return response


@login_required
def individual_family_section(request, pk):
    """Return the family section partial for OOB refresh."""
    individual = get_object_or_404(
        Individual.objects.select_related("family", "mother", "father")
        .prefetch_related(
            "cross_ids__id_type",
            "family__individuals",
            "family__individuals__cross_ids__id_type",
            "family__individuals__mother",
            "family__individuals__father",
            "family__individuals__statuses",
        ),
        pk=pk,
    )
    return render(request, "lab/partials/tabs/_family.html", {"individual": individual})


@login_required
@require_POST
def individual_toggle_index(request, pk):
    """Toggle the is_index flag on a family member and re-render the row."""
    member = get_object_or_404(Individual, pk=pk)
    if not request.user.has_perm("lab.change_individual"):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    member.is_index = not member.is_index
    member.save(update_fields=["is_index"])
    individual_pk = request.POST.get("individual_pk")
    individual = get_object_or_404(Individual, pk=individual_pk) if individual_pk else member
    context = {"member": member, "individual": individual, "edit_mode": False}
    return render(request, "lab/partials/family_member_row.html", context)


@login_required
@require_POST
def individual_toggle_affected(request, pk):
    """Toggle the is_affected flag on a family member and re-render the row."""
    member = get_object_or_404(Individual, pk=pk)
    if not request.user.has_perm("lab.change_individual"):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    member.is_affected = not member.is_affected
    member.save(update_fields=["is_affected"])
    individual_pk = request.POST.get("individual_pk")
    individual = get_object_or_404(Individual, pk=individual_pk) if individual_pk else member
    context = {"member": member, "individual": individual, "edit_mode": False}
    return render(request, "lab/partials/family_member_row.html", context)


@login_required
def individual_parents_display(request, pk):
    member = get_object_or_404(Individual, pk=pk)
    individual_pk = request.GET.get("individual_pk")
    individual = get_object_or_404(Individual, pk=individual_pk) if individual_pk else member
    context = {"member": member, "individual": individual, "edit_mode": False}
    return render(request, "lab/partials/family_member_row.html", context)


@login_required
@require_POST
def individual_parents_save(request, pk):
    if not request.user.has_perm("lab.change_family"):
        return HttpResponseForbidden("You do not have permission to edit family relationships.")
    member = get_object_or_404(Individual, pk=pk)
    individual_pk = request.POST.get("individual_pk")
    individual = get_object_or_404(Individual, pk=individual_pk) if individual_pk else member

    father_id = request.POST.get("father_id") or None
    mother_id = request.POST.get("mother_id") or None

    member.father_id = int(father_id) if father_id else None
    member.mother_id = int(mother_id) if mother_id else None
    if request.user.has_perm("lab.change_individual"):
        member.is_index = request.POST.get("is_index") == "1"
        member.is_affected = request.POST.get("is_affected") == "1"
    member.save()
    member.refresh_from_db()

    family_members = member.family.individuals.exclude(pk=pk) if member.family else Individual.objects.none()
    context = {"member": member, "individual": individual, "family_members": family_members, "edit_mode": False}
    return render(request, "lab/partials/family_member_row.html", context)


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
def individual_age_of_onset_months_edit(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    from .forms import AgeOfOnsetMonthsForm
    form = AgeOfOnsetMonthsForm(instance=individual)
    context = {
        "individual": individual,
        "form": form,
        "edit_onset_months": True,
    }
    return render(request, "lab/partials/tabs/_phenotype.html#age_of_onset_months_content", context)


@login_required
@require_POST
def individual_age_of_onset_months_save(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    from .forms import AgeOfOnsetMonthsForm
    form = AgeOfOnsetMonthsForm(request.POST, instance=individual)
    if form.is_valid():
        form.save()
        context = {"individual": individual}
        return render(request, "lab/partials/tabs/_phenotype.html#age_of_onset_months_content", context)

    context = {
        "individual": individual,
        "form": form,
        "edit_onset_months": True,
    }
    return render(request, "lab/partials/tabs/_phenotype.html#age_of_onset_months_content", context)


@login_required
def individual_age_of_onset_months_display(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    context = {"individual": individual}
    return render(request, "lab/partials/tabs/_phenotype.html#age_of_onset_months_content", context)


@login_required
@require_POST
def update_status(request, content_type_id, object_id, status_id):
    """
    Toggle a status tag on an object. Adds if not present, removes if already tagged.
    """
    from django.contrib.contenttypes.models import ContentType
    from .models import Status

    ct = get_object_or_404(ContentType, pk=content_type_id)
    Model = ct.model_class()
    obj = get_object_or_404(Model, pk=object_id)
    toggle_status = get_object_or_404(Status, pk=status_id)

    change_perms = [f"{ct.app_label}.change_{ct.model}"]
    if ct.app_label == "variant" and ct.model == "variant":
        change_perms.append("variant.change_annotation")
    if not any(request.user.has_perm(perm) for perm in change_perms):
        return HttpResponseForbidden("You do not have permission to change this status.")

    # Toggle: remove if already present, add if not
    if obj.statuses.filter(pk=toggle_status.pk).exists():
        obj.statuses.remove(toggle_status)
    else:
        # If this status belongs to an exclusive group, remove all other
        # statuses in that group before adding the new one.
        if toggle_status.group:
            from .models import Status as StatusModel
            group_siblings = StatusModel.objects.filter(
                group=toggle_status.group
            ).exclude(pk=toggle_status.pk)
            for sibling in group_siblings:
                obj.statuses.remove(sibling)
        obj.statuses.add(toggle_status)

    individual = _resolve_workflow_individual(obj)
    context = {
        ct.model: obj,
        "individual": individual,
    }

    if ct.app_label == "variant" and ct.model == "variant":
        response = render(request, "lab/partials/variant_detail.html#variant_status_controls", context)

        from lab.tables import _render_status_badges
        from django.utils.html import format_html
        badges_html = _render_status_badges(list(obj.statuses.all()))
        response.content += format_html(
            '<span id="variant-row-status-{}" hx-swap-oob="true">{}</span>',
            obj.pk,
            badges_html,
        ).encode("utf-8")
    else:
        partial_name = f"{ct.model}_status_badge"
        response = render(request, f"lab/partials/tabs/_workflow.html#{partial_name}", context)

    # If we can resolve the owning Individual, also send an OOB swap for the
    # table row badge so connected statuses stay in sync.
    if individual:
        from lab.tables import _render_status_badges
        from .status_utils import collect_individual_row_statuses
        from django.utils.html import format_html
        badges_html = _render_status_badges(collect_individual_row_statuses(individual))
        oob_html = format_html(
            '<span id="individual-row-status-{}" hx-swap-oob="true">{}</span>',
            individual.pk,
            badges_html,
        )
        response.content += oob_html.encode("utf-8")

    return response

def _workflow_sample_status_options(form):
    if form.is_bound:
        selected_ids = set(form.data.getlist(form.add_prefix("statuses")))
    else:
        initial_statuses = form.initial.get("statuses") or []
        selected_ids = {str(getattr(status, "pk", status)) for status in initial_statuses}

    options = []
    for status in form.fields["statuses"].queryset:
        options.append(
            {
                "id": str(status.pk),
                "status": status,
                "group_name": status.group.name if status.group_id else "",
                "selected": str(status.pk) in selected_ids,
            }
        )
    return options


@login_required
def sample_create_modal(request, individual_id):
    """Render the workflow sample creation modal or handle submission."""
    import json

    from .forms import WorkflowSampleCreateForm
    from .models import Individual, Note, Sample

    if not request.user.has_perm("lab.add_sample"):
        return HttpResponseForbidden("You do not have permission to add samples.")

    individual = get_object_or_404(Individual, pk=individual_id)

    if request.method == "POST":
        form = WorkflowSampleCreateForm(request.POST, individual=individual)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.individual = individual
            sample.created_by = request.user
            sample.save()

            selected_statuses = form.cleaned_data.get("statuses")
            if selected_statuses:
                sample.statuses.set(selected_statuses)
            elif not sample.statuses.exists():
                default_status = _get_status_for_model(
                    Sample,
                    "Available" if sample.receipt_date else "Planned",
                    "Not Available",
                )
                if default_status:
                    sample.statuses.add(default_status)

            note_content = form.cleaned_data.get("note_content", "").strip()
            if note_content:
                Note.objects.create(
                    content=note_content,
                    user=request.user,
                    content_object=sample,
                )

            response = HttpResponse(status=204)
            response["HX-Trigger"] = json.dumps(
                {
                    "workflowRefreshed": True,
                    "closeModal": True,
                    "close-modal": True,
                }
            )
            return response
    else:
        initial = {}
        status = _get_status_for_model(Sample, "Planned", "Available", "Not Available")
        if status:
            initial["statuses"] = [status.pk]

        form = WorkflowSampleCreateForm(initial=initial, individual=individual)

    context = {
        "form": form,
        "individual": individual,
        "action_url": request.path,
        "status_options": _workflow_sample_status_options(form),
    }
    return render(request, "lab/partials/modals/sample_create_modal.html", context)


@login_required
def test_create_modal(request, sample_id):
    """Render a test creation form or handle submission"""
    from .forms import TestForm
    from .models import Sample, Test
    from django.template.loader import render_to_string

    if not request.user.has_perm("lab.add_test"):
        return HttpResponseForbidden("You do not have permission to add tests.")
    
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
            test.save()
            selected_statuses = form.cleaned_data.get("statuses")
            if selected_statuses:
                test.statuses.set(selected_statuses)
            elif not test.statuses.exists():
                default_status = _get_status_for_model(
                    Test,
                    "Waiting Data/Bioinformatic process",
                    "Planned",
                    "Data Delivered / Completed",
                )
                if default_status:
                    test.statuses.add(default_status)

            sample = (
                Sample.objects.select_related("individual", "sample_type")
                .prefetch_related(
                    "statuses",
                    "tasks",
                    "notes",
                    "tests",
                    "tests__statuses",
                    "tests__tasks",
                    "tests__notes",
                    "tests__pipelines",
                    "tests__pipelines__statuses",
                    "tests__pipelines__tasks",
                    "tests__pipelines__notes",
                    "tests__pipelines__analyses",
                    "tests__pipelines__analyses__statuses",
                    "tests__pipelines__analyses__tasks",
                    "tests__pipelines__analyses__notes",
                    "tests__pipelines__analyses__reports",
                    "tests__pipelines__analyses__found_variants",
                )
                .get(pk=sample.pk)
            )
            individual = sample.individual
            sample_html = render_to_string(
                "lab/partials/tabs/_workflow.html#sample_card",
                {"individual": individual, "sample": sample},
                request=request,
            )
            sample_html = sample_html.replace(
                f'id="sample-card-{sample.id}"',
                f'id="sample-card-{sample.id}" hx-swap-oob="outerHTML"',
                1,
            )
            response = HttpResponse(sample_html)
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = '{"closeModal": true, "close-modal": true}'
            return response
    else:
        initial = {"sample": sample}
        status = _get_status_for_model(Test, "Planned", "Waiting Data/Bioinformatic process", "Data Delivered / Completed")
        if status:
            initial["statuses"] = [status]
            
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
        "close_on_success": True,
    }
    return render(request, "lab/partials/generic_modal_form.html", context)


@login_required
def pipeline_create_modal(request, test_id):
    """Render a pipeline creation form or handle submission"""
    from .forms import PipelineForm
    from .models import Pipeline, Test
    from django.template.loader import render_to_string

    if not request.user.has_perm("lab.add_pipeline"):
        return HttpResponseForbidden("You do not have permission to add pipelines.")
    
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
            pipeline.save()
            selected_statuses = form.cleaned_data.get("statuses")
            if selected_statuses:
                pipeline.statuses.set(selected_statuses)
            elif not pipeline.statuses.exists():
                default_status = _get_status_for_model(
                    Pipeline,
                    "Planned",
                    "Waiting Data/Bioinformatic process",
                    "Bioinformatic process completed",
                )
                if default_status:
                    pipeline.statuses.add(default_status)

            test = (
                Test.objects.select_related("sample__individual", "test_type")
                .prefetch_related(
                    "statuses",
                    "tasks",
                    "notes",
                    "pipelines",
                    "pipelines__statuses",
                    "pipelines__tasks",
                    "pipelines__notes",
                    "pipelines__analyses",
                    "pipelines__analyses__statuses",
                    "pipelines__analyses__tasks",
                    "pipelines__analyses__notes",
                    "pipelines__analyses__reports",
                    "pipelines__analyses__found_variants",
                )
                .get(pk=test.pk)
            )
            individual = test.sample.individual
            test_html = render_to_string(
                "lab/partials/tabs/_workflow.html#test_card",
                {"individual": individual, "test": test},
                request=request,
            )
            test_html = test_html.replace(
                f'id="test-card-{test.id}"',
                f'id="test-card-{test.id}" hx-swap-oob="outerHTML"',
                1,
            )
            response = HttpResponse(test_html)
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = '{"closeModal": true, "close-modal": true}'
            return response
    else:
        initial = {"test": test}
        status = _get_status_for_model(Pipeline, "Planned", "Waiting Data/Bioinformatic process", "Bioinformatic process completed")
        if status:
            initial["statuses"] = [status]
            
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
        "close_on_success": True,
    }
    return render(request, "lab/partials/generic_modal_form.html", context)


@login_required
def analysis_create_modal(request, pipeline_id):
    """Render an analysis creation form or handle submission"""
    from .forms import AnalysisForm
    from .models import Analysis, Pipeline
    from django.template.loader import render_to_string

    if not request.user.has_perm("lab.add_analysis"):
        return HttpResponseForbidden("You do not have permission to add analyses.")
    
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
            analysis.save()
            selected_statuses = form.cleaned_data.get("statuses")
            if selected_statuses:
                analysis.statuses.set(selected_statuses)
            elif not analysis.statuses.exists():
                default_status = _get_status_for_model(
                    Analysis,
                    "Planned",
                    "Waiting Confirmation",
                    "Completed",
                )
                if default_status:
                    analysis.statuses.add(default_status)

            pipeline = (
                Pipeline.objects.select_related("test__sample__individual", "type")
                .prefetch_related(
                    "statuses",
                    "tasks",
                    "notes",
                    "analyses",
                    "analyses__statuses",
                    "analyses__tasks",
                    "analyses__notes",
                    "analyses__reports",
                    "analyses__found_variants",
                )
                .get(pk=pipeline.pk)
            )
            individual = pipeline.test.sample.individual
            pipeline_html = render_to_string(
                "lab/partials/tabs/_workflow.html#pipeline_card",
                {"individual": individual, "pipeline": pipeline},
                request=request,
            )
            pipeline_html = pipeline_html.replace(
                f'id="pipeline-card-{pipeline.id}"',
                f'id="pipeline-card-{pipeline.id}" hx-swap-oob="outerHTML"',
                1,
            )
            response = HttpResponse(pipeline_html)
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = '{"closeModal": true, "close-modal": true}'
            return response
    else:
        initial = {"pipeline": pipeline}
        status = _get_status_for_model(Analysis, "Planned", "Waiting Confirmation", "Completed")
        if status:
            initial["statuses"] = [status]
            
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
        "close_on_success": True,
    }
    return render(request, "lab/partials/generic_modal_form.html", context)
@login_required
def task_create_modal(request, content_type_id, object_id):
    """Render a task creation form or handle submission"""
    from .forms import TaskForm
    from .models import Status, Individual, Sample, Test, Pipeline, Project, Analysis
    from django.contrib.contenttypes.models import ContentType
    from django.template.loader import render_to_string
    from variant.models import Variant
    
    ct = get_object_or_404(ContentType, pk=content_type_id)
    Model = ct.model_class()
    obj = get_object_or_404(Model, pk=object_id)
    
    
    # Determine target ID and partial name
    target_id = "#workflow-content" # fallback
    partial_name = ""
    count_id = ""
    submit_target = "#generic-modal-content"
    partial_template = "lab/partials/tabs/_workflow.html"
    
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
        target_id = f"#pipeline-tasks-{obj.id}"
        partial_name = "pipeline_tasks"
        count_id = f"task-count-pipeline-{obj.id}"
        individual = obj.test.sample.individual
    elif isinstance(obj, Project):
        target_id = f"#project-tasks-{obj.id}"
        # Tasks created directly on a Project are fixed to that project
        # (individual is not strictly needed here)
        individual = None
    elif isinstance(obj, Analysis):
        target_id = f"#analysis-tasks-{obj.id}"
        partial_name = "analysis_tasks"
        count_id = f"task-count-analysis-{obj.id}"
        individual = obj.pipeline.test.sample.individual if obj.pipeline and obj.pipeline.test and obj.pipeline.test.sample else None
    elif isinstance(obj, Variant):
        target_id = f"#variant-tasks-{obj.id}"
        partial_name = "variant_tasks"
        count_id = f"task-count-variant-{obj.id}"
        partial_template = "lab/partials/variant_detail.html"
        individual = obj.individual

    if request.method == "POST":
        form = TaskForm(
            request.POST,
            content_object=obj,
            individual=individual,
            project=obj if isinstance(obj, Project) else None,
        )
        if form.is_valid():
            task = form.save(commit=False)
            task.content_type = ct
            task.object_id = object_id
            task.created_by = request.user
            if isinstance(obj, Project):
                task.project = obj
            task.save()
            selected_statuses = form.cleaned_data.get("statuses")
            if selected_statuses:
                task.statuses.set(selected_statuses)
            elif not task.statuses.exists():
                default_status = _get_status_for_model(Task, "Assigned", "Active", "Completed")
                if default_status:
                    task.statuses.add(default_status)
            success_html = render_to_string(
                "lab/partials/modals/task_created_success.html",
                {
                    "task": task,
                    "project": obj if isinstance(obj, Project) else task.project,
                },
                request=request,
            )

            if isinstance(obj, Project):
                tasks_qs = (
                    obj.tasks
                    .exclude(statuses__name__iexact="Completed")
                    .select_related("assigned_to")
                    .prefetch_related("statuses")
                    .order_by("-id")
                    .distinct()
                )
                page_obj = Paginator(tasks_qs, 5).get_page(1)
                tasks_html = render_to_string(
                    "lab/partials/project_tasks_partial.html",
                    {"project": obj, "tasks_page": page_obj},
                    request=request,
                )
                oob_tasks = (
                    f'<div id="{target_id.lstrip("#")}" hx-swap-oob="innerHTML">'
                    f"{tasks_html}</div>"
                )
                return HttpResponse(success_html + oob_tasks)

            context = {
                "individual": individual,
                "sample": obj if isinstance(obj, Sample) else None,
                "test": obj if isinstance(obj, Test) else None,
                "pipeline": obj if isinstance(obj, Pipeline) else None,
                "analysis": obj if isinstance(obj, Analysis) else None,
                "variant": obj if isinstance(obj, Variant) else None,
            }
            partial_html = render_to_string(
                f"{partial_template}#{partial_name}",
                context,
                request=request,
            )
            count = obj.tasks.count()
            oob_target = target_id.lstrip("#")
            if isinstance(obj, Variant):
                count_html = (
                    f'<span id="{count_id}" hx-swap-oob="true" '
                    f'class="badge badge-xs badge-ghost ml-1">{count}</span>'
                )
            else:
                count_html = f'''
                <div id="{count_id}" hx-swap-oob="true" 
                     class="flex items-center gap-1.5 tooltip tooltip-bottom" 
                     data-tip="{count} Tasks">
                    <i class="fa-solid fa-list-check"></i> {count}
                </div>
                '''
            oob_html = f'''
            {count_html}
            <div id="{oob_target}" hx-swap-oob="innerHTML">
                {partial_html}
            </div>
            '''
            return HttpResponse(success_html + oob_html)

    else:
        initial = {"content_type": ct.pk, "object_id": object_id}
        default_status = _get_status_for_model(Task, "Assigned", "Active", "Completed")
        if default_status:
            initial["statuses"] = [default_status]
        form = TaskForm(
            initial=initial,
            content_object=obj,
            individual=individual,
            project=obj if isinstance(obj, Project) else None,
        )
        # Hide generic fields
        form.fields["content_type"].widget = forms.HiddenInput()
        form.fields["object_id"].widget = forms.HiddenInput()

    # Make associated type & object visible, descriptive, and non-interactable
    from django import forms as dj_forms
    form.fields["content_type"].disabled = True
    form.fields["content_type"].label = "Associated Type"
    # Display the human-readable model name instead of the ContentType ID
    form.initial["content_type"] = Model._meta.verbose_name.title()
    form.fields["content_type"].widget = dj_forms.TextInput(
        attrs={
            "class": "input input-bordered w-full pointer-events-none bg-base-200/60",
            "readonly": True,
        }
    )

    form.fields["object_id"].disabled = True
    form.fields["object_id"].label = "Associated Object"
    # Display the object's __str__ representation instead of its numeric ID
    form.initial["object_id"] = str(obj)
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
        "hx_target": submit_target,
        "submit_label": "Create Task",
    }
    response = render(request, "lab/partials/generic_modal_form.html", context)
    if request.method == "POST":
        response.headers["HX-Retarget"] = submit_target
        response.headers["HX-Reswap"] = "innerHTML"
    return response


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
    query = request.GET.get("q", "")
    projects = Project.objects.all()
    if query:
        projects = filter_normalized_contains(projects, ["name"], query)
    return render(request, "lab/partials/project_picker_results.html", {"projects": projects[:10]})


@login_required
def project_individual_search(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not request.user.has_perm("lab.change_project"):
        return HttpResponseForbidden("You do not have permission to change projects.")
    query = (request.GET.get("search") or request.GET.get("q") or "").strip()
    individuals = Individual.objects.none()
    if query:
        individuals = filter_normalized_contains(
            Individual.objects.prefetch_related("cross_ids__id_type", "statuses"),
            ["cross_ids__id_value", "cross_ids__id_type__name"],
            query,
        ).distinct()[:15]
    already_in_project = set(project.individuals.values_list("pk", flat=True))
    return render(request, "lab/partials/project_individual_search_results.html", {
        "individuals": individuals,
        "project": project,
        "already_in_project": already_in_project,
        "query": query,
    })


def _project_individuals_page_context(request, project, per_page: int = 25):
    """Build paginated context for the project individuals table."""
    from django.db.models import Q, Min

    individuals_qs = (
        project.individuals.all()
        .prefetch_related("statuses", "institution", "cross_ids__id_type")
    ).annotate(first_institution_name=Min("institution__name"))

    search = request.GET.get("search", "").strip()
    if search:
        individuals_qs = filter_normalized_contains(
            individuals_qs,
            ["cross_ids__id_value", "institution__name"],
            search,
        ).distinct()

    sort = request.GET.get("sort") or "added"
    direction = request.GET.get("dir") or "desc"
    sort_map = {
        "primary": "id",
        "secondary": "id",
        "status": "id",  # status is now M2M tags, sort by id as fallback
        "institution": "first_institution_name",
        "sex": "sex",
        "added": "created_at",
    }
    sort_field = sort_map.get(sort, "created_at")
    if direction == "desc":
        sort_field = f"-{sort_field}"
    individuals_qs = individuals_qs.order_by(sort_field, "id")
    paginator = Paginator(individuals_qs, per_page)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)
    return {
        "project": project,
        "individual_page": page_obj,
        "project_individuals_search": search,
        "project_individuals_sort": sort,
        "project_individuals_dir": direction,
    }


@login_required
def project_individuals_page(request, pk):
    """Return only the next chunk of project-individual rows for infinite scroll."""
    project = get_object_or_404(Project, pk=pk)
    context = _project_individuals_page_context(request, project)
    # Only return table rows; outer template wraps them in <tbody>.
    return render(request, "lab/partials/project_individual_rows.html", context)


@login_required
def task_detail_edit(request, pk):
    """Return the edit form partial for a task's details."""
    from .forms import TaskEditForm
    task = get_object_or_404(Task, pk=pk)
    form = TaskEditForm(instance=task)
    return render(request, "lab/task_detail.html#task_details", {
        "task": task,
        "form": form,
        "edit_mode": True,
    })


@login_required
@require_POST
def task_detail_save(request, pk):
    """Save edited task details and return the display partial."""
    from .forms import TaskEditForm
    task = get_object_or_404(Task, pk=pk)
    form = TaskEditForm(request.POST, instance=task)
    if form.is_valid():
        task = form.save()
        selected_statuses = form.cleaned_data.get("statuses")
        if selected_statuses is not None:
            task.statuses.set(selected_statuses)
        task.refresh_from_db()
        return render(request, "lab/task_detail.html#task_details", {
            "task": task,
            "edit_mode": False,
        })
    return render(request, "lab/task_detail.html#task_details", {
        "task": task,
        "form": form,
        "edit_mode": True,
    })


@login_required
def project_tasks_page(request, pk):
    """Return a paginated tasks partial for the project dropdown."""
    from .models import Task
    from django.core.paginator import Paginator

    project = get_object_or_404(Project, pk=pk)
    per_page = 5
    tasks_qs = (
        project.tasks
        .exclude(statuses__name__iexact="Completed")
        .select_related("assigned_to")
        .prefetch_related("statuses")
        .order_by("-id")
        .distinct()
    )
    paginator = Paginator(tasks_qs, per_page)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "lab/partials/project_tasks_partial.html", {
        "project": project,
        "tasks_page": page_obj,
    })


@login_required
@require_POST
def project_individual_add(request, project_pk, individual_pk):
    if not request.user.has_perm("lab.change_project"):
        return HttpResponseForbidden("You do not have permission to change projects.")
    project = get_object_or_404(Project, pk=project_pk)
    individual = get_object_or_404(Individual, pk=individual_pk)
    project.individuals.add(individual)
    project.refresh_from_db()
    project = (
        Project.objects
        .prefetch_related(
            "individuals__cross_ids__id_type",
            "individuals__statuses",
            "individuals__institution",
        )
        .get(pk=project_pk)
    )
    context = _project_individuals_page_context(request, project)
    return render(request, "lab/partials/tabs/_project_individuals.html", context)


@login_required
def project_individual_remove(request, project_pk, individual_pk):
    if request.method not in ("DELETE", "POST"):
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["DELETE", "POST"])
    if not request.user.has_perm("lab.change_project"):
        return HttpResponseForbidden("You do not have permission to change projects.")
    project = get_object_or_404(Project, pk=project_pk)
    individual = get_object_or_404(Individual, pk=individual_pk)
    project.individuals.remove(individual)
    project.refresh_from_db()
    project = (
        Project.objects
        .prefetch_related(
            "individuals__cross_ids__id_type",
            "individuals__statuses",
            "individuals__institution",
        )
        .get(pk=project_pk)
    )
    context = _project_individuals_page_context(request, project)
    return render(request, "lab/partials/tabs/_project_individuals.html", context)


def _user_can_access_document(request_user, obj):
    model_name = obj._meta.model_name
    return (
        request_user.is_staff
        or request_user.has_perm(f"lab.view_{model_name}")
        or request_user.has_perm(f"lab.change_{model_name}")
    )


def _get_downloadable_document_file(request_user, obj):
    if not request_user.has_perm("lab.view_sensitive_data"):
        raise PermissionError("Document download requires sensitive-data permission.")
    if not obj.file:
        raise Http404("Original file not found.")
    return obj.file


@login_required
def document_preview(request, model_name, pk):
    """Render a document preview in the side drawer."""
    from django.apps import apps
    try:
        Model = apps.get_model("lab", model_name)
        obj = get_object_or_404(Model, pk=pk)
    except (LookupError, ValueError):
        return HttpResponse("Invalid model or object.")

    if not _user_can_access_document(request.user, obj):
        return HttpResponseForbidden("You do not have permission to view this document.")

    context = {
        "object": obj,
        "model_name": model_name,
    }
    response = render(request, "lab/partials/preview_drawer.html", context)
    response["HX-Trigger"] = "open-preview"
    return response


@login_required
def document_download(request, model_name, pk):
    try:
        Model = apps.get_model("lab", model_name)
        obj = get_object_or_404(Model, pk=pk)
    except (LookupError, ValueError):
        return HttpResponse("Invalid model or object.")

    if not _user_can_access_document(request.user, obj):
        return HttpResponseForbidden("You do not have permission to download this document.")

    try:
        selected_file = _get_downloadable_document_file(request.user, obj)
    except PermissionError as exc:
        return HttpResponseForbidden(str(exc))

    filename = Path(selected_file.name).name or f"{obj._meta.model_name}-{obj.pk}"
    return FileResponse(selected_file.open("rb"), as_attachment=True, filename=filename)


@login_required
def project_create_modal(request):
    """Render a project creation form or handle submission.

    Includes a QoL option to copy individuals from existing projects into the
    newly created project.
    """
    from .forms import ProjectCreateWithCopyForm

    if request.method == "POST":
        form = ProjectCreateWithCopyForm(request.POST)
        if form.is_valid():
            # BaseForm.save handles created_by when possible
            project = form.save()

            copy_from = form.cleaned_data.get("copy_from_projects")
            if copy_from:
                individual_ids = (
                    Individual.objects.filter(projects__in=copy_from)
                    .values_list("id", flat=True)
                    .distinct()
                )
                if individual_ids:
                    project.individuals.add(*individual_ids)

            # Ask HTMX to refresh the page so the project list updates.
            response = HttpResponse(status=204)
            response["HX-Refresh"] = "true"
            return response
    else:
        form = ProjectCreateWithCopyForm()

    context = {
        "form": form,
        "title": "Add Project",
        "action_url": request.path,
        "hx_target": "#project-table-container",
        "close_on_success": True,
    }
    return render(request, "lab/partials/generic_modal_form.html", context)


@login_required
def project_delete_modal(request, pk):
    """Confirm and delete a project from the project detail page."""
    project = get_object_or_404(Project, pk=pk)

    if not request.user.has_perm("lab.delete_project"):
        return HttpResponseForbidden("You do not have permission to delete projects.")

    if request.method == "POST":
        project.delete()
        response = HttpResponse(status=204)
        # After deletion, send user back to the project list.
        response["HX-Redirect"] = reverse("lab:project_list")
        return response

    context = {
        "project": project,
        "action_url": request.path,
    }
    return render(request, "lab/partials/modals/project_delete_confirm.html", context)


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
def report_create_modal(request, analysis_id):
    """Render an analysis report creation modal or handle submission"""
    from .forms import AnalysisReportForm
    from .models import Analysis
    
    analysis = get_object_or_404(Analysis, pk=analysis_id)
    individual = analysis.pipeline.test.sample.individual
    workflow_target_id = f"#workflow-content-{individual.pk}"
    
    if request.method == "POST":
        form = AnalysisReportForm(request.POST, request.FILES, analysis=analysis)
        if form.is_valid():
            report = form.save(commit=False)
            report.analysis = analysis
            report.created_by = request.user
            report.save()
            form.save_m2m()
            
            # Refresh the workflow tab
            return render(
                request,
                "lab/partials/tabs/_workflow.html",
                {"individual": individual, "workflow_target_id": workflow_target_id},
            )
    else:
        form = AnalysisReportForm(analysis=analysis)

    title = f"Upload Analysis Report for {analysis.type.name}" if analysis.type else "Upload Analysis Report"
    context = {
        "form": form,
        "title": title,
        "action_url": request.path,
        "workflow_target_id": workflow_target_id,
    }
    return render(request, "lab/partials/modals/upload_modal_form.html", context)


@login_required
def generate_analysis_report_docx(request, analysis_id):
    from django.core.files.base import ContentFile
    from django.http import HttpResponseBadRequest
    from django.shortcuts import get_object_or_404, render
    from django.utils import timezone

    from variant.models import Variant

    from .models import Analysis, AnalysisReport
    from .docx_reports import (
        build_docx_report_bytes,
        choose_docx_template_for_test_type,
        resolve_docx_template_path,
    )
    from .forms import AnalysisReportGenerateForm

    analysis = get_object_or_404(
        Analysis.objects.select_related("pipeline__test__sample__individual", "pipeline__test__test_type"),
        pk=analysis_id,
    )
    if not analysis.pipeline_id or not analysis.pipeline.test_id or not analysis.pipeline.test.sample_id:
        return HttpResponseBadRequest("Analysis is missing pipeline/test/sample linkage.")

    individual = analysis.pipeline.test.sample.individual
    workflow_target_id = f"#workflow-content-{individual.pk}" if individual else "#workflow-content"
    variant_ids = request.GET.getlist("variant_ids") if request.method == "GET" else request.POST.getlist("variant_ids")
    report_mode = (
        request.GET.get("report_mode", "positive")
        if request.method == "GET"
        else request.POST.get("report_mode", "positive")
    )
    if report_mode not in {"positive", "negative"}:
        return HttpResponseBadRequest("Invalid report mode.")

    test_type = analysis.pipeline.test.test_type
    if request.method == "GET":
        form = AnalysisReportGenerateForm(test_type=test_type, report_mode=report_mode)
        context = {
            "form": form,
            "action_url": request.path,
            "analysis": analysis,
            "individual": individual,
            "workflow_target_id": workflow_target_id,
            "variant_ids": variant_ids,
            "selected_count": len(variant_ids),
            "report_mode": report_mode,
        }
        return render(request, "lab/partials/modals/report_generate_modal.html", context)

    form = AnalysisReportGenerateForm(request.POST, test_type=test_type, report_mode=report_mode)
    if not form.is_valid():
        context = {
            "form": form,
            "action_url": request.path,
            "analysis": analysis,
            "individual": individual,
            "workflow_target_id": workflow_target_id,
            "variant_ids": variant_ids,
            "selected_count": len(variant_ids),
            "report_mode": report_mode,
        }
        return render(request, "lab/partials/modals/report_generate_modal.html", context)

    selected_qs = Variant.objects.filter(individual=individual)
    if variant_ids:
        selected_qs = selected_qs.filter(id__in=variant_ids)

    # Ensure only unreported variants are picked (avoid duplicates across reports for same analysis)
    selected_qs = selected_qs.exclude(reports__analysis=analysis).distinct()

    negative = report_mode == "negative"
    test_type_name = getattr(test_type, "name", None)
    configured_template = form.cleaned_data.get("template_location", "") or ""
    configured_template_path = resolve_docx_template_path(configured_template)
    if configured_template_path:
        template_choice = type(
            "TemplateChoice",
            (),
            {"path": configured_template_path, "reason": f"configured on TestType: {configured_template}"},
        )()
    else:
        template_choice = choose_docx_template_for_test_type(test_type_name, negative=negative)
    report_date = form.cleaned_data["report_date"]
    default_method_text = form.cleaned_data.get("default_method_text", "") or ""
    default_total_reads_text = form.cleaned_data.get("default_total_reads_text", "") or ""
    default_coverage_20x_text = form.cleaned_data.get("default_coverage_20x_text", "") or ""
    default_mean_depth_text = form.cleaned_data.get("default_mean_depth_text", "") or ""
    default_filtering_text = form.cleaned_data.get("default_filtering_text", "") or ""
    default_limitations_text = form.cleaned_data.get("default_limitations_text", "") or ""
    default_positive_comment_text = form.cleaned_data.get("default_positive_comment_text", "") or ""
    default_negative_result_text = form.cleaned_data.get("default_negative_result_text", "") or ""
    signers = list(form.cleaned_data.get("signers") or [])
    authorized_signer = form.cleaned_data.get("authorized_signer")

    referring_physicians = ", ".join(
        [
            getattr(physician, "full_name", None)
            or str(physician)
            for physician in individual.physicians.all()
        ]
    )
    referring_clinic = ", ".join(individual.institution.values_list("name", flat=True))
    hpo_terms = ", ".join(
        [getattr(term, "descriptive_term", str(term)) for term in individual.hpo_terms.all()]
    )
    signer_blocks = []
    for signer in signers:
        if hasattr(signer, "profile") and signer.profile.signer_block_text:
            signer_blocks.append(
                [
                    line.strip()
                    for line in signer.profile.signer_block_text.splitlines()
                    if line.strip()
                ]
            )

    signer_1_entries = [signer_blocks[0]] if len(signer_blocks) >= 1 else []
    signer_2_entries = [signer_blocks[1]] if len(signer_blocks) >= 2 else []
    signer_3_entries = [signer_blocks[2]] if len(signer_blocks) >= 3 else []

    signer_1_block = "\n\n".join("\n".join(lines) for lines in signer_1_entries)
    signer_2_block = "\n\n".join("\n".join(lines) for lines in signer_2_entries)
    signer_3_block = "\n\n".join("\n".join(lines) for lines in signer_3_entries)

    authorized_signer_lines = []
    if authorized_signer and hasattr(authorized_signer, "profile"):
        authorized_signer_lines = [
            line.strip()
            for line in (authorized_signer.profile.signer_block_text or "").splitlines()
            if line.strip()
        ]

    while len(authorized_signer_lines) < 4:
        authorized_signer_lines.append("")

    report_zygosity_labels = {
        "het": "Heterozigot",
        "hom": "Homozigot",
        "hemi": "Hemizigot",
        "hetpl": "Heteroplazmi",
    }

    rows = [
        {
            "location": str(v),
            "zygosity": report_zygosity_labels.get(v.zygosity, v.get_zygosity_display()),
            "type": v.type,
            "genes": ", ".join([str(g) for g in v.genes.all()]),
        }
        for v in selected_qs
    ]

    first_variant = rows[0] if rows else None
    first_variant_model = selected_qs.first()
    latest_classification = (
        first_variant_model.classifications.order_by("-created_at").first()
        if first_variant_model and hasattr(first_variant_model, "classifications")
        else None
    )

    report_sex = {
        "male": "Erkek",
        "female": "Kadın",
    }.get(individual.sex, individual.get_sex_display() if individual.sex else "")

    placeholders = {
        "REPORT_DATE": report_date.strftime("%d.%m.%Y"),
        "PATIENT_NAME": individual.full_name or "",
        "PATIENT_DOB": individual.birth_date.strftime("%d.%m.%Y") if individual.birth_date else "",
        "PATIENT_SEX": report_sex,
        "REFERRING_CLINIC": referring_clinic,
        "REFERRING_PHYSICIAN": referring_physicians,
        "TEST_INDICATION": individual.diagnosis or "",
        "IBG_BIOBANK_NO": individual.secondary_id or "",
        "RB_BIOBANK_NO": individual.primary_id or "",
        "HPO_TERMS": hpo_terms,
        "RESULT_ROW_NUMBER": "1" if first_variant else "",
        "GENE_TRANSCRIPT_BLOCK": ", ".join(first_variant_model.genes.values_list("symbol", flat=True)) if first_variant_model else "",
        "VARIANT_DETAILS_BLOCK": first_variant["location"] if first_variant else "",
        "ZYGOSITY": first_variant["zygosity"] if first_variant else "",
        "CLASSIFICATION_BLOCK": latest_classification.get_classification_display() if latest_classification else "",
        "OMIM_BLOCK": "",
        "INTERPRETATION_TEXT": "",
        "VARIANT_INTERPRETATION": "",
        "PHENOTYPE_CORRELATION": "",
        "SIGNER_1_BLOCK": signer_1_block,
        "SIGNER_2_BLOCK": signer_2_block,
        "SIGNER_3_BLOCK": signer_3_block,
        "SIGNER_3_NAME": authorized_signer_lines[0],
        "SIGNER_3_AFFILIATION": authorized_signer_lines[1],
        "SIGNER_3_TITLE": authorized_signer_lines[2],
        "SIGNER_3_ROLE": authorized_signer_lines[3],
        "AUTHORIZED_SIGNER_BLOCK": "\n".join([line for line in authorized_signer_lines if line]),
        "METHOD_SUMMARY": default_method_text,
        "TOTAL_READS": default_total_reads_text,
        "COVERAGE_20X": default_coverage_20x_text,
        "MEAN_DEPTH": default_mean_depth_text,
        "FILTERING_SUMMARY": default_filtering_text,
        "LIMITATIONS": default_limitations_text,
        "DEFAULT_METHOD_TEXT": default_method_text,
        "DEFAULT_TOTAL_READS_TEXT": default_total_reads_text,
        "DEFAULT_COVERAGE_20X_TEXT": default_coverage_20x_text,
        "DEFAULT_MEAN_DEPTH_TEXT": default_mean_depth_text,
        "DEFAULT_FILTERING_TEXT": default_filtering_text,
        "DEFAULT_LIMITATIONS_TEXT": default_limitations_text,
        "DEFAULT_POSITIVE_COMMENT_TEXT": "",
        "DEFAULT_NEGATIVE_RESULT_TEXT": "",
        "POSITIVE_COMMENT_TEXT": "",
        "NEGATIVE_RESULT_TEXT": "",
    }

    def expand_report_text(template_text: str) -> str:
        expanded = template_text or ""
        for key, value in placeholders.items():
            expanded = expanded.replace(f"{{{{{key}}}}}", value or "")
        return expanded

    default_method_text = expand_report_text(default_method_text)
    default_total_reads_text = expand_report_text(default_total_reads_text)
    default_coverage_20x_text = expand_report_text(default_coverage_20x_text)
    default_mean_depth_text = expand_report_text(default_mean_depth_text)
    default_filtering_text = expand_report_text(default_filtering_text)
    default_limitations_text = expand_report_text(default_limitations_text)
    placeholders["METHOD_SUMMARY"] = default_method_text
    placeholders["TOTAL_READS"] = default_total_reads_text
    placeholders["COVERAGE_20X"] = default_coverage_20x_text
    placeholders["MEAN_DEPTH"] = default_mean_depth_text
    placeholders["FILTERING_SUMMARY"] = default_filtering_text
    placeholders["LIMITATIONS"] = default_limitations_text
    placeholders["DEFAULT_METHOD_TEXT"] = default_method_text
    placeholders["DEFAULT_TOTAL_READS_TEXT"] = default_total_reads_text
    placeholders["DEFAULT_COVERAGE_20X_TEXT"] = default_coverage_20x_text
    placeholders["DEFAULT_MEAN_DEPTH_TEXT"] = default_mean_depth_text
    placeholders["DEFAULT_FILTERING_TEXT"] = default_filtering_text
    placeholders["DEFAULT_LIMITATIONS_TEXT"] = default_limitations_text
    default_positive_comment_text = expand_report_text(default_positive_comment_text)
    default_negative_result_text = expand_report_text(default_negative_result_text)
    placeholders["DEFAULT_POSITIVE_COMMENT_TEXT"] = default_positive_comment_text
    placeholders["DEFAULT_NEGATIVE_RESULT_TEXT"] = default_negative_result_text

    if negative:
        negative_result_text = default_negative_result_text

        placeholders["INTERPRETATION_TEXT"] = negative_result_text
        placeholders["VARIANT_INTERPRETATION"] = negative_result_text
        placeholders["DEFAULT_NEGATIVE_RESULT_TEXT"] = negative_result_text
        placeholders["NEGATIVE_RESULT_TEXT"] = negative_result_text
    elif first_variant_model:
        positive_comment_text = default_positive_comment_text
        placeholders["INTERPRETATION_TEXT"] = ""
        placeholders["VARIANT_INTERPRETATION"] = positive_comment_text
        placeholders["PHENOTYPE_CORRELATION"] = hpo_terms
        placeholders["DEFAULT_POSITIVE_COMMENT_TEXT"] = positive_comment_text
        placeholders["POSITIVE_COMMENT_TEXT"] = positive_comment_text

    title = f"{test_type_name or 'Test'} Report"
    docx_bytes = build_docx_report_bytes(
        template_path=template_choice.path,
        title=title,
        variants_rows=rows,
        negative=negative,
        placeholders=placeholders,
        rich_text_blocks={
            "SIGNER_1_BLOCK": signer_1_entries,
            "SIGNER_2_BLOCK": signer_2_entries,
            "SIGNER_3_BLOCK": signer_3_entries,
            "AUTHORIZED_SIGNER_BLOCK": [authorized_signer_lines] if any(authorized_signer_lines) else [],
        },
    )

    ts = timezone.now().strftime("%Y%m%d_%H%M")
    fn_safe_test = (test_type_name or "report").replace(" ", "_")
    filename = f"{individual.primary_id}_{fn_safe_test}_{ts}.docx"

    report = AnalysisReport.objects.create(
        analysis=analysis,
        description=(
            f"Generated DOCX ({'negative' if negative else 'variants selected'}) — template: {template_choice.reason}"
        ),
        created_by=request.user,
    )
    report.file.save(filename, ContentFile(docx_bytes))
    if not negative:
        report.variants.set(list(selected_qs))

    workflow_target_id = f"#workflow-content-{individual.pk}" if individual else "#workflow-content"
    html = render(
        request,
        "lab/partials/tabs/_workflow.html",
        {"individual": individual, "workflow_target_id": workflow_target_id},
    ).content.decode()
    close_oob = (
        '<div id="generic-modal-content" hx-swap-oob="innerHTML">'
        '<div x-data x-init="$nextTick(() => document.getElementById(\'generic-modal\').close())"></div>'
        "</div>"
    )
    response = HttpResponse(html + close_oob)
    response["HX-Retarget"] = workflow_target_id
    response["HX-Reswap"] = "innerHTML"
    return response


@login_required
def report_replace_modal(request, report_id):
    from django.shortcuts import get_object_or_404, render
    from django.views.decorators.http import require_http_methods

    from .forms import AnalysisReportReplaceForm
    from .models import AnalysisReport

    report = get_object_or_404(AnalysisReport.objects.select_related("analysis__pipeline__test__sample__individual"), pk=report_id)
    individual = report.analysis.pipeline.test.sample.individual if report.analysis and report.analysis.pipeline_id else None
    workflow_target_id = f"#workflow-content-{individual.pk}" if individual else "#workflow-content"

    @require_http_methods(["GET", "POST"])
    def _inner(request):
        can_change_report = request.user.has_perm("lab.change_analysisreport")
        can_delete_report = request.user.has_perm("lab.delete_analysisreport")

        if not (can_change_report or can_delete_report):
            return HttpResponseForbidden("You do not have permission to modify or delete analysis reports.")

        if request.method == "POST":
            action = request.POST.get("action", "replace")

            if action == "delete":
                if not can_delete_report:
                    return HttpResponseForbidden("You do not have permission to delete analysis reports.")

                # Delete stored files before removing the report record.
                if report.file:
                    report.file.delete(save=False)
                if report.preview_file:
                    report.preview_file.delete(save=False)
                report.delete()

                workflow_target_id = f"#workflow-content-{individual.pk}" if individual else "#workflow-content"
                html = (
                    render(
                        request,
                        "lab/partials/tabs/_workflow.html",
                        {"individual": individual, "workflow_target_id": workflow_target_id},
                    ).content.decode()
                    if individual
                    else ""
                )
                close_oob = (
                    '<div id="generic-modal-content" hx-swap-oob="innerHTML">'
                    '<div x-data x-init="$nextTick(() => document.getElementById(\'generic-modal\').close())"></div>'
                    "</div>"
                )
                response = HttpResponse(html + close_oob)
                response["HX-Retarget"] = workflow_target_id
                response["HX-Reswap"] = "innerHTML"
                return response

            if not can_change_report:
                return HttpResponseForbidden("You do not have permission to replace analysis report files.")

            form = AnalysisReportReplaceForm(request.POST, request.FILES)
            if form.is_valid():
                report.file = form.cleaned_data["file"]
                report.save(update_fields=["file"])
                workflow_target_id = f"#workflow-content-{individual.pk}" if individual else "#workflow-content"
                html = (
                    render(
                        request,
                        "lab/partials/tabs/_workflow.html",
                        {"individual": individual, "workflow_target_id": workflow_target_id},
                    ).content.decode()
                    if individual
                    else ""
                )
                close_oob = (
                    '<div id="generic-modal-content" hx-swap-oob="innerHTML">'
                    '<div x-data x-init="$nextTick(() => document.getElementById(\'generic-modal\').close())"></div>'
                    "</div>"
                )
                response = HttpResponse(html + close_oob)
                response["HX-Retarget"] = workflow_target_id
                response["HX-Reswap"] = "innerHTML"
                return response
        else:
            form = AnalysisReportReplaceForm()

        context = {
            "form": form,
            "title": "Replace Analysis Report File",
            "action_url": request.path,
            "report": report,
            "can_change_report": can_change_report,
            "can_delete_report": can_delete_report,
            "workflow_target_id": workflow_target_id,
        }
        return render(request, "lab/partials/modals/report_replace_modal.html", context)

    return _inner(request)


def _workflow_delete_registry():
    from .models import Analysis, AnalysisReport, Pipeline, Sample, Test
    from variant.models import Variant

    return {
        "sample": {
            "model": Sample,
            "label": "Sample",
            "permission": "lab.delete_sample",
            "blockers": (
                ("Tests", lambda obj: obj.tests.all()),
            ),
        },
        "test": {
            "model": Test,
            "label": "Test",
            "permission": "lab.delete_test",
            "blockers": (
                ("Pipelines", lambda obj: obj.pipelines.all()),
            ),
        },
        "pipeline": {
            "model": Pipeline,
            "label": "Pipeline",
            "permission": "lab.delete_pipeline",
            "blockers": (
                ("Analyses", lambda obj: obj.analyses.all()),
            ),
        },
        "analysis": {
            "model": Analysis,
            "label": "Analysis",
            "permission": "lab.delete_analysis",
            "blockers": (
                ("Variants", lambda obj: obj.found_variants.all()),
                ("Reports", lambda obj: obj.reports.all()),
            ),
        },
        "variant": {
            "model": Variant,
            "label": "Variant",
            "permission": "variant.delete_variant",
            "blockers": (
                ("Reports", lambda obj: obj.reports.all()),
            ),
        },
        "report": {
            "model": AnalysisReport,
            "label": "Report",
            "permission": "lab.delete_analysisreport",
            "blockers": (),
        },
    }


def _workflow_delete_blockers(obj, config):
    blockers = []
    limit = 10

    for label, queryset_fn in config.get("blockers", ()):
        queryset = queryset_fn(obj)
        total = queryset.count()
        if not total:
            continue
        blockers.append(
            {
                "label": label,
                "count": total,
                "objects": [str(item) for item in queryset[:limit]],
                "truncated": total > limit,
            }
        )

    return blockers


def _workflow_delete_context(model_name, obj, config, error=""):
    individual = _resolve_workflow_individual(obj)
    workflow_target_id = f"#workflow-content-{individual.pk}" if individual else "#workflow-content"
    blockers = _workflow_delete_blockers(obj, config)
    return {
        "obj": obj,
        "model_name": model_name,
        "label": config["label"],
        "blockers": blockers,
        "can_delete": not blockers,
        "delete_url": reverse("lab:workflow_delete", kwargs={"model_name": model_name, "pk": obj.pk}),
        "workflow_target_id": workflow_target_id,
        "error": error,
    }


def _close_generic_modal(response):
    response["HX-Trigger"] = "close-modal"
    return response


@login_required
def workflow_delete_confirm(request, model_name, pk):
    registry = _workflow_delete_registry()
    config = registry.get(model_name)
    if not config:
        return HttpResponse(status=404)
    if not request.user.has_perm(config["permission"]):
        return HttpResponseForbidden("You do not have permission to delete this item.")

    obj = get_object_or_404(config["model"], pk=pk)
    context = _workflow_delete_context(model_name, obj, config)
    return render(request, "lab/partials/modals/workflow_delete_confirm.html", context)


@login_required
@require_POST
def workflow_delete(request, model_name, pk):
    from django.db.models.deletion import ProtectedError

    registry = _workflow_delete_registry()
    config = registry.get(model_name)
    if not config:
        return HttpResponse(status=404)
    if not request.user.has_perm(config["permission"]):
        return HttpResponseForbidden("You do not have permission to delete this item.")

    obj = get_object_or_404(config["model"], pk=pk)
    individual = _resolve_workflow_individual(obj)
    blockers = _workflow_delete_blockers(obj, config)
    if blockers:
        context = _workflow_delete_context(
            model_name,
            obj,
            config,
            error="This item cannot be deleted while connected objects exist.",
        )
        response = render(request, "lab/partials/modals/workflow_delete_confirm.html", context)
        response.headers["HX-Retarget"] = "#generic-modal-content"
        response.headers["HX-Reswap"] = "innerHTML"
        return response

    try:
        if model_name == "report":
            if obj.file:
                obj.file.delete(save=False)
            if obj.preview_file:
                obj.preview_file.delete(save=False)
        obj.delete()
    except ProtectedError as exc:
        protected = [
            {
                "label": protected_obj._meta.verbose_name_plural.title(),
                "count": 1,
                "objects": [str(protected_obj)],
                "truncated": False,
            }
            for protected_obj in list(exc.protected_objects)[:10]
        ]
        context = _workflow_delete_context(
            model_name,
            obj,
            config,
            error="This item cannot be deleted because protected records depend on it.",
        )
        context["blockers"] = protected or context["blockers"]
        context["can_delete"] = False
        response = render(request, "lab/partials/modals/workflow_delete_confirm.html", context)
        response.headers["HX-Retarget"] = "#generic-modal-content"
        response.headers["HX-Reswap"] = "innerHTML"
        return response

    if not individual:
        return _close_generic_modal(HttpResponse(status=204))

    workflow_target_id = f"#workflow-content-{individual.pk}"
    workflow_html = render(
        request,
        "lab/partials/tabs/_workflow.html",
        {"individual": individual, "workflow_target_id": workflow_target_id},
    ).content.decode()
    return _close_generic_modal(HttpResponse(workflow_html))


@login_required
def variant_create_modal(request, individual_id=None, analysis_id=None):
    """Create a variant scoped to an individual or an analysis (type-switching modal)."""
    from variant.forms import CNVForm, RepeatForm, SNVForm, SVForm, VariantTypeForm
    from lab.models import Individual, Analysis

    analysis = None
    individual = None
    title = ""
    post_url = ""

    if analysis_id:
        analysis = get_object_or_404(Analysis.objects.select_related("pipeline__test__sample__individual"), pk=analysis_id)
        pipeline = analysis.pipeline
        if not pipeline:
            return HttpResponse("Analysis has no pipeline attached.", status=400)
        individual = pipeline.test.sample.individual
        title = f"Add Variant for {analysis.type.name if analysis.type else 'Analysis'}"
        post_url = reverse("lab:variant_create_for_analysis_modal", kwargs={"analysis_id": analysis.id})
    elif individual_id:
        individual = get_object_or_404(Individual, pk=individual_id)
        title = f"Add Variant for {individual.primary_id}"
        post_url = reverse("lab:variant_create_for_individual_modal", kwargs={"individual_id": individual.id})
    else:
        return HttpResponse("Missing context for variant creation.", status=400)

    variant_type = request.GET.get("variant_type") or request.POST.get("variant_type") or "snv"

    form_class_map = {
        "snv": SNVForm,
        "cnv": CNVForm,
        "sv": SVForm,
        "repeat": RepeatForm,
    }
    form_class = form_class_map.get(variant_type, SNVForm)

    # Build the type selector form (always shown in full modal)
    type_form = VariantTypeForm(initial={"variant_type": variant_type})
    type_form.fields["variant_type"].widget.attrs.update(
        {
            "hx-get": post_url,
            "hx-target": "#variant-type-fields",
            "hx-swap": "innerHTML",
            "hx-trigger": "change",
            "hx-include": 'select[name="variant_type"]',
        }
    )

    if request.method == "POST":
        form = form_class(request.POST, individual=individual)
        if form.is_valid():
            variant = form.save(commit=False)
            variant.individual = individual
            variant.analysis = analysis
            variant.created_by = request.user
            variant.save()

            workflow_target_id = f"#workflow-content-{individual.pk}" if individual else "#workflow-content"
            workflow_html = render(
                request,
                "lab/partials/tabs/_workflow.html",
                {"individual": individual, "workflow_target_id": workflow_target_id},
            ).content.decode()
            target_id = workflow_target_id.lstrip("#")
            response = HttpResponse(
                f'<div id="{target_id}" hx-swap-oob="innerHTML">{workflow_html}</div>'
            )
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = '{"closeModal": true, "close-modal": true}'
            return response
    else:
        form = form_class()

    workflow_target_id = f"#workflow-content-{individual.pk}" if individual else "#workflow-content"

    for field_name, field in form.fields.items():
        current_classes = field.widget.attrs.get("class", "")
        if isinstance(field.widget, forms.TextInput) or isinstance(field.widget, forms.NumberInput) or isinstance(
            field.widget, forms.Select
        ):
            if "select" not in current_classes and "input" not in current_classes:
                if isinstance(field.widget, forms.Select):
                    field.widget.attrs["class"] = f"select select-bordered w-full {current_classes}"
                else:
                    field.widget.attrs["class"] = f"input input-bordered w-full {current_classes}"

    # Only return fields if the request specifically targets "#variant-type-fields"
    if request.method == "GET" and request.headers.get("HX-Target") == "variant-type-fields":
        return render(
            request,
            "lab/partials/modals/variant_add_fields.html",
            {"form": form, "variant_type": variant_type},
        )

    return render(
        request,
        "lab/partials/modals/variant_add_modal.html",
        {
            "title": title,
            "analysis": analysis,
            "type_form": type_form,
            "form": form,
            "variant_type": variant_type,
            "variant_add_post_url": post_url,
            "workflow_target_id": workflow_target_id,
        },
    )


def _safe_deep_get(data, *keys, default=None):
    """Safely traverse nested dict/list, treating a list node as its first element."""
    try:
        result = data
        for k in keys:
            if isinstance(result, dict):
                result = result.get(k)
            elif isinstance(result, list):
                result = result[0].get(k) if result and isinstance(result[0], dict) else None
            else:
                return default
            if result is None:
                return default
        return result
    except (AttributeError, TypeError, IndexError, KeyError):
        return default


def _prepare_vep_display(data):
    item = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else (data if isinstance(data, dict) else {})
    IMPACT_ORDER = {'HIGH': 0, 'MODERATE': 1, 'LOW': 2, 'MODIFIER': 3}

    summary = {}
    if item.get('most_severe_consequence'):
        summary['Most Severe Consequence'] = item['most_severe_consequence'].replace('_', ' ').title()
    if item.get('allele_string'):
        summary['Allele'] = item['allele_string']
    if item.get('assembly_name'):
        summary['Assembly'] = item['assembly_name']
    if item.get('seq_region_name'):
        summary['Region'] = item['seq_region_name']

    transcripts = []
    for tc in item.get('transcript_consequences', []):
        if not isinstance(tc, dict):
            continue
        sift_pred = tc.get('sift_prediction', '')
        sift_score = tc.get('sift_score')
        pp_pred = tc.get('polyphen_prediction', '')
        pp_score = tc.get('polyphen_score')
        transcripts.append({
            'gene':         tc.get('gene_symbol', ''),
            'transcript':   tc.get('transcript_id', ''),
            'biotype':      tc.get('biotype', ''),
            'consequences': ', '.join(tc.get('consequence_terms', [])).replace('_', ' '),
            'impact':       tc.get('impact', ''),
            'hgvsc':        tc.get('hgvsc', ''),
            'hgvsp':        tc.get('hgvsp', ''),
            'sift':         f"{sift_pred} ({sift_score})" if sift_pred and sift_score is not None else sift_pred,
            'sift_pred':    sift_pred,
            'polyphen':     f"{pp_pred} ({pp_score})" if pp_pred and pp_score is not None else pp_pred,
            'polyphen_pred': pp_pred,
            'canonical':    tc.get('canonical', 0),
        })

    transcripts.sort(key=lambda t: (0 if t['canonical'] else 1, IMPACT_ORDER.get(t['impact'], 99)))
    return {'type': 'vep', 'summary': summary, 'transcripts': transcripts[:25]}


def _prepare_myvariant_display(data):
    if not isinstance(data, dict):
        return {'type': 'generic', 'fields': {}}
    g = _safe_deep_get
    sections = {}

    pop = {}
    v = g(data, 'gnomad_genome', 'af', 'af')
    if v is not None: pop['gnomAD Genome AF'] = f"{float(v):.2e}"
    v = g(data, 'gnomad_exome', 'af', 'af')
    if v is not None: pop['gnomAD Exome AF'] = f"{float(v):.2e}"
    v = g(data, 'gnomad', 'af')
    if v is not None and not pop: pop['gnomAD AF'] = f"{float(v):.2e}"
    if pop:
        sections['Population Frequencies'] = pop

    path = {}
    v = g(data, 'cadd', 'phred')
    if v is not None: path['CADD Phred'] = str(v)
    v = g(data, 'cadd', 'rawscore')
    if v is not None: path['CADD Raw'] = f"{float(v):.4f}"
    v = g(data, 'dbnsfp', 'sift', 'pred')
    if v: path['SIFT'] = v if isinstance(v, str) else str(v)
    v = g(data, 'dbnsfp', 'polyphen2', 'hdiv', 'pred')
    if v: path['PolyPhen2 (HDIV)'] = v if isinstance(v, str) else str(v)
    v = g(data, 'dbnsfp', 'mutationtaster', 'pred')
    if v: path['MutationTaster'] = v if isinstance(v, str) else str(v)
    v = g(data, 'dbnsfp', 'revel', 'score')
    if v is not None: path['REVEL'] = str(v)
    if path:
        sections['Pathogenicity Scores'] = path

    clin = {}
    v = g(data, 'clinvar', 'rcv', 'clinical_significance') or g(data, 'clinvar', 'clinical_significance')
    if v: clin['Significance'] = v if isinstance(v, str) else str(v)
    v = g(data, 'clinvar', 'rcv', 'conditions', 'name')
    if v: clin['Condition'] = v if isinstance(v, str) else str(v)
    v = g(data, 'clinvar', 'gene', 'symbol')
    if v: clin['Gene'] = v
    if clin:
        sections['ClinVar'] = clin

    return {'type': 'myvariant', 'sections': sections}


def _prepare_genebe_display(data):
    if not isinstance(data, dict):
        return {'type': 'generic', 'fields': {}}
    g = _safe_deep_get
    vd = g(data, 'variants', 0)
    if not isinstance(vd, dict):
        vd = data

    fields = {}
    def pick(*paths):
        for path in paths:
            value = g(vd, *path) if isinstance(path, tuple) else g(vd, path)
            if value is None:
                value = g(data, *path) if isinstance(path, tuple) else g(data, path)
            if value is not None:
                return value
        return None

    for label, path in [
        ('Gene', ('gene_symbol',)),
        ('Transcript', ('transcript',)),
        ('Effect', ('effect',)),
        ('ACMG Classification', ('acmg_classification',)),
        ('ACMG Score', ('acmg_score',)),
        ('ClinVar Classification', ('clinvar_classification',)),
        ('ClinVar Review Status', ('clinvar_review_status',)),
        ('Combined Pathogenicity', ('pathogenicity_classification_combined',)),
        ('Population AF', ('frequency_reference_population',)),
        ('gnomAD Exomes AF', ('gnomad_exomes_af',)),
        ('gnomAD Genomes AF', ('gnomad_genomes_af',)),
        ('Computational Prediction', ('computational_prediction_selected',)),
        ('Splice Prediction', ('splice_prediction_selected',)),
    ]:
        v = pick(path)
        if v is not None and v != '':
            if label.endswith('AF'):
                try:
                    fields[label] = f"{float(v):.2e}"
                except (TypeError, ValueError):
                    fields[label] = str(v)
            else:
                fields[label] = str(v)

    criteria = g(vd, 'acmg_criteria') or g(data, 'acmg_criteria') or []
    if isinstance(criteria, str):
        criteria = [c.strip() for c in criteria.split(',') if c.strip()]
    elif not isinstance(criteria, list):
        criteria = [criteria] if criteria else []

    gene_records = []
    for item in g(vd, 'acmg_by_gene') or g(data, 'acmg_by_gene') or []:
        if not isinstance(item, dict):
            continue
        gene_records.append({
            'gene_symbol': item.get('gene_symbol'),
            'verdict': item.get('verdict'),
            'score': item.get('score'),
            'inheritance_mode': item.get('inheritance_mode'),
            'transcript': item.get('transcript'),
            'criteria': item.get('criteria'),
            'effects': item.get('effects'),
        })

    return {'type': 'genebe', 'fields': fields, 'criteria': criteria, 'gene_records': gene_records}


def _prepare_generic_display(data):
    items = data if isinstance(data, dict) else (data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {})
    fields = {
        k: str(v) if not isinstance(v, (dict, list)) else f"[{type(v).__name__}, {len(v)} items]"
        for k, v in items.items() if not str(k).startswith('_') and v is not None
    }
    return {'type': 'generic', 'fields': fields}


def _prepare_annotation_display(annotation):
    source = (annotation.source or '').lower()
    if 'vep' in source:
        return _prepare_vep_display(annotation.data)
    elif 'myvariant' in source:
        return _prepare_myvariant_display(annotation.data)
    elif 'genebe' in source:
        return _prepare_genebe_display(annotation.data)
    else:
        return _prepare_generic_display(annotation.data)


@login_required
def variant_detail_partial(request, pk):
    """Return the expanded detail panel for a single variant row."""
    from variant.models import Variant
    from variant.forms import VariantACMGEvidenceOverrideForm
    variant = get_object_or_404(
        Variant.objects.select_related(
            "individual",
            "created_by",
            # Variant is now linked to Analysis, which links to Pipeline.
            "analysis",
            "analysis__pipeline__type",
            "analysis__pipeline__performed_by",
            "analysis__pipeline__test__test_type",
            "analysis__pipeline__test__sample__sample_type",
        ).prefetch_related(
            "genes",
            "statuses",
            "classifications__user",
            "annotations",
            "acmg_evidence_overrides",
            "notes__user",
            "notes__private_owner",
            "tasks__assigned_to",
            "tasks__statuses",
            "individual__samples__sample_type",
            "individual__samples__statuses",
            "individual__samples__tests__test_type",
            "individual__samples__tests__statuses",
            "individual__samples__tests__performed_by",
            "individual__samples__tests__pipelines__type",
            "individual__samples__tests__pipelines__statuses",
            "individual__samples__tests__pipelines__performed_by",
            "individual__samples__tests__pipelines__analyses__type",
            "individual__samples__tests__pipelines__analyses__statuses",
            "individual__samples__tests__pipelines__analyses__performed_by",
        ),
        pk=pk,
    )
    annotations_display = [
        {"annotation": ann, "display": _prepare_annotation_display(ann)}
        for ann in variant.annotations.all()
    ]

    # Gene-in-cohort: for each gene, collect all variants (and their workflow) sharing that gene
    gene_cohort_data = []
    for gene in variant.genes.all():
        gene_variants = (
            Variant.objects.filter(genes=gene)
            .select_related(
                "individual",
                "analysis",
                "analysis__pipeline__type",
                "analysis__pipeline__test__test_type",
            )
            .prefetch_related(
                "analysis__pipeline__analyses__type",
                "individual__hpo_terms",
                "individual__institution",
                "individual__cross_ids__id_type",
            )
            .order_by("individual__id")
        )

        entries = []
        for v in gene_variants:
            analysis = v.analysis
            pipeline = analysis.pipeline if analysis and getattr(analysis, "pipeline_id", None) else None
            test = pipeline.test if pipeline and getattr(pipeline, "test_id", None) else None

            entries.append(
                {
                    "variant": v,
                    "individual": v.individual,
                    "is_current": v.pk == variant.pk,
                    "pipeline": pipeline,
                    "test": test,
                    "analysis": analysis,
                }
            )

        gene_cohort_data.append({
            "gene": gene,
            "entries": entries,
            "count": len(entries),
        })

    return render(request, "lab/partials/variant_detail.html", {
        "variant": variant,
        "annotations_display": annotations_display,
        "gene_cohort_data": gene_cohort_data,
        "manual_override_form": VariantACMGEvidenceOverrideForm(),
        "manual_acmg_overrides": variant.acmg_evidence_overrides.filter(source="manual").order_by("criterion"),
        "selected_criteria": [],
    })


@login_required
@require_http_methods(["GET"])
def variant_genebe_fetch(request, pk):
    from variant.models import Variant
    from variant.services import AnnotationService
    from variant.forms import VariantACMGEvidenceOverrideForm

    if not request.user.has_perm("variant.change_variant"):
        return HttpResponseForbidden("You do not have permission to fetch GeneBe classifications.")

    variant = get_object_or_404(
        Variant.objects.select_related("individual", "analysis").prefetch_related("annotations"),
        pk=pk,
    )

    service = AnnotationService()
    genebe_data = service.fetch_genebe(variant)
    service.link_genes(variant)

    variant = Variant.objects.prefetch_related("annotations", "acmg_evidence_overrides").get(pk=pk)

    return render(request, "variant/partials/_genebe_classification.html", {
        "variant": variant,
        "genebe_data": genebe_data,
        "manual_override_form": VariantACMGEvidenceOverrideForm(),
        "manual_acmg_overrides": variant.acmg_evidence_overrides.filter(source="manual").order_by("criterion"),
        "selected_criteria": [],
    })


@login_required
@require_POST
def variant_acmg_evidence_save(request, pk):
    from variant.models import Variant, ACMGEvidenceOverride
    from variant.templatetags.variant_filters import (
        ACMG_CRITERIA_INFO,
        _default_strength_for_info,
        _imported_acmg_criteria_set,
        _normalize_strength,
        _record_acmg_map,
    )

    variant = get_object_or_404(Variant.objects.prefetch_related("annotations", "acmg_evidence_overrides"), pk=pk)

    if not request.user.has_perm("variant.change_variant"):
        return HttpResponseForbidden("You do not have permission to change ACMG evidence.")

    catalog_criteria = set(ACMG_CRITERIA_INFO)
    gene_symbol = (request.POST.get("gene_symbol") or "").strip()
    transcript = (request.POST.get("transcript") or "").strip()
    included_criteria = {
        str(item).strip().replace(" ", "_").upper()
        for item in request.POST.getlist("included_criteria")
        if str(item).strip()
    }
    included_criteria &= catalog_criteria

    imported_criteria = _imported_acmg_criteria_set(variant, gene_symbol, transcript) & catalog_criteria
    imported_map = _record_acmg_map(variant, "genebe", gene_symbol, transcript)

    for criterion in catalog_criteria:
        default_strength = _default_strength_for_info(ACMG_CRITERIA_INFO[criterion])
        imported_record = imported_map.get(criterion)
        imported_strength = _normalize_strength(
            imported_record.strength if imported_record else default_strength,
            default_strength,
        )
        selected_strength = _normalize_strength(
            request.POST.get(f"strength_{criterion}"),
            "indeterminate" if criterion not in included_criteria else default_strength,
        )
        should_include = criterion in included_criteria and selected_strength != "indeterminate"
        was_imported = criterion in imported_criteria

        if should_include == was_imported and (
            not should_include or selected_strength == imported_strength
        ):
            ACMGEvidenceOverride.objects.filter(
                variant=variant,
                gene_symbol=gene_symbol,
                transcript=transcript,
                criterion=criterion,
                source="manual",
            ).delete()
            continue

        ACMGEvidenceOverride.objects.update_or_create(
            variant=variant,
            gene_symbol=gene_symbol,
            transcript=transcript,
            criterion=criterion,
            source="manual",
            defaults={
                "included": should_include,
                "strength": selected_strength if should_include else "indeterminate",
                "note": "",
                "created_by": request.user,
            },
        )

    variant = Variant.objects.prefetch_related("annotations", "acmg_evidence_overrides").get(pk=pk)

    genebe = variant.annotations.filter(source="genebe").first()
    genebe_data = genebe.data if genebe else None
    return render(request, "variant/partials/_genebe_classification.html", {
        "variant": variant,
        "genebe_data": genebe_data,
        "manual_acmg_overrides": variant.acmg_evidence_overrides.filter(source="manual").order_by("criterion"),
    })


# ---------------------------------------------------------------------------
# Configurations CRUD (generic HTMX views)
# ---------------------------------------------------------------------------

def _get_config_registry():
    from .models import Contact, SampleType, TestType, Institution, PipelineType, AnalysisType, IdentifierType, Status, StatusGroup
    from .forms import (
        ContactConfigForm, SampleTypeForm, TestTypeForm, InstitutionConfigForm,
        PipelineTypeForm, AnalysisTypeForm, IdentifierTypeForm,
        StatusConfigForm, StatusGroupConfigForm,
    )
    return {
        "sampletype": {
            "model": SampleType, "form": SampleTypeForm,
            "label": "Sample Types", "icon": "fa-solid fa-vial",
            "fields": ["name", "description"],
            "usage_relation": "sample",
            "usage_label": "samples",
        },
        "testtype": {
            "model": TestType, "form": TestTypeForm,
            "label": "Test Types", "icon": "fa-solid fa-flask",
            "fields": ["name", "description"],
            "usage_relation": "test",
            "usage_label": "tests",
        },
        "pipelinetype": {
            "model": PipelineType, "form": PipelineTypeForm,
            "label": "Pipeline Types", "icon": "fa-solid fa-diagram-project",
            "fields": ["name", "version", "description"],
            "usage_relation": "pipeline",
            "usage_label": "pipelines",
        },
        "analysistype": {
            "model": AnalysisType, "form": AnalysisTypeForm,
            "label": "Analysis Types", "icon": "fa-solid fa-microscope",
            "fields": ["name", "description"],
            "usage_relation": "analyses",   # related_name on Analysis.type
            "usage_label": "analyses",
        },
        "identifiertype": {
            "model": IdentifierType, "form": IdentifierTypeForm,
            "label": "Identifier Types", "icon": "fa-solid fa-id-badge",
            "fields": ["name", "example", "use_priority", "is_shown_in_table"],
            "usage_relation": "crossidentifier",
            "usage_label": "identifiers",
        },
        "statusgroup": {
            "model": StatusGroup, "form": StatusGroupConfigForm,
            "label": "Status Groups", "icon": "fa-regular fa-circle-dot",
            "fields": ["name", "content_type"],
            "usage_relation": "statuses",
            "usage_label": "statuses",
        },
        "status": {
            "model": Status, "form": StatusConfigForm,
            "label": "Statuses", "icon": "fa-solid fa-circle-dot",
            "fields": ["name", "short_name", "color"],
            "usage_relation": None,  # computed specially across many models
            "usage_label": "objects",
        },
        "institution": {
            "model": Institution, "form": InstitutionConfigForm,
            "label": "Institutions", "icon": "fa-solid fa-hospital",
            "fields": ["name", "city", "speciality"],
            "usage_relation": "individuals",  # M2M related_name
            "usage_label": "individuals",
            # M2M fields are invisible to Django's Collector, so we guard manually.
            "m2m_protections": [
                {"accessor": "individuals", "verbose_name": "individual"},
            ],
        },
        "contact": {
            "model": Contact, "form": ContactConfigForm,
            "label": "Contacts", "icon": "fa-solid fa-address-book",
            "fields": ["full_name", "emails", "phones", "institutions_as_staff"],
            "usage_relation": "patients",
            "usage_label": "patients",
            "m2m_protections": [
                {"accessor": "patients", "verbose_name": "individual"},
                {"accessor": "institutions_as_staff", "verbose_name": "institution"},
            ],
        },
    }


def _check_m2m_protections(obj, config):
    """
    Return a list of {'type': ..., 'display': ...} dicts for any M2M-related
    objects that should block deletion (Django's Collector won't catch these).
    """
    result = []
    for guard in config.get("m2m_protections", []):
        accessor = guard["accessor"]
        verbose = guard["verbose_name"]
        related_qs = getattr(obj, accessor).all()
        sample = list(related_qs[:10])
        if sample:
            for related_obj in sample:
                result.append({
                    "type": verbose.title(),
                    "display": str(related_obj),
                })
            remaining = related_qs.count() - len(sample)
            if remaining > 0:
                result.append({
                    "type": verbose.title(),
                    "display": f"… and {remaining} more",
                })
    return result


def _compute_status_usage():
    """Return {status_id: total_usage_count} across all TaggedStatus records."""
    from collections import defaultdict
    from django.db.models import Count
    from .models import TaggedStatus

    usage = defaultdict(int)
    for row in TaggedStatus.objects.values("tag_id").annotate(c=Count("id")):
        usage[row["tag_id"]] += row["c"]
    return dict(usage)


def _build_section_context(request, key, config):
    """Build per-section context dict for the config_section partial."""
    from django.db.models import Count

    usage_relation = config.get("usage_relation")
    if usage_relation:
        objects = config["model"].objects.annotate(
            usage_count=Count(usage_relation, distinct=True)
        )
    else:
        objects = config["model"].objects.all()

    ctx = {
        "key": key,
        "label": config["label"],
        "icon": config["icon"],
        "fields": config["fields"],
        "objects": objects,
        "usage_label": config.get("usage_label", ""),
        "can_add": request.user.has_perm(f"lab.add_{key}"),
        "can_change": request.user.has_perm(f"lab.change_{key}"),
        "can_delete": request.user.has_perm(f"lab.delete_{key}"),
    }

    if key == "status":
        from .models import Status
        usage_map = _compute_status_usage()
        from django.db.models import F
        statuses = Status.objects.select_related("content_type", "group").order_by(
            "content_type__app_label", "content_type__model",
            F("group__name").asc(nulls_last=True), "name"
        )
        # Attach pre-computed usage count to each status object
        for s in statuses:
            s.usage_count = usage_map.get(s.pk, 0)
        groups = {}
        for status in statuses:
            if status.content_type:
                group_key = status.content_type.model
                group_label = status.content_type.model.replace("_", " ").title()
            else:
                group_key = "__global__"
                group_label = "Global"
            if group_key not in groups:
                groups[group_key] = {"label": group_label, "objects": []}
            groups[group_key]["objects"].append(status)
        # Put Global first, then alphabetical
        ordered = {}
        if "__global__" in groups:
            ordered["__global__"] = groups.pop("__global__")
        for k in sorted(groups):
            ordered[k] = groups[k]
        ctx["status_groups"] = ordered
    elif key == "statusgroup":
        groups = {}
        status_groups = objects.select_related("content_type").order_by(
            "content_type__app_label", "content_type__model", "name"
        )
        for status_group in status_groups:
            if status_group.content_type:
                group_key = status_group.content_type.model
                group_label = status_group.content_type.model.replace("_", " ").title()
            else:
                group_key = "__global__"
                group_label = "Global"
            if group_key not in groups:
                groups[group_key] = {"label": group_label, "objects": []}
            groups[group_key]["objects"].append(status_group)
        ordered = {}
        if "__global__" in groups:
            ordered["__global__"] = groups.pop("__global__")
        for k in sorted(groups):
            ordered[k] = groups[k]
        ctx["status_group_scopes"] = ordered

    return ctx


@login_required
def config_section_partial(request, model_name):
    """Return refreshed HTML for a single config section (used after CRUD operations)."""
    registry = _get_config_registry()
    if model_name not in registry:
        return HttpResponse(status=404)
    config = registry[model_name]
    if not (request.user.has_perm(f"lab.view_{model_name}") or
            request.user.has_perm(f"lab.change_{model_name}")):
        return HttpResponse(status=403)
    ctx = {"section": _build_section_context(request, model_name, config)}
    return render(request, "lab/partials/config_section.html", ctx)


@login_required
def config_form(request, model_name, pk=None):
    """
    GET  → render add/edit form inside the generic modal.
    POST → save and return updated section HTML (success) or form with errors
           (re-targeted back into the modal).
    """
    registry = _get_config_registry()
    if model_name not in registry:
        return HttpResponse(status=404)

    config = registry[model_name]
    Model = config["model"]
    FormClass = config["form"]

    required_perm = f"lab.{'change' if pk else 'add'}_{model_name}"
    if not request.user.has_perm(required_perm):
        return HttpResponseForbidden("Permission denied.")

    instance = get_object_or_404(Model, pk=pk) if pk else None

    if request.method == "POST":
        form = FormClass(request.POST, instance=instance)
        if form.is_valid():
            obj = form.save(commit=False)
            if not getattr(obj, "created_by_id", None):
                obj.created_by = request.user
            obj.save()
            if hasattr(form, "save_m2m"):
                form.save_m2m()

            # Return the refreshed section as primary + close-modal snippet as OOB
            ctx = {"section": _build_section_context(request, model_name, config)}
            section_html = render(request, "lab/partials/config_section.html", ctx).content.decode()
            close_oob = (
                '<div id="generic-modal-content" hx-swap-oob="innerHTML">'
                '<div x-data x-init="$nextTick(() => document.getElementById(\'generic-modal\').close())"></div>'
                '</div>'
            )
            return HttpResponse(section_html + close_oob)
        else:
            # Re-render the form with errors back into the modal
            ctx = {
                "model_name": model_name,
                "label": config["label"],
                "form": form,
                "pk": pk,
                "action_url": request.path,
                "section_id": f"config-section-{model_name}",
            }
            response = render(request, "lab/partials/config_form.html", ctx)
            response.headers["HX-Retarget"] = "#generic-modal-content"
            response.headers["HX-Reswap"] = "innerHTML"
            return response

    # GET – render empty/pre-filled form
    form = FormClass(instance=instance)
    ctx = {
        "model_name": model_name,
        "label": config["label"],
        "form": form,
        "pk": pk,
        "action_url": request.path,
        "section_id": f"config-section-{model_name}",
    }
    return render(request, "lab/partials/config_form.html", ctx)


@login_required
def config_delete_confirm(request, model_name, pk):
    """Render a delete-confirmation snippet (loads into the generic modal)."""
    registry = _get_config_registry()
    if model_name not in registry:
        return HttpResponse(status=404)

    config = registry[model_name]
    if not request.user.has_perm(f"lab.delete_{model_name}"):
        return HttpResponseForbidden("Permission denied.")

    obj = get_object_or_404(config["model"], pk=pk)

    # Collect related objects (Django-admin style).
    # PROTECT fields raise ProtectedError inside collector.collect() itself,
    # so we must catch it here — not just at obj.delete() time.
    from django.db.models.deletion import Collector, ProtectedError
    from django.db import router

    cascade = {}
    protected = []

    using = router.db_for_write(config["model"])
    collector = Collector(using=using)
    try:
        collector.collect([obj], keep_parents=False)
        # Objects that would be cascade-deleted (excluding the item itself)
        for model_cls, objs in collector.data.items():
            if model_cls is config["model"]:
                continue
            label = model_cls._meta.verbose_name_plural.title()
            cascade[label] = [str(o) for o in list(objs)[:10]]
    except ProtectedError as exc:
        protected = [
            {"type": o._meta.verbose_name.title(), "display": str(o)}
            for o in list(exc.protected_objects)[:10]
        ]

    # M2M relations are invisible to Collector — check them separately.
    protected.extend(_check_m2m_protections(obj, config))

    ctx = {
        "obj": obj,
        "model_name": model_name,
        "label": config["label"],
        "cascade": cascade,
        "protected": protected,
        "delete_url": f"/htmx/config/{model_name}/{pk}/delete/",
        "section_id": f"config-section-{model_name}",
    }
    return render(request, "lab/partials/config_delete_confirm.html", ctx)


@login_required
@require_POST
def config_delete(request, model_name, pk):
    """Execute deletion and return the refreshed section (or protected error)."""
    registry = _get_config_registry()
    if model_name not in registry:
        return HttpResponse(status=404)

    config = registry[model_name]
    if not request.user.has_perm(f"lab.delete_{model_name}"):
        return HttpResponseForbidden("Permission denied.")

    obj = get_object_or_404(config["model"], pk=pk)

    # Block on M2M protections before attempting deletion.
    m2m_blocked = _check_m2m_protections(obj, config)
    if m2m_blocked:
        ctx = {
            "obj": obj,
            "model_name": model_name,
            "label": config["label"],
            "cascade": {},
            "protected": m2m_blocked,
            "delete_url": f"/htmx/config/{model_name}/{pk}/delete/",
            "section_id": f"config-section-{model_name}",
            "error": "This item cannot be deleted because other records depend on it.",
        }
        response = render(request, "lab/partials/config_delete_confirm.html", ctx)
        response.headers["HX-Retarget"] = "#generic-modal-content"
        response.headers["HX-Reswap"] = "innerHTML"
        return response

    from django.db.models.deletion import ProtectedError
    try:
        obj.delete()
    except ProtectedError as exc:
        protected_objs = [
            {"type": o._meta.verbose_name.title(), "display": str(o)}
            for o in list(exc.protected_objects)[:10]
        ]
        ctx = {
            "obj": obj,
            "model_name": model_name,
            "label": config["label"],
            "cascade": {},
            "protected": protected_objs,
            "delete_url": f"/htmx/config/{model_name}/{pk}/delete/",
            "section_id": f"config-section-{model_name}",
            "error": "This item cannot be deleted because other records depend on it.",
        }
        response = render(request, "lab/partials/config_delete_confirm.html", ctx)
        response.headers["HX-Retarget"] = "#generic-modal-content"
        response.headers["HX-Reswap"] = "innerHTML"
        return response

    # Success – return refreshed section and close the modal via HTMX event.
    ctx = {"section": _build_section_context(request, model_name, config)}
    section_html = render(request, "lab/partials/config_section.html", ctx).content.decode()
    return _close_generic_modal(HttpResponse(section_html))
