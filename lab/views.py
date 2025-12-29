from django.apps import apps
from django import forms as dj_forms
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest, HttpResponseForbidden, JsonResponse, HttpResponse
from django.db.models import Q, Count, Min
from django.contrib.contenttypes.models import ContentType
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.vary import vary_on_headers
from django.template.loader import render_to_string
from django.template import TemplateDoesNotExist
from django.template.response import TemplateResponse
from django.contrib import messages
import json

# Import encrypted field filtering functions
from .filters import _is_encrypted_field, _separate_encrypted_fields, _filter_encrypted_fields

# Import models
from .models import (
    Individual,
    Test,
    Analysis,
    Sample,
    Task,
    Note,
    Project,
    Institution,
    IdentifierType,
    CrossIdentifier,
    Family,
    Status,
)
from django.contrib.auth.models import User

# Import forms
from .forms import NoteForm, FORMS_MAPPING, TaskForm

# Import visualization functions
from .visualization.hpo_network_visualization import (
    process_hpo_data,
    cytoscape_hpo_network,
    cytoscape_elements_json,
)
from .visualization.plots import plots_page as plots_view
from .visualization.maps import generate_map_data
from .visualization.timeline import timeline


from .filters import (
    apply_filters,
    FILTER_CONFIG,
    get_available_statuses,
    get_available_types,
    get_sort_options,
)

# Import SQL agent for natural language search
from .sql_agent import query_natural_language


def _format_user_label(user):
    full_name = (user.get_full_name() or "").strip()
    if full_name:
        return full_name
    if getattr(user, "username", ""):
        return user.username
    if getattr(user, "email", ""):
        return user.email
    return f"User {user.pk}"


def _parse_id_list(raw_value):
    """
    Normalize a raw POST value into a list of string IDs.
    Accepts JSON lists, comma-separated strings, or already iterable values.
    """
    if not raw_value:
        return []
    if isinstance(raw_value, (list, tuple)):
        return [str(v) for v in raw_value if str(v).strip()]
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            return [str(v) for v in parsed if str(v).strip()]
        if parsed:
            return [str(parsed)]
    except Exception:
        pass
    return [v.strip() for v in str(raw_value).split(",") if v.strip()]


def _staff_initial_json_from_queryset(qs):
    if not qs:
        return "[]"
    data = [{"value": str(user.pk), "label": _format_user_label(user)} for user in qs]
    return json.dumps(data)


def _parse_staff_ids(raw_value):
    return _parse_id_list(raw_value)


def _staff_initial_json_from_ids(id_list):
    ids = [str(_id) for _id in id_list if str(_id).strip()]
    if not ids:
        return "[]"
    users = User.objects.filter(pk__in=ids)
    label_map = {str(user.pk): _format_user_label(user) for user in users}
    ordered = [{"value": pk, "label": label_map.get(pk, pk)} for pk in ids if pk in label_map]
    return json.dumps(ordered)


def _staff_initial_json_from_post(post_data):
    if not post_data:
        return "[]"
    raw = post_data.get("staff_ids") or post_data.get("staff")
    return _staff_initial_json_from_ids(_parse_staff_ids(raw))


def _institution_initial_json_from_queryset(qs):
    if not qs:
        return "[]"
    data = [
        {"value": str(inst.pk), "label": getattr(inst, "name", str(inst))}
        for inst in qs
    ]
    return json.dumps(data)


def _institution_initial_json_from_ids(id_list):
    ids = [str(_id) for _id in id_list if str(_id).strip()]
    if not ids:
        return "[]"
    institutions = Institution.objects.filter(pk__in=ids)
    label_map = {str(inst.pk): getattr(inst, "name", str(inst)) for inst in institutions}
    ordered = [
        {"value": pk, "label": label_map.get(pk, pk)} for pk in ids if pk in label_map
    ]
    return json.dumps(ordered)


def _institution_initial_json_from_post(post_data):
    if not post_data:
        return "[]"
    raw = post_data.get("institution_ids") or post_data.get("institution")
    return _institution_initial_json_from_ids(_parse_id_list(raw))


@login_required
@require_POST
def task_complete(request, pk):
    """Mark a Task as completed and return the updated card/detail partial.

    Uses the Task.complete(user) model method to set status to 'Completed'.
    """
    task = get_object_or_404(Task, pk=pk)
    try:
        was_changed = task.complete(request.user)
    except Exception as e:
        return HttpResponseBadRequest(str(e))

    # Decide which partial to render based on provided context
    # Prefer to update the card in lists; fall back to detail when needed
    template_name = "lab/task.html#card"
    if request.POST.get("view") == "detail":
        template_name = "lab/task.html#detail"

    response = render(
        request,
        template_name,
        {
            "item": task,
            "model_name": "Task",
            "app_label": "lab",
        },
    )
    # Optionally trigger a front-end event to refresh filters/counts
    response["HX-Trigger"] = json.dumps(
        {
            "taskStatusUpdated": {
                "pk": task.pk,
                "status": getattr(task.status, "name", None),
            },
            "filters-updated": True,
        }
    )
    return response


@login_required
@require_POST
def task_reopen(request, pk):
    """Reopen a Task by setting its status to 'Active' and return updated partial."""
    task = get_object_or_404(Task, pk=pk)
    target_status = task.previous_status
    if target_status is None:
        target_status = Status.objects.filter(name__iexact="active").first()
        if not target_status:
            return HttpResponseBadRequest("No 'Active' status found in Status model.")
    # Update if different
    if task.status_id != target_status.id:
        task.status = target_status
        # Update related object's status if supported
        if hasattr(task.content_object, "update_status"):
            task.content_object.update_status(
                target_status,
                request.user,
                f"Status updated via task reopen: {task.title}",
            )
        task.save()

    template_name = "lab/task.html#card"
    if request.POST.get("view") == "detail":
        template_name = "lab/task.html#detail"

    response = render(
        request,
        template_name,
        {
            "item": task,
            "model_name": "Task",
            "app_label": "lab",
        },
    )
    response["HX-Trigger"] = json.dumps(
        {
            "taskStatusUpdated": {
                "pk": task.pk,
                "status": getattr(task.status, "name", None),
            },
            "filters-updated": True,
        }
    )
    return response


@login_required
def index(request):
    def get_initial_json(model_class, param_name):
        val = request.GET.get(param_name)
        if not val:
            return "[]"
        ids = []
        if val.startswith("[") and val.endswith("]"):
            try:
                ids = json.loads(val)
            except:
                pass
        elif "," in val:
            try:
                ids = [int(x) for x in val.split(",") if x.strip().isdigit()]
            except:
                pass
        elif val.isdigit():
            ids = [int(val)]
        
        if not ids:
            return "[]"
            
        objs = model_class.objects.filter(pk__in=ids)
        return json.dumps([{"value": obj.pk, "label": str(obj)} for obj in objs])

    # Display preferences with sensible defaults
    profile = getattr(request.user, "profile", None)
    raw_display_prefs = {}
    if profile and hasattr(profile, "display_preferences"):
        raw_display_prefs = profile.display_preferences or {}
    display_preferences = {
        "filter_popup_on_hover": raw_display_prefs.get("filter_popup_on_hover", True),
        "default_list_view": raw_display_prefs.get("default_list_view", "cards"),
    }

    context = {
        "institutions": Institution.objects.all(),
        "individual_statuses": Status.objects.filter(
            Q(content_type=ContentType.objects.get_for_model(Individual))
            | Q(content_type__isnull=True)
        ).order_by("name"),
        "initial_projects": get_initial_json(Project, "filter_project"),
        "initial_tests": get_initial_json(Test, "filter_test"),
        "initial_analyses": get_initial_json(Analysis, "filter_analysis"),
        "initial_institutions": get_initial_json(Institution, "filter_institution"),
        "display_preferences": display_preferences,
    }

    if request.headers.get("HX-Request"):
        return render(request, "lab/index.html#index", context)
    return render(request, "lab/index.html", context)


@login_required
def generic_search(request):
    target_app_label = request.GET.get("app_label", "lab").strip()  # Get app_label
    target_model_name = request.GET.get("model_name", "").strip()
    if not target_model_name:
        return HttpResponseBadRequest("Model not specified.")

    target_model = apps.get_model(
        app_label=target_app_label, model_name=target_model_name
    )

    filtered_items = apply_filters(
        request, target_model_name, target_model.objects.all()
    )

    # Number of items after applying current filters
    num_items = filtered_items.count()
    # Total number of items without filters (for X/Y display in header)
    total_items = target_model.objects.count()

    # Pagination (may be recomputed for combobox below)
    page = request.GET.get("page")
    paginator = Paginator(filtered_items, 12)
    paged_items = paginator.get_page(page)

    # The rest of the view remains the same...
    own_search_term = request.GET.get("search", "").strip()
    card_partial = request.GET.get("card", "card")
    view_mode = request.GET.get("view_mode", "cards")
    icon_class = request.GET.get("icon_class", "fa-magnifying-glass")
    # Combobox render mode (for Select2-like behavior)
    render_mode = request.GET.get("render")
    if render_mode == "combobox":
        # Apply free-text search for combobox results
        value_field = request.GET.get("value_field", "pk")
        label_field = request.GET.get("label_field")
        base_qs = filtered_items
        if own_search_term:
            try:
                if label_field:
                    # Special handling for Individual model with individual_id property
                    # individual_id is a property, so we search on cross_ids__id_value instead
                    if target_model_name == "Individual" and label_field == "individual_id":
                        # Search on cross_ids__id_value (the actual database field containing ID values)
                        # Also search by full_name (encrypted field)
                        q_label = Q(cross_ids__id_value__icontains=own_search_term)
                        
                        # Search by full_name using encrypted field filtering
                        encrypted_queryset = _filter_encrypted_fields(
                            base_qs, 
                            ["full_name"], 
                            [own_search_term], 
                            exact_match=False, 
                            exclude=False
                        )
                        encrypted_pks = set(encrypted_queryset.values_list("pk", flat=True))
                        
                        # Get PKs from cross_ids search
                        cross_ids_pks = set(base_qs.filter(q_label).values_list("pk", flat=True))
                        
                        # Combine both searches with OR logic
                        all_pks = cross_ids_pks | encrypted_pks
                        
                        if all_pks:
                            base_qs = base_qs.filter(pk__in=list(all_pks)).distinct()
                        else:
                            base_qs = base_qs.none()
                    else:
                        # Try direct icontains on specified label field
                        # BUT ALSO include cross_id search for related models if applicable
                        q_label = Q(**{f"{label_field}__icontains": own_search_term})
                        
                        # For Individual model, also search by full_name (encrypted field)
                        if target_model_name == "Individual":
                            encrypted_queryset = _filter_encrypted_fields(
                                base_qs,
                                ["full_name"],
                                [own_search_term],
                                exact_match=False,
                                exclude=False
                            )
                            encrypted_pks = set(encrypted_queryset.values_list("pk", flat=True))
                            label_pks = set(base_qs.filter(q_label).values_list("pk", flat=True))
                            all_pks = label_pks | encrypted_pks
                            if all_pks:
                                base_qs = base_qs.filter(pk__in=list(all_pks)).distinct()
                            else:
                                base_qs = base_qs.none()
                        else:
                            if target_model_name == "Sample":
                                q_label |= Q(individual__cross_ids__id_value__icontains=own_search_term)
                            elif target_model_name == "Test":
                                q_label |= Q(sample__individual__cross_ids__id_value__icontains=own_search_term)
                            elif target_model_name == "Analysis":
                                q_label |= Q(test__sample__individual__cross_ids__id_value__icontains=own_search_term)
                            elif target_model_name == "Variant":
                                q_label |= Q(individual__cross_ids__id_value__icontains=own_search_term)
                                
                            base_qs = base_qs.filter(q_label).distinct()
                else:
                    # Fallback: OR over all CharField/TextField
                    text_fields = []
                    try:
                        for f in target_model._meta.get_fields():
                            internal = getattr(f, "get_internal_type", lambda: None)()
                            if internal in ("CharField", "TextField"):
                                text_fields.append(f.name)
                    except Exception:
                        text_fields = []
                    
                    # For Individual model, use encrypted field filtering for full_name
                    if target_model_name == "Individual":
                        # Separate encrypted and regular fields
                        encrypted_fields, regular_fields = _separate_encrypted_fields(target_model, text_fields)
                        
                        # Search regular fields
                        regular_pks = set()
                        if regular_fields:
                            qobj = Q()
                            for fname in regular_fields:
                                qobj |= Q(**{f"{fname}__icontains": own_search_term})
                            qobj |= Q(cross_ids__id_value__icontains=own_search_term)
                            regular_pks = set(base_qs.filter(qobj).values_list("pk", flat=True))
                        
                        # Search encrypted fields
                        encrypted_pks = set()
                        if encrypted_fields:
                            encrypted_queryset = _filter_encrypted_fields(
                                base_qs,
                                encrypted_fields,
                                [own_search_term],
                                exact_match=False,
                                exclude=False
                            )
                            encrypted_pks = set(encrypted_queryset.values_list("pk", flat=True))
                        
                        # Combine results
                        all_pks = regular_pks | encrypted_pks
                        if all_pks:
                            base_qs = base_qs.filter(pk__in=list(all_pks)).distinct()
                        else:
                            base_qs = base_qs.none()
                    else:
                        if text_fields:
                            qobj = Q()
                            for fname in text_fields:
                                qobj |= Q(**{f"{fname}__icontains": own_search_term})
                            
                            # Special handling for Individual: also search cross_ids
                            if target_model_name == "Sample":
                                qobj |= Q(individual__cross_ids__id_value__icontains=own_search_term)
                            elif target_model_name == "Test":
                                qobj |= Q(sample__individual__cross_ids__id_value__icontains=own_search_term)
                            elif target_model_name == "Analysis":
                                qobj |= Q(test__sample__individual__cross_ids__id_value__icontains=own_search_term)
                            elif target_model_name == "Variant":
                                qobj |= Q(individual__cross_ids__id_value__icontains=own_search_term)
                                
                            base_qs = base_qs.filter(qobj).distinct()
            except Exception as e:
                # If filtering fails, leave base_qs as-is
                import traceback
                print(f"Error in combobox search: {e}")
                print(traceback.format_exc())
                pass

        # Rebuild pagination after search filtering
        paginator = Paginator(base_qs, 12)
        paged_items = paginator.get_page(page)
        # Exclude already selected ids
        exclude_ids_raw = request.GET.get("exclude_ids", "")
        exclude_ids = []
        if exclude_ids_raw:
            try:
                exclude_ids = json.loads(exclude_ids_raw)
            except Exception:
                try:
                    exclude_ids = [
                        int(x) for x in exclude_ids_raw.split(",") if x.strip()
                    ]
                except Exception:
                    exclude_ids = []

        if exclude_ids:
            try:
                paged_items.object_list = paged_items.object_list.exclude(
                    pk__in=exclude_ids
                )
                # Recreate paginator for accurate counts if exclusion affected page
                paginator = Paginator(paged_items.object_list, 12)
                paged_items = paginator.get_page(page)
            except Exception:
                pass

        # Build option dicts for template rendering
        options = []
        try:
            for obj in paged_items.object_list:
                try:
                    value = (
                        getattr(obj, value_field)
                        if value_field and value_field != "pk"
                        else getattr(obj, "pk")
                    )
                except Exception:
                    value = getattr(obj, "pk")
                try:
                    label = getattr(obj, label_field) if label_field else str(obj)
                except Exception:
                    label = str(obj)
                options.append({"value": value, "label": str(label)})
        except Exception:
            # Fallback: simple string labels
            options = [
                {"value": getattr(obj, "pk"), "label": str(obj)}
                for obj in paged_items.object_list
            ]

        context = {
            "items": paged_items,
            "app_label": target_app_label,
            "model_name": target_model_name,
            "value_field": value_field,
            "label_field": label_field,
            "options": options,
            "sort_options": get_sort_options(target_model_name),
        }
        # Try model-specific combobox-options partial first, fall back to generic
        try:
            return render(
                request,
                f"{target_app_label}/{target_model_name.lower()}.html#combobox-options",
                context,
            )
        except TemplateDoesNotExist:
            return render(request, "lab/partials/partials.html#combobox-options", context)

    # Render description snippet for Family description autofill
    if request.GET.get("render") == "family_description" and target_model_name == "Family":
        search_value = request.GET.get("search", "").strip()
        family = None
        if search_value:
            # search_value may be family_id; try exact match first
            family = target_model.objects.filter(family_id=search_value).first()
            if not family:
                # fallback contains
                family = target_model.objects.filter(family_id__icontains=search_value).first()
        description = getattr(family, "description", "") if family else ""
        return render(
            request,
            "lab/partials/partials.html#family-description-field",
            {"description": description},
        )

    # Render prefilled individual forms for a selected Family
    if request.GET.get("render") == "family_individual_forms" and target_model_name == "Family":
        search_value = request.GET.get("search", "").strip()
        family = None
        if search_value:
            family = target_model.objects.filter(family_id=search_value).first()
            if not family:
                family = target_model.objects.filter(family_id__icontains=search_value).first()
        individuals = []
        prefills = []
        try:
            from django.contrib.contenttypes.models import ContentType as _CT
            indiv_ct = _CT.get_for_model(Individual)
            individual_statuses = Status.objects.filter(
                Q(content_type=indiv_ct) | Q(content_type__isnull=True)
            ).order_by("name")
        except Exception:
            individual_statuses = Status.objects.all().order_by("name")

        users = User.objects.all().order_by("username")
        task_statuses = Status.objects.filter(
            Q(content_type=ContentType.objects.get_for_model(Task))
            | Q(content_type__isnull=True)
        ).order_by("name")
        projects = Project.objects.all().order_by("name")
        identifier_types = IdentifierType.objects.all().order_by("name")

        if family:
            individuals = list(getattr(family, "individuals", Individual.objects.none()).all())
            # Build initial JSONs for comboboxes per individual
            import json as _json
            for ind in individuals:
                try:
                    inst_initial = [
                        {"value": str(i.pk), "label": getattr(i, "name", str(i))}
                        for i in getattr(ind, "institution", []).all()
                    ]
                except Exception:
                    inst_initial = []
                try:
                    hpo_initial = [
                        {"value": str(t.pk), "label": getattr(t, "label", str(t))}
                        for t in getattr(ind, "hpo_terms", []).all()
                    ]
                except Exception:
                    hpo_initial = []
                prefills.append(
                    {
                        "individual": ind,
                        "initial_institutions_json": _json.dumps(inst_initial),
                        "initial_hpo_json": _json.dumps(hpo_initial),
                    }
                )

        return render(
            request,
            "lab/crud.html#prefilled-individual-forms",
            {
                "prefills": prefills,
                "count": len(prefills),
                "identifier_types": identifier_types,
                "individual_statuses": individual_statuses,
                "users": users,
                "task_statuses": task_statuses,
                "projects": projects,
            },
        )

    context = {
        "items": paged_items,
        "num_items": num_items,
        "total_items": total_items,
        "search": own_search_term,
        "app_label": target_app_label,
        "model_name": target_model_name,
        "all_filters": {
            k: v for k, v in request.GET.items() if k.startswith("filter_")
        },
        "view_mode": view_mode,
        "card": card_partial,
        "icon_class": icon_class,
        "sort_options": get_sort_options(target_model_name),
    }
    
    # Add model-specific statuses to context for status badge dropdowns
    try:
        model_class = apps.get_model(app_label=target_app_label, model_name=target_model_name)
        if hasattr(model_class, 'status'):
            model_ct = ContentType.objects.get_for_model(model_class)
            statuses_var_name = f"{target_model_name.lower()}_statuses"
            context[statuses_var_name] = Status.objects.filter(
                Q(content_type=model_ct) | Q(content_type__isnull=True)
            ).order_by("name")
    except Exception:
        pass  # If model doesn't have status field, skip
    
    response = render(
        request,
        "lab/partials/partials.html#generic-search-results",
        context,
    )
    return response


@login_required
def generic_search_page(request):
    """
    This view ONLY handles infinite scroll pagination.
    It returns a simple list of items, not an OOB response.
    """
    target_app_label = request.GET.get("app_label", "lab").strip()
    target_model_name = request.GET.get("model_name", "").strip()
    if not target_model_name:
        return HttpResponseBadRequest("Model not specified.")

    target_model = apps.get_model(
        app_label=target_app_label, model_name=target_model_name
    )

    filtered_items = apply_filters(
        request, target_model_name, target_model.objects.all()
    )

    # Pagination
    page = request.GET.get("page")
    paginator = Paginator(filtered_items, 12)
    paged_items = paginator.get_page(page)

    card_partial = request.GET.get("card", "card")
    view_mode = request.GET.get("view_mode", "cards")
    # Combobox render mode (for Select2-like behavior)
    render_mode = request.GET.get("render")
    if render_mode == "combobox":
        # Exclude already selected ids
        exclude_ids_raw = request.GET.get("exclude_ids", "")
        exclude_ids = []
        if exclude_ids_raw:
            try:
                exclude_ids = json.loads(exclude_ids_raw)
            except Exception:
                try:
                    exclude_ids = [
                        int(x) for x in exclude_ids_raw.split(",") if x.strip()
                    ]
                except Exception:
                    exclude_ids = []

        if exclude_ids:
            try:
                paged_items.object_list = paged_items.object_list.exclude(
                    pk__in=exclude_ids
                )
                paginator = Paginator(paged_items.object_list, 12)
                paged_items = paginator.get_page(page)
            except Exception:
                pass

        value_field = request.GET.get("value_field", "pk")
        label_field = request.GET.get("label_field")

        # Build option dicts for template rendering
        options = []
        try:
            for obj in paged_items.object_list:
                try:
                    value = (
                        getattr(obj, value_field)
                        if value_field and value_field != "pk"
                        else getattr(obj, "pk")
                    )
                except Exception:
                    value = getattr(obj, "pk")
                try:
                    label = getattr(obj, label_field) if label_field else str(obj)
                except Exception:
                    label = str(obj)
                options.append({"value": value, "label": str(label)})
        except Exception:
            # Fallback: simple string labels
            options = [
                {"value": getattr(obj, "pk"), "label": str(obj)}
                for obj in paged_items.object_list
            ]

        context = {
            "items": paged_items,
            "model_name": target_model_name,
            "app_label": target_app_label,
            "value_field": value_field,
            "label_field": label_field,
            "options": options,
        }
        try:
            return render(
                request,
                f"{target_app_label}/{target_model_name.lower()}.html#combobox-options",
                context,
            )
        except TemplateDoesNotExist:
            return render(request, "lab/partials/partials.html#combobox-options", context)

    context = {
        "items": paged_items,
        "model_name": target_model_name,
        "app_label": target_app_label,
        "all_filters": {
            k: v for k, v in request.GET.items() if k.startswith("filter_")
        },
        "view_mode": view_mode,
        "card": card_partial,
    }
    
    # Add model-specific statuses to context for status badge dropdowns
    try:
        model_class = apps.get_model(app_label=target_app_label, model_name=target_model_name)
        if hasattr(model_class, 'status'):
            model_ct = ContentType.objects.get_for_model(model_class)
            statuses_var_name = f"{target_model_name.lower()}_statuses"
            context[statuses_var_name] = Status.objects.filter(
                Q(content_type=model_ct) | Q(content_type__isnull=True)
            ).order_by("name")
    except Exception:
        pass  # If model doesn't have status field, skip
    
    return render(request, "lab/partials/_infinite_scroll_items.html", context)


@login_required
@vary_on_headers("HX-Request")
def generic_detail(request):
    target_app_label = request.GET.get("app_label", "lab").strip()
    target_model_name = request.GET.get("model_name", "").strip()
    pk = request.GET.get("pk")
    if not target_model_name or not pk:
        return HttpResponseBadRequest("Model or pk not specified.")

    target_model = apps.get_model(
        app_label=target_app_label, model_name=target_model_name
    )

    obj = get_object_or_404(target_model, pk=pk)

    if target_app_label == "variant":
        template_base = "variant/variant.html"
    else:
        template_base = f"{target_app_label}/{target_model_name.lower()}.html"
    context = {
        "item": obj,
        "model_name": target_model_name,
        "app_label": target_app_label,
        "user": request.user,
    }

    requested_tab = request.GET.get("activeTab")
    normalized_tab = None
    if requested_tab:
        normalized_tab = "history" if requested_tab == "status" else requested_tab
        context["activeTab"] = normalized_tab

    history_prefetched = normalized_tab == "history"
    context["history_prefetched"] = history_prefetched

    def _add_statuses_for_models(context, model_classes):
        """Attach status querysets for each provided model class if not already present."""
        for model_class in model_classes:
            try:
                key = f"{model_class.__name__.lower()}_statuses"
                if key in context:
                    continue
                model_ct = ContentType.objects.get_for_model(model_class)
                context[key] = Status.objects.filter(
                    Q(content_type=model_ct) | Q(content_type__isnull=True)
                ).order_by("name")
            except Exception:
                # If a model lacks a status relationship, skip silently.
                continue

    if target_model_name == "Individual":
        context["tests"] = [
            test for sample in obj.samples.all() for test in sample.tests.all()
        ]
        context["analyses"] = [
            analysis for test in context["tests"] for analysis in test.analyses.all()
        ]
        # Build initial JSON for HPO terms combobox
        try:
            hpo_initial = [
                {"value": str(t.pk), "label": getattr(t, "label", str(t))}
                for t in getattr(obj, "hpo_terms", []).all()
            ]
            context["hpo_initial_json"] = json.dumps(hpo_initial)
        except Exception:
            context["hpo_initial_json"] = "[]"
        # Get all available Individual statuses for status dropdown
        individual_ct = ContentType.objects.get_for_model(Individual)
        context["individual_statuses"] = Status.objects.filter(
            Q(content_type=individual_ct) | Q(content_type__isnull=True)
        ).order_by("name")
        _add_statuses_for_models(
            context, [Sample, Test, Analysis, Project, Task]
        )
    elif target_model_name == "Sample":
        context["analyses"] = [
            analysis for test in obj.tests.all() for analysis in test.analyses.all()
        ]
        # Get all available Sample statuses for status dropdown
        sample_ct = ContentType.objects.get_for_model(Sample)
        context["sample_statuses"] = Status.objects.filter(
            Q(content_type=sample_ct) | Q(content_type__isnull=True)
        ).order_by("name")
        _add_statuses_for_models(context, [Test, Analysis, Task])
    
    # Add statuses for any model that has a status field
    if hasattr(target_model, 'status'):
        model_ct = ContentType.objects.get_for_model(target_model)
        statuses_var_name = f"{target_model_name.lower()}_statuses"
        if statuses_var_name not in context:  # Only add if not already added above
            context[statuses_var_name] = Status.objects.filter(
                Q(content_type=model_ct) | Q(content_type__isnull=True)
            ).order_by("name")

    # Ensure related cards rendered in detail views have status choices available
    related_status_models = []
    if target_model_name == "Test":
        related_status_models = [Analysis, Task]
    elif target_model_name == "Analysis":
        related_status_models = [Task]
    elif target_model_name == "Project":
        related_status_models = [Individual, Task]

    if related_status_models:
        _add_statuses_for_models(context, related_status_models)

    if request.htmx:
        # For HTMX requests, return only the detail partial
        return render(request, f"{template_base}#detail", context)
    else:
        # For direct loads, render the main index page and inject the detail content
        detail_html = render_to_string(
            f"{template_base}#detail", context=context, request=request
        )
        return render(
            request,
            "lab/index.html",
            {
                "initial_detail_html": detail_html,
                "item": obj,
                "model_name": target_model_name,
                "app_label": target_app_label,
            },
        )

@login_required
@vary_on_headers("HX-Request")
def generic_detail(request):
    target_app_label = request.GET.get("app_label", "lab").strip()
    target_model_name = request.GET.get("model_name", "").strip()
    pk = request.GET.get("pk")
    if not target_model_name or not pk:
        return HttpResponseBadRequest("Model or pk not specified.")

    target_model = apps.get_model(
        app_label=target_app_label, model_name=target_model_name
    )

    obj = get_object_or_404(target_model, pk=pk)

    if target_app_label == "variant":
        template_base = "variant/variant.html"
    else:
        template_base = f"{target_app_label}/{target_model_name.lower()}.html"
    context = {
        "item": obj,
        "model_name": target_model_name,
        "app_label": target_app_label,
        "user": request.user,
    }

    requested_tab = request.GET.get("activeTab")
    normalized_tab = None
    if requested_tab:
        normalized_tab = "history" if requested_tab == "status" else requested_tab
        context["activeTab"] = normalized_tab

    history_prefetched = normalized_tab == "history"
    context["history_prefetched"] = history_prefetched

    def _add_statuses_for_models(context, model_classes):
        """Attach status querysets for each provided model class if not already present."""
        for model_class in model_classes:
            try:
                key = f"{model_class.__name__.lower()}_statuses"
                if key in context:
                    continue
                model_ct = ContentType.objects.get_for_model(model_class)
                context[key] = Status.objects.filter(
                    Q(content_type=model_ct) | Q(content_type__isnull=True)
                ).order_by("name")
            except Exception:
                # If a model lacks a status relationship, skip silently.
                continue

    if target_model_name == "Individual":
        context["tests"] = [
            test for sample in obj.samples.all() for test in sample.tests.all()
        ]
        context["analyses"] = [
            analysis for test in context["tests"] for analysis in test.analyses.all()
        ]
        # Build initial JSON for HPO terms combobox
        try:
            hpo_initial = [
                {"value": str(t.pk), "label": getattr(t, "label", str(t))}
                for t in getattr(obj, "hpo_terms", []).all()
            ]
            context["hpo_initial_json"] = json.dumps(hpo_initial)
        except Exception:
            context["hpo_initial_json"] = "[]"
        # Get all available Individual statuses for status dropdown
        individual_ct = ContentType.objects.get_for_model(Individual)
        context["individual_statuses"] = Status.objects.filter(
            Q(content_type=individual_ct) | Q(content_type__isnull=True)
        ).order_by("name")
        _add_statuses_for_models(
            context, [Sample, Test, Analysis, Project, Task]
        )
    elif target_model_name == "Sample":
        context["analyses"] = [
            analysis for test in obj.tests.all() for analysis in test.analyses.all()
        ]
        # Get all available Sample statuses for status dropdown
        sample_ct = ContentType.objects.get_for_model(Sample)
        context["sample_statuses"] = Status.objects.filter(
            Q(content_type=sample_ct) | Q(content_type__isnull=True)
        ).order_by("name")
        _add_statuses_for_models(context, [Test, Analysis, Task])
    
    # Add statuses for any model that has a status field
    if hasattr(target_model, 'status'):
        model_ct = ContentType.objects.get_for_model(target_model)
        statuses_var_name = f"{target_model_name.lower()}_statuses"
        if statuses_var_name not in context:  # Only add if not already added above
            context[statuses_var_name] = Status.objects.filter(
                Q(content_type=model_ct) | Q(content_type__isnull=True)
            ).order_by("name")

    # Ensure related cards rendered in detail views have status choices available
    related_status_models = []
    if target_model_name == "Test":
        related_status_models = [Analysis, Task]
    elif target_model_name == "Analysis":
        related_status_models = [Task]
    elif target_model_name == "Project":
        related_status_models = [Individual, Task]

    if related_status_models:
        _add_statuses_for_models(context, related_status_models)

    if request.htmx:
        # For HTMX requests, return only the detail partial
        return render(request, f"{template_base}#detail", context)
    else:
        # For direct loads, render the main index page and inject the detail content
        detail_html = render_to_string(
            f"{template_base}#detail", context=context, request=request
        )
        return render(
            request,
            "lab/index.html",
            {
                "initial_detail_html": detail_html,
                "item": obj,
                "model_name": target_model_name,
                "app_label": target_app_label,
            },
        )


@login_required
@require_GET
def history_tab(request):
    target_app_label = request.GET.get("app_label", "lab").strip()
    target_model_name = request.GET.get("model_name", "").strip()
    pk = request.GET.get("pk")

    if not target_model_name or not pk:
        return HttpResponseBadRequest("Model or pk not specified.")

    target_model = apps.get_model(
        app_label=target_app_label, model_name=target_model_name
    )
    obj = get_object_or_404(target_model, pk=pk)

    # Collect history from the main object
    history_records = []
    if hasattr(obj, "history"):
        for record in obj.history.all():
            record.model_name = target_model_name
            history_records.append(record)

    # Collect history from related objects if it's a Variant
    if target_model_name == "Variant":
        # Annotations
        for annotation in obj.annotations.all():
            if hasattr(annotation, "history"):
                for record in annotation.history.all():
                    record.model_name = "Annotation"
                    history_records.append(record)
        
        # Classifications
        for classification in obj.classifications.all():
            if hasattr(classification, "history"):
                for record in classification.history.all():
                    record.model_name = "Classification"
                    history_records.append(record)

    # Sort by history_date descending
    history_records.sort(key=lambda x: x.history_date, reverse=True)

    # Calculate diffs for updates
    for record in history_records:
        if record.history_type == "~" and record.prev_record:
            record.delta = record.diff_against(record.prev_record)

    template_base = f"{target_app_label}/{target_model_name.lower()}.html"
    context = {
        "item": obj,
        "history_records": history_records,
        "model_name": target_model_name,
        "app_label": target_app_label,
        "user": request.user,
        "history_prefetched": True,
    }

    return render(request, f"{template_base}#history-tab", context)


@login_required
@require_POST
def update_status(request):
    """Generic view to update the status of any model."""
    model_name = request.POST.get("model_name")
    app_label = request.POST.get("app_label", "lab")
    object_id = request.POST.get("object_id")
    status_id = request.POST.get("status_id")
    
    if not all([model_name, object_id, status_id]):
        return HttpResponseBadRequest("model_name, object_id, and status_id are required.")
    
    try:
        # Get the model class
        model_class = apps.get_model(app_label=app_label, model_name=model_name)
        obj = get_object_or_404(model_class, pk=object_id)
        perm_name = f"{model_class._meta.app_label}.change_{model_class._meta.model_name}"
        if not request.user.has_perm(perm_name):
            return HttpResponseForbidden(
                "You do not have permission to modify this object."
            )
        
        # Get model content type to filter statuses
        model_ct = ContentType.objects.get_for_model(model_class)
        
        # Verify the status is valid for this model
        status = Status.objects.filter(
            Q(content_type=model_ct) | Q(content_type__isnull=True),
            pk=status_id
        ).first()
        
        if not status:
            return HttpResponseBadRequest(f"Invalid status for {model_name}.")
        
        # Update the status
        old_status = obj.status
        obj.status = status
        obj.save()

        # Send notification if status changed
        if old_status != status:
            from .services import send_notification
            
            # Notify the creator of the object
            if hasattr(obj, "created_by") and obj.created_by != request.user:
                send_notification(
                    sender=request.user,
                    recipient=obj.created_by,
                    verb="Status Change",
                    description=f"Status of {model_name} '{obj}' changed from '{old_status}' to '{status}'",
                    target=obj,
                )
            
            # Notify assigned user if applicable (e.g. for Task)
            if hasattr(obj, "assigned_to") and obj.assigned_to and obj.assigned_to != request.user:
                send_notification(
                    sender=request.user,
                    recipient=obj.assigned_to,
                    verb="Status Change",
                    description=f"Status of {model_name} '{obj}' changed from '{old_status}' to '{status}'",
                    target=obj,
                )
        
        # Refresh the object from database to ensure we have latest data
        obj.refresh_from_db()
        
        # If htmx request, return the updated status badge and refresh the card/detail
        if request.htmx:
            # Get available statuses for the dropdown
            available_statuses = Status.objects.filter(
                Q(content_type=model_ct) | Q(content_type__isnull=True)
            ).order_by("name")
            
            # Determine which partial to return based on view parameter
            view_type = request.POST.get("view", "card")  # Default to card for list views
            template_name = f"{app_label}/{model_name.lower()}.html"
            
            if view_type == "detail":
                partial_name = "status-badge"
            else:
                partial_name = "status-badge-card"
            
            # Context variable name for statuses (e.g., individual_statuses, sample_statuses)
            statuses_var_name = f"{model_name.lower()}_statuses"
            
            # Build context similar to generic_detail to ensure all related data is included
            context = {
                "item": obj,
                statuses_var_name: available_statuses,
                "model_name": model_name,
                "app_label": app_label,
                "user": request.user,
            }
            
            # Add model-specific context (same as generic_detail)
            if model_name == "Individual":
                context["tests"] = [
                    test for sample in obj.samples.all() for test in sample.tests.all()
                ]
                context["analyses"] = [
                    analysis for test in context["tests"] for analysis in test.analyses.all()
                ]
                # Build initial JSON for HPO terms combobox
                try:
                    hpo_initial = [
                        {"value": str(t.pk), "label": getattr(t, "label", str(t))}
                        for t in getattr(obj, "hpo_terms", []).all()
                    ]
                    context["hpo_initial_json"] = json.dumps(hpo_initial)
                except Exception:
                    context["hpo_initial_json"] = "[]"
            elif model_name == "Sample":
                context["analyses"] = [
                    analysis for test in obj.tests.all() for analysis in test.analyses.all()
                ]
            
            # Get the target element ID from the request
            target_id = request.POST.get("target_id")
            if not target_id:
                # Default target based on view type
                if view_type == "detail":
                    target_id = "status-badge-container"
                else:
                    target_id = f"status-badge-container-{obj.id}"
            
            # Render the status badge partial
            badge_html = render_to_string(
                f"{template_name}#{partial_name}",
                context=context,
                request=request
            )
            
            # Also refresh the card/detail view
            refresh_card = request.POST.get("refresh_card", "true").lower() == "true"
            refresh_detail = request.POST.get("refresh_detail", "false").lower() == "true"
            
            response = HttpResponse()
            
            # Add the status badge update
            response.write(badge_html)
            
            # Add card refresh if requested and in card view
            if refresh_card and view_type != "detail":
                card_partial = request.POST.get("card", "card")
                card_html = render_to_string(
                    f"{template_name}#{card_partial}",
                    context=context,
                    request=request
                )
                # Cards are wrapped in divs with IDs like "card-wrapper-{id}" in infinite scroll
                # Target the wrapper div for OOB swap - need to wrap card_html in the wrapper div
                card_wrapper_id = f"card-wrapper-{obj.id}"
                card_wrapper_html = f'<div id="{card_wrapper_id}" hx-swap-oob="outerHTML">{card_html}</div>'
                response.write(card_wrapper_html)
            
            # Add detail refresh if requested
            if refresh_detail or view_type == "detail":
                detail_html = render_to_string(
                    f"{template_name}#detail",
                    context=context,
                    request=request
                )
                detail_target_id = request.POST.get("detail_target_id", f"{model_name.lower()}-detail")
                response.write(f'<div id="{detail_target_id}" hx-swap-oob="outerHTML">{detail_html}</div>')
            
            # Trigger event to refresh other UI components
            response["HX-Trigger"] = json.dumps({
                "status-updated": {
                    "model_name": model_name,
                    "object_id": obj.id,
                    "status_id": status.id,
                    "status_name": status.name,
                }
            })
            return response
        else:
            return JsonResponse({
                "success": True,
                "old_status": old_status.name,
                "new_status": status.name,
            })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return HttpResponseBadRequest(f"Error updating status: {str(e)}")


@login_required
@require_POST
def update_individual_status(request):
    """Update the status of an Individual (kept for backward compatibility)."""
    # Redirect to generic update_status
    request.POST = request.POST.copy()
    request.POST['model_name'] = 'Individual'
    request.POST['object_id'] = request.POST.get('individual_id')
    return update_status(request)


@login_required
def hpo_network_visualization(request):
    initial_queryset = Individual.objects.all()
    filtered_individuals = apply_filters(request, "Individual", initial_queryset)
    threshold = request.GET.get("threshold", 12)
    if threshold:
        threshold = int(threshold)
    else:
        threshold = 12
    consolidated_counts, graph, hpo = process_hpo_data(
        filtered_individuals, threshold=threshold
    )
    elements, _ = cytoscape_hpo_network(graph, hpo, consolidated_counts, min_count=1)
    elements_json = cytoscape_elements_json(elements)
    return render(
        request,
        "lab/plots.html#hpo-network-visualization",
        {
            "elements_json": elements_json,
            "threshold": threshold,
            "term_count": len(consolidated_counts),
            "individuals": filtered_individuals,
            "individual_count": len(filtered_individuals),
        },
    )


@login_required
def get_select_options(request):
    model_name = request.GET.get("model_name")
    field_name = request.GET.get("field_name")
    selected_value = request.GET.get("selected_value")

    # Handle multiple selected values - if it's a JSON array, parse it
    if (
        selected_value
        and selected_value.startswith("[")
        and selected_value.endswith("]")
    ):
        try:
            import json

            selected_value = json.loads(selected_value)
        except json.JSONDecodeError:
            selected_value = [selected_value]
    elif selected_value:
        # Single value - convert to list for consistency
        selected_value = [selected_value]
    else:
        selected_value = []

    config = FILTER_CONFIG.get(model_name, {})
    if not config:
        return HttpResponseBadRequest("Model not configured.")

    select_config = config.get("select_fields", {}).get(field_name, {})
    field_path = select_config.get("field_path")
    select_filter_path = select_config.get("select_filter_path", field_path)

    model_class = apps.get_model(
        app_label=config.get("app_label"), model_name=model_name
    )
    if not all([field_name, model_class, select_filter_path]):
        return HttpResponseBadRequest("Invalid request for select options.")

    # Apply all filters *except* the one we are fetching options for
    filtered_qs = apply_filters(
        request, model_name, model_class.objects.all(), exclude_filter=field_name
    )
    options = (
        filtered_qs.order_by(select_filter_path)
        .values_list(select_filter_path, flat=True)
        .filter(**{f"{select_filter_path}__isnull": False})
        .distinct()
    )

    return render(
        request,
        "lab/partials.html#select-options",
        {
            "options": list(options),
            "label": select_config.get("label", ""),
            "selected_value": selected_value,
        },
    )


@login_required
def get_objects_by_content_type(request):
    """Get objects of a specific model type for task association"""
    # Try both parameter names (content_type_id from hx-vals, content_type from hx-include)
    content_type_id = request.GET.get("content_type_id") or request.GET.get("content_type")
    
    if not content_type_id:
        return HttpResponse('<div class="text-gray-500 text-sm p-2">Select a type first</div>')
    
    try:
        content_type = ContentType.objects.get(pk=content_type_id)
        model_class = content_type.model_class()
        
        # Determine app_label and model_name for the partial
        app_label = model_class._meta.app_label
        model_name = model_class._meta.model_name

        # Optional: preselect an existing object (used when editing a Task)
        selected_object_id = request.GET.get("object_id")
        initial = ""
        initial_value = ""
        if selected_object_id:
            try:
                obj = model_class.objects.get(pk=selected_object_id)
                initial = str(obj)
                initial_value = str(obj.pk)
            except Exception:
                # If lookup fails, fall back to no initial
                initial = ""
                initial_value = ""
        
        # Render the single generic combobox partial
        # We need to pass the correct context for the combobox controller
        context = {
            "app_label": app_label,
            "model_name": model_class.__name__, # Use class name for display/logic
            "value_field": "pk",
            "name": "object_id",
            "icon_class": "fa-magnifying-glass",
            "initial": initial,
            "initial_value": initial_value,
        }
        
        return render(request, "lab/partials/partials.html#single-generic-combobox", context)
        
    except Exception as e:
        return HttpResponse(f'<div class="text-red-500 text-sm p-2">Error loading objects: {str(e)}</div>')


@login_required
def get_status_buttons(request):
    """Get status buttons for a specific model"""
    model_name = request.GET.get("model_name")
    app_label = request.GET.get("app_label", "lab")
    selected_statuses = request.GET.get("selected_statuses")

    # Handle multiple selected statuses - if it's a JSON array, parse it
    if (
        selected_statuses
        and selected_statuses.startswith("[")
        and selected_statuses.endswith("]")
    ):
        try:
            import json

            selected_statuses = json.loads(selected_statuses)
        except json.JSONDecodeError:
            selected_statuses = [selected_statuses]
    elif selected_statuses:
        # Single value - convert to list for consistency
        selected_statuses = [selected_statuses]
    else:
        selected_statuses = []

    if not model_name:
        return HttpResponseBadRequest("Model not specified.")

    # Get available statuses for this model
    statuses = get_available_statuses(model_name, app_label)

    return render(
        request,
        "lab/partials/partials.html#status-buttons",
        {
            "statuses": statuses,
            "selected_statuses": selected_statuses,
            "model_name": model_name,
        },
    )


@login_required
def get_type_buttons(request):
    """Get type buttons for a specific model"""
    model_name = request.GET.get("model_name")
    app_label = request.GET.get("app_label", "lab")

    if not model_name:
        return HttpResponseBadRequest("Model not specified.")

    # Get available types for this model
    types = get_available_types(model_name, app_label)

    return render(
        request,
        "lab/partials/partials.html#type-buttons",
        {
            "types": types,
            "model_name": model_name,
        },
    )


@login_required
def project_add_individuals(request, pk=None):
    """Add one or more Individuals to a Project via HTMX.

    Expects POST with 'individual_ids' as JSON list string or comma-separated string.
    Returns updated Individuals tab content fragment.
    """
    # Determine target project by URL pk or posted project_id
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    project_id = pk or request.POST.get("project_id")
    # Handle JSON array input from combobox hidden input
    if isinstance(project_id, str) and project_id.startswith("[") and project_id.endswith("]"):
        try:
            import json as _json
            arr = _json.loads(project_id)
            if isinstance(arr, list) and arr:
                project_id = arr[0]
        except Exception:
            pass
    if not project_id:
        return HttpResponseBadRequest("project_id not specified")
    project = get_object_or_404(Project, pk=project_id)

    ids_raw = request.POST.get("individual_ids", "")
    individual_ids = []
    if ids_raw:
        try:
            import json

            parsed = json.loads(ids_raw)
            if isinstance(parsed, list):
                individual_ids = [int(x) for x in parsed if str(x).isdigit()]
        except Exception:
            # Fallback: comma-separated
            individual_ids = [int(x) for x in ids_raw.split(",") if x.strip().isdigit()]

    if not individual_ids:
        # Support single individual via 'individual_id'
        single_id = request.POST.get("individual_id")
        if single_id and str(single_id).isdigit():
            individual_ids = [int(single_id)]

    if individual_ids:
        qs = Individual.objects.filter(pk__in=individual_ids)
        project.individuals.add(*qs)

    # Decide which fragment to return
    return_context = request.POST.get("return") or request.POST.get("return_context")
    if return_context == "individual":
        # Need an individual to refresh; prefer explicit individual_id
        ind_id = request.POST.get("individual_id")
        if not ind_id and individual_ids:
            ind_id = individual_ids[0]
        individual = get_object_or_404(Individual, pk=ind_id)
        return render(
            request,
            "lab/individual.html#individual-projects-fragment",
            {"item": individual},
        )
    if request.htmx:
        # Return refreshed project individuals fragment so the tab updates without a full reload
        return render(
            request,
            "lab/project.html#project-individuals-fragment",
            {"item": project, "user": request.user},
        )

    redirect_url = request.META.get("HTTP_REFERER") or reverse("lab:home")
    return redirect(redirect_url)


@login_required
def project_remove_individuals(request, pk=None):
    """Remove one or more Individuals from a Project via HTMX.

    Expects POST with 'individual_ids' as JSON list string or comma-separated string.
    Returns updated Individuals tab content fragment.
    """
    # Determine target project by URL pk or posted project_id
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    project_id = pk or request.POST.get("project_id")
    # Handle JSON array input from combobox hidden input
    if isinstance(project_id, str) and project_id.startswith("[") and project_id.endswith("]"):
        try:
            import json as _json
            arr = _json.loads(project_id)
            if isinstance(arr, list) and arr:
                project_id = arr[0]
        except Exception:
            pass
    if not project_id:
        return HttpResponseBadRequest("project_id not specified")
    project = get_object_or_404(Project, pk=project_id)

    ids_raw = request.POST.get("individual_ids", "")
    individual_ids = []
    if ids_raw:
        try:
            import json

            parsed = json.loads(ids_raw)
            if isinstance(parsed, list):
                individual_ids = [int(x) for x in parsed if str(x).isdigit()]
        except Exception:
            # Fallback: comma-separated
            individual_ids = [int(x) for x in ids_raw.split(",") if x.strip().isdigit()]

    if not individual_ids:
        # Support single individual via 'individual_id'
        single_id = request.POST.get("individual_id")
        if single_id and str(single_id).isdigit():
            individual_ids = [int(single_id)]

    if individual_ids:
        qs = Individual.objects.filter(pk__in=individual_ids)
        project.individuals.remove(*qs)

    # Decide which fragment to return
    return_context = request.POST.get("return") or request.POST.get("return_context")
    if return_context == "individual":
        # Need an individual to refresh; prefer explicit individual_id
        ind_id = request.POST.get("individual_id")
        if not ind_id and individual_ids:
            ind_id = individual_ids[0]
        individual = get_object_or_404(Individual, pk=ind_id)
        return render(
            request,
            "lab/individual.html#individual-projects-fragment",
            {"item": individual},
        )
    if request.htmx:
        # Return refreshed project individuals fragment so the tab updates without a full reload
        return render(
            request,
            "lab/project.html#project-individuals-fragment",
            {"item": project, "user": request.user},
        )

    redirect_url = request.META.get("HTTP_REFERER") or reverse("lab:home")
    return redirect(redirect_url)


@login_required
def note_create(request):
    """Create a new note for a specific object"""
    if request.method == "POST":
        content_type_str = request.POST.get("content_type")
        object_id = request.POST.get("object_id")
        app_label = request.POST.get("app_label", "lab")

        # Get the content type and object
        model = apps.get_model(app_label, content_type_str)
        content_type = ContentType.objects.get_for_model(model)
        obj = model.objects.get(id=object_id)

        # Create the note
        is_private = request.POST.get("private") in ["1", "true", "on", "True"]
        Note.objects.create(
            content=request.POST.get("content"),
            user=request.user,
            private_owner=request.user if is_private else None,
            content_type=content_type,
            object_id=object_id,
        )

        # Return the updated list and trigger a note count update event
        response = TemplateResponse(
            request,
            "lab/note.html#list",
            {
                "object": obj,
                "content_type": content_type_str,
                "app_label": app_label,
                "user": request.user,
            },
        )
        try:
            response["HX-Trigger"] = f"noteCountUpdate-{content_type_str}-{object_id}"
        except Exception:
            pass
        return response

    # For GET requests, return the form
    content_type_str = request.GET.get("content_type")
    object_id = request.GET.get("object_id")
    app_label = request.GET.get("app_label", "lab")

    # Get the content type and object
    model = apps.get_model(app_label, content_type_str)
    content_type = ContentType.objects.get_for_model(model)
    obj = model.objects.get(id=object_id)

    return TemplateResponse(
        request,
        "lab/note.html#form",
        {
            "object": obj,
            "content_type": content_type_str,
            "app_label": app_label,
            "form": NoteForm(),
        },
    )


@login_required
def note_delete(request, pk):
    if request.method == "DELETE":
        note = get_object_or_404(Note, id=pk)

        # Get the object and content type before deleting the note
        obj = note.content_object
        content_type_str = note.content_type.model
        object_id = note.object_id

        # Only allow the note creator or staff to delete
        if request.user == note.user or request.user.is_staff:
            note.delete()

            response = render(
                request,
                "lab/note.html#list",
                {
                    "object": obj,
                    "content_type": content_type_str,
                    "user": request.user,
                },
            )
            response["HX-Trigger"] = f"noteCountUpdate-{content_type_str}-{object_id}"
            return response

        return HttpResponseForbidden()


@login_required
def note_update(request, pk):
    """Update an existing note"""
    if request.method == "POST":
        note = get_object_or_404(Note, id=pk)

        # Only allow the note creator or staff to edit
        if request.user == note.user or request.user.is_staff:
            note.content = request.POST.get("content")
            note.save()

            # Get the object and content type for the response
            obj = note.content_object
            content_type_str = note.content_type.model
            object_id = note.object_id

            response = render(
                request,
                "lab/note.html#list",
                {
                    "object": obj,
                    "content_type": content_type_str,
                    "user": request.user,
                },
            )
            response["HX-Trigger"] = f"noteCountUpdate-{content_type_str}-{object_id}"
            return response

        return HttpResponseForbidden()


@login_required
def note_count(request):
    if request.method == "GET":
        object_id = request.GET.get("object_id")
        content_type_str = request.GET.get("content_type")

        # Get the content type and object
        model = apps.get_model("lab", content_type_str.capitalize())
        obj = model.objects.get(id=object_id)

        return render(
            request,
            "lab/note.html#summary",
            context={
                "object": obj,
                "content_type": content_type_str,
                "user": request.user,
            },
        )


@login_required
def note_list(request):
    if request.method == "POST":
        object_id = request.POST.get("object_id")
        content_type_str = request.POST.get("content_type")

        # Get the content type and object
        model = apps.get_model("lab", content_type_str.capitalize())
        obj = model.objects.get(id=object_id)

        return render(
            request,
            "lab/note.html#list",
            context={
                "object": obj,
                "content_type": content_type_str,
                "user": request.user,
            },
        )


@login_required
def check_notifications(request):
    """Check if the current user has any unread notifications"""
    try:
        from notifications.models import Notification

        unread_count = Notification.objects.filter(
            recipient=request.user, unread=True
        ).count()
        return JsonResponse(
            {"has_unread": unread_count > 0, "unread_count": unread_count}
        )
    except ImportError:
        # If notifications app is not available, return no unread notifications
        return JsonResponse({"has_unread": False, "unread_count": 0})


@login_required
def notifications_page(request):
    """Display notifications page"""
    try:
        from notifications.models import Notification
        from django.db.models import Exists, OuterRef, Q
        from django.core.paginator import Paginator
        from collections import defaultdict

        from .models import Note, Task, Project, Individual, Sample, Test, Analysis
        from variant.models import Variant
        from django.contrib.contenttypes.models import ContentType

        scope = request.GET.get("scope", "all")

        notifications_qs = Notification.objects.filter(
            recipient=request.user
        ).order_by("-timestamp")

        if scope == "associated":
            # Collect direct notes and tasks by the user
            notes_qs = Note.objects.filter(user=request.user)
            tasks_qs = Task.objects.filter(
                Q(assigned_to=request.user) | Q(created_by=request.user)
            )

            ct_map = {
                "project": ContentType.objects.get_for_model(Project),
                "individual": ContentType.objects.get_for_model(Individual),
                "sample": ContentType.objects.get_for_model(Sample),
                "test": ContentType.objects.get_for_model(Test),
                "analysis": ContentType.objects.get_for_model(Analysis),
                "variant": ContentType.objects.get_for_model(Variant),
            }

            # Direct note targets
            note_targets = defaultdict(set)
            for row in notes_qs.values("content_type_id", "object_id"):
                note_targets[row["content_type_id"]].add(row["object_id"])

            # Direct task targets
            task_targets = defaultdict(set)
            for row in tasks_qs.values("content_type_id", "object_id"):
                task_targets[row["content_type_id"]].add(row["object_id"])

            # Prepare sets for each model and grow them via hierarchy traversal
            project_ids = set(task_targets[ct_map["project"].id])
            individual_ids = set(task_targets[ct_map["individual"].id])
            sample_ids = set(task_targets[ct_map["sample"].id])
            test_ids = set(task_targets[ct_map["test"].id])
            analysis_ids = set(task_targets[ct_map["analysis"].id])
            variant_ids = set(task_targets[ct_map["variant"].id])

            def add_ids(target_set, iterable):
                before = len(target_set)
                target_set.update([i for i in iterable if i is not None])
                return len(target_set) != before

            changed = True
            while changed:
                changed = False

                # Project -> Individuals
                if project_ids:
                    changed |= add_ids(
                        individual_ids,
                        Project.objects.filter(id__in=project_ids)
                        .values_list("individuals__id", flat=True)
                    )

                # Individuals -> Projects
                if individual_ids:
                    changed |= add_ids(
                        project_ids,
                        Project.objects.filter(individuals__id__in=individual_ids)
                        .values_list("id", flat=True)
                    )

                # Individuals -> Samples / Tests / Analyses / Variants
                if individual_ids:
                    changed |= add_ids(
                        sample_ids,
                        Sample.objects.filter(individual_id__in=individual_ids)
                        .values_list("id", flat=True)
                    )
                    changed |= add_ids(
                        test_ids,
                        Test.objects.filter(sample__individual_id__in=individual_ids)
                        .values_list("id", flat=True)
                    )
                    changed |= add_ids(
                        analysis_ids,
                        Analysis.objects.filter(test__sample__individual_id__in=individual_ids)
                        .values_list("id", flat=True)
                    )
                    changed |= add_ids(
                        variant_ids,
                        Variant.objects.filter(
                            Q(individual_id__in=individual_ids)
                            | Q(analysis__test__sample__individual_id__in=individual_ids)
                        ).values_list("id", flat=True)
                    )

                # Samples -> Individual / Tests / Analyses / Variants
                if sample_ids:
                    changed |= add_ids(
                        individual_ids,
                        Sample.objects.filter(id__in=sample_ids)
                        .values_list("individual_id", flat=True)
                    )
                    changed |= add_ids(
                        test_ids,
                        Test.objects.filter(sample_id__in=sample_ids)
                        .values_list("id", flat=True)
                    )
                    changed |= add_ids(
                        analysis_ids,
                        Analysis.objects.filter(test__sample_id__in=sample_ids)
                        .values_list("id", flat=True)
                    )
                    changed |= add_ids(
                        variant_ids,
                        Variant.objects.filter(
                            Q(analysis__test__sample_id__in=sample_ids)
                            | Q(individual__samples__id__in=sample_ids)
                        )
                        .values_list("id", flat=True)
                    )

                # Tests -> Sample / Individual / Analyses / Variants
                if test_ids:
                    changed |= add_ids(
                        sample_ids,
                        Test.objects.filter(id__in=test_ids)
                        .values_list("sample_id", flat=True)
                    )
                    changed |= add_ids(
                        individual_ids,
                        Test.objects.filter(id__in=test_ids)
                        .values_list("sample__individual_id", flat=True)
                    )
                    changed |= add_ids(
                        analysis_ids,
                        Analysis.objects.filter(test_id__in=test_ids)
                        .values_list("id", flat=True)
                    )
                    changed |= add_ids(
                        variant_ids,
                        Variant.objects.filter(analysis__test_id__in=test_ids)
                        .values_list("id", flat=True)
                    )

                # Analyses -> Test / Sample / Individual / Variants
                if analysis_ids:
                    changed |= add_ids(
                        test_ids,
                        Analysis.objects.filter(id__in=analysis_ids)
                        .values_list("test_id", flat=True)
                    )
                    changed |= add_ids(
                        sample_ids,
                        Analysis.objects.filter(id__in=analysis_ids)
                        .values_list("test__sample_id", flat=True)
                    )
                    changed |= add_ids(
                        individual_ids,
                        Analysis.objects.filter(id__in=analysis_ids)
                        .values_list("test__sample__individual_id", flat=True)
                    )
                    changed |= add_ids(
                        variant_ids,
                        Variant.objects.filter(analysis_id__in=analysis_ids)
                        .values_list("id", flat=True)
                    )

                # Variants -> Analysis / Test / Sample / Individual / Projects (via individual)
                if variant_ids:
                    changed |= add_ids(
                        analysis_ids,
                        Variant.objects.filter(id__in=variant_ids)
                        .values_list("analysis_id", flat=True)
                    )
                    changed |= add_ids(
                        test_ids,
                        Variant.objects.filter(id__in=variant_ids)
                        .values_list("analysis__test_id", flat=True)
                    )
                    changed |= add_ids(
                        sample_ids,
                        Variant.objects.filter(id__in=variant_ids)
                        .values_list("analysis__test__sample_id", flat=True)
                    )
                    changed |= add_ids(
                        individual_ids,
                        Variant.objects.filter(id__in=variant_ids)
                        .values_list("individual_id", flat=True)
                    )

            # Build allowed targets from tasks (direct + connected) and notes
            allowed = defaultdict(set)
            allowed[ct_map["project"].id] |= project_ids
            allowed[ct_map["individual"].id] |= individual_ids
            allowed[ct_map["sample"].id] |= sample_ids
            allowed[ct_map["test"].id] |= test_ids
            allowed[ct_map["analysis"].id] |= analysis_ids
            allowed[ct_map["variant"].id] |= variant_ids

            for ct_id, obj_ids in note_targets.items():
                allowed[ct_id] |= obj_ids

            filter_q = Q(pk__in=[])  # start false
            for ct_id, obj_ids in allowed.items():
                if obj_ids:
                    filter_q |= Q(target_content_type_id=ct_id, target_object_id__in=obj_ids)

            # If no matches, empty queryset
            if any(allowed.values()):
                notifications_qs = notifications_qs.filter(filter_q)
            else:
                notifications_qs = notifications_qs.none()

        # Mark notifications as read when viewed (all unseen, not just current page)
        unread_notifications = notifications_qs.filter(unread=True)
        unread_count = unread_notifications.count()
        if unread_count:
            unread_notifications.update(unread=False)

        paginator = Paginator(notifications_qs, 20)
        page_number = request.GET.get("page") or 1
        page_obj = paginator.get_page(page_number)

        context = {
            "notifications": page_obj.object_list,
            "page_obj": page_obj,
            "unread_count": unread_count,
            "scope": scope,
        }
    except ImportError:
        context = {"notifications": [], "page_obj": None, "unread_count": 0, "scope": "all"}

    # Handle HTMX requests for partial rendering
    if request.headers.get("HX-Request"):
        if request.GET.get("append") == "1":
            return render(request, "lab/notifications.html#notifications-append", context)
        return render(request, "lab/notifications.html#notifications-content", context)

    return render(request, "lab/notifications.html", context)


@login_required
def profile_settings(request):
    """View to manage user profile and notification settings"""
    # Ensure profile exists (signal should handle this, but for safety)
    if not hasattr(request.user, "profile"):
        from .models import Profile

        Profile.objects.create(user=request.user)

    profile = request.user.profile

    # Redirect to SPA if accessed directly without HTMX
    if not request.headers.get("HX-Request") and request.method == "GET":
        return redirect("/?page=profile_settings")

    if request.method == "POST":
        # Update email notification settings
        email_settings = {
            "task_assigned": request.POST.get("task_assigned") == "on",
            "status_change": request.POST.get("status_change") == "on",
            "group_message": request.POST.get("group_message") == "on",
        }

        # Update display preferences
        display_preferences = {
            "filter_popup_on_hover": request.POST.get("filter_popup_on_hover")
            == "on",
            "default_list_view": request.POST.get("default_list_view", "cards"),
        }

        profile.email_notifications = email_settings
        profile.display_preferences = display_preferences
        profile.save()
        messages.success(request, "Settings updated successfully.")
        # For HTMX requests, fall through to the partial rendering below so that
        # we only refresh the settings panel instead of re-embedding the entire SPA.
        # For normal form POSTs, redirect back to the page.
        if not request.headers.get("HX-Request"):
            return redirect("lab:profile_settings")

    # Merge with defaults for display
    # Default to True for all keys if not present
    current_email_settings = profile.email_notifications or {}
    display_settings = {
        "task_assigned": current_email_settings.get("task_assigned", True),
        "status_change": current_email_settings.get("status_change", True),
        "group_message": current_email_settings.get("group_message", True),
    }

    current_display_prefs = profile.display_preferences or {}
    preference_settings = {
        "filter_popup_on_hover": current_display_prefs.get(
            "filter_popup_on_hover", True
        ),
        "default_list_view": current_display_prefs.get("default_list_view", "cards"),
    }

    context = {
        "profile": profile,
        "display_settings": display_settings,
        "preference_settings": preference_settings,
    }

    # Handle HTMX requests for partial rendering
    if request.headers.get("HX-Request"):
        return render(request, "lab/profile_settings.html#profile-settings-content", context)

    return render(request, "lab/profile_settings.html", context)


@login_required
def send_group_message(request):
    if request.method == "POST":
        message = request.POST.get("message")
        if message:
            from django.contrib.auth.models import Group
            from .services import send_notification
            
            try:
                group = Group.objects.get(name="Group Members")
                users = group.user_set.all()
                count = 0
                for user in users:
                    if user != request.user:  # Don't send to self
                        send_notification(
                            sender=request.user,
                            recipient=user,
                            verb="Group Message",
                            description=f"Group Message from {request.user}: {message}",
                            target=group,
                        )
                        count += 1
                messages.success(request, f"Message sent to {count} group members.")
            except Group.DoesNotExist:
                messages.error(request, "Group 'Group Members' does not exist.")
        else:
            messages.error(request, "Message cannot be empty.")
            
        return redirect("lab:profile_settings")
    
    return redirect("lab:profile_settings")


@login_required
def individual_timeline(request, pk):


    return timeline(request, pk)


@login_required
def plots_page(request):
    """View for the plots page showing various data visualizations."""


    return plots_view(request)


@login_required
def nl_search(request):
    """
    Natural language search view that converts user queries to SQL and returns results.
    """
    if request.method == "POST":
        query = request.POST.get("query", "").strip()

        if not query:
            return render(
                request,
                "lab/nl_search.html#nl-search-error",
                {"error": "No query provided."},
            )

        try:
            # Process the natural language query using Mistral
            result = query_natural_language(query, "mistral")

            if result["success"]:
                return render(
                    request,
                    "lab/nl_search.html#nl-search-result",
                    {
                        "query": result["query"],
                        "sql": result["sql"],
                        "result": result["result"],
                        "success": True,
                    },
                )
            else:
                return render(
                    request,
                    "lab/nl_search.html#nl-search-error",
                    {"error": result["error"]},
                )

        except Exception as e:
            return render(
                request,
                "lab/nl_search.html#nl-search-error",
                {"error": f"An error occurred: {str(e)}"},
            )

    # GET request - show the search form
    return render(request, "lab/nl_search.html")


@login_required
def generic_create(request):
    """
    Generic view for creating objects of any model type.
    """
    if request.method == "POST":
        model_name = request.POST.get("model_name")
        app_label = request.POST.get("app_label", "lab")

        if not model_name:
            return HttpResponseBadRequest("Model name not specified.")

        # Get the model class
        try:
            model_class = apps.get_model(app_label=app_label, model_name=model_name)
        except LookupError:
            return HttpResponseBadRequest(f"Model {model_name} not found.")

        # Get the appropriate form
        form_class = FORMS_MAPPING.get(model_name)
        if not form_class:
            return HttpResponseBadRequest(f"No form available for {model_name}.")

        # Normalize M2M payloads coming from comboboxes (<field>_ids) into the form data
        data = request.POST.copy()
        m2m_payloads = {}
        try:
            for m2m_field in model_class._meta.many_to_many:
                field_name = m2m_field.name
                candidate_params = [f"{field_name}_ids"]
                if field_name.endswith("s"):
                    candidate_params.append(f"{field_name[:-1]}_ids")
                raw_val = None
                for pname in candidate_params:
                    raw_val = data.get(pname)
                    if raw_val:
                        break
                id_list = _parse_id_list(raw_val) if raw_val else []
                if id_list:
                    data.setlist(field_name, id_list)
                    m2m_payloads[field_name] = id_list
        except Exception:
            data = request.POST
            m2m_payloads = {}

        form = form_class(data)
        if form.is_valid():
            # Save the object with the user context for created_by field
            obj = form.save(user=request.user)
            
            # Special handling for Task: set content_type and object_id if provided
            if model_name == 'Task' and isinstance(obj, Task):
                content_type_id = request.POST.get("content_type")
                object_id = request.POST.get("object_id")
                if content_type_id and object_id:
                    try:
                        content_type = ContentType.objects.get(pk=content_type_id)
                        obj.content_type = content_type
                        obj.object_id = int(object_id)
                        obj.save()
                    except (ContentType.DoesNotExist, ValueError, TypeError):
                        pass  # Silently fail if invalid
            # Generic: handle any ManyToMany fields posted as JSON lists via <field_name>_ids
            try:
                for m2m_field in obj._meta.many_to_many:
                    field_name = m2m_field.name
                    payload_ids = m2m_payloads.get(field_name)
                    if not payload_ids:
                        continue
                    related_model = m2m_field.remote_field.model
                    related_qs = related_model.objects.filter(pk__in=payload_ids)
                    getattr(obj, field_name).set(related_qs)
            except Exception:
                pass

            # Default status: prefer model-specific, else any status
            if hasattr(obj, "status") and not getattr(obj, "status_id", None):
                model_ct = None
                try:
                    model_ct = ContentType.objects.get_for_model(model_class)
                    # Try to get a model-specific status first
                    default_status = Status.objects.filter(
                        content_type=model_ct
                    ).first()
                    # If no model-specific status, fall back to any status
                    if not default_status:
                        default_status = Status.objects.first()
                except Exception:
                    # Fallback to any status if there's an error
                    default_status = Status.objects.first()

                if default_status:
                    obj.status = default_status
                    obj.save()

            # Optionally create an associated Task
            try:
                if request.POST.get("create_task"):
                    from django.utils.dateparse import parse_datetime

                    ct = ContentType.objects.get_for_model(model_class)
                    title = request.POST.get("task-title") or f"Follow-up for {obj}"
                    description = request.POST.get("task-description", "")
                    assigned_to_id = request.POST.get("task-assigned_to") or getattr(
                        request.user, "id", None
                    )
                    due_raw = request.POST.get("task-due_date")
                    due_dt = parse_datetime(due_raw) if due_raw else None
                    priority = request.POST.get("task-priority") or "medium"
                    # Prefer an 'Active' status, else any
                    status_id = request.POST.get("task-status")
                    if not status_id:
                        active = Status.objects.filter(name__iexact="active").first()
                        status_id = getattr(active, "id", None) or getattr(
                            Status.objects.first(), "id", None
                        )
                    project_id = request.POST.get("task-project") or None

                    task_kwargs = {
                        "title": title,
                        "description": description,
                        "assigned_to_id": assigned_to_id,
                        "created_by": request.user,
                        "due_date": due_dt,
                        "priority": priority,
                        "status_id": status_id,
                        "content_type": ct,
                        "object_id": obj.pk,
                    }
                    if project_id:
                        task_kwargs["project_id"] = project_id
                    # Only create if we have an assignee and a status
                    if task_kwargs.get("assigned_to_id") and task_kwargs.get("status_id"):
                        Task.objects.create(**task_kwargs)
            except Exception:
                # Do not block main creation if task creation fails
                pass

            # Return success response for HTMX
            if request.htmx:
                context = {
                    "object": obj,
                    "model_name": model_name,
                    "app_label": app_label,
                }
                
                # For Sample creation, include individual and all samples
                if model_name == "Sample" and hasattr(obj, 'individual'):
                    context["individual"] = obj.individual
                    all_samples_qs = obj.individual.samples.all().order_by('-id')
                    context["all_samples"] = all_samples_qs
                    context["new_sample"] = obj
                    context["other_samples"] = all_samples_qs.exclude(pk=obj.pk)
                    context["new_sample_pk"] = obj.pk
                
                # For Test creation, include individual, sample, and all tests for that individual
                elif model_name == "Test" and hasattr(obj, 'sample') and obj.sample:
                    context["sample"] = obj.sample
                    context["individual"] = obj.sample.individual
                    # Get all tests for this individual (through all their samples)
                    all_tests_qs = Test.objects.filter(sample__individual=obj.sample.individual).order_by('-id')
                    context["all_tests"] = all_tests_qs
                    context["new_test"] = obj
                    context["other_tests"] = all_tests_qs.exclude(pk=obj.pk)
                    context["new_test_pk"] = obj.pk
                
                # For Analysis creation, include individual, sample, test, and all analyses for that individual
                elif model_name == "Analysis" and hasattr(obj, 'test') and obj.test:
                    context["test"] = obj.test
                    context["sample"] = obj.test.sample
                    context["individual"] = obj.test.sample.individual
                    # Get all analyses for this individual (through test -> sample -> individual)
                    all_analyses_qs = Analysis.objects.filter(test__sample__individual=obj.test.sample.individual).order_by('-id')
                    context["all_analyses"] = all_analyses_qs
                    context["new_analysis"] = obj
                    context["other_analyses"] = all_analyses_qs.exclude(pk=obj.pk)
                    context["new_analysis_pk"] = obj.pk
                
                # For Task creation, include associated object and all tasks for that object
                elif model_name == "Task" and hasattr(obj, 'content_object') and obj.content_object:
                    context["associated_object"] = obj.content_object
                    context["associated_model_name"] = obj.content_type.model
                    context["associated_app_label"] = obj.content_type.app_label
                    # Get all tasks for this same object
                    all_tasks_qs = Task.objects.filter(
                        content_type=obj.content_type,
                        object_id=obj.object_id
                    ).order_by('-id')
                    context["all_tasks"] = all_tasks_qs
                    context["new_task"] = obj
                    context["other_tasks"] = all_tasks_qs.exclude(pk=obj.pk)
                    context["new_task_pk"] = obj.pk
                
                response = render(
                    request,
                    "lab/crud.html#create-success",
                    context,
                )
                # Emit object-specific and generic refresh events for listeners
                try:
                    response["HX-Trigger"] = json.dumps(
                        {
                            f"created-{model_name}": {
                                "pk": obj.pk,
                                "label": str(obj),
                                "app_label": app_label,
                                "model_name": model_name,
                            },
                            f"created-{model_name}-{obj.pk}": True,
                            # Also trigger global filters refresh so dependent UI updates
                            "filters-updated": True,
                        }
                    )
                except Exception:
                    # Fallback to a simple model-level trigger
                    response["HX-Trigger"] = f"created-{model_name}"
                return response
            else:
                return redirect(
                    "lab:generic_detail",
                    app_label=app_label,
                    model_name=model_name,
                    pk=obj.pk,
                )
        else:
            # Form validation failed
            staff_initial_json = "[]"
            institution_initial_json = "[]"
            if model_name == "Individual":
                institution_initial_json = _institution_initial_json_from_post(request.POST)
            if model_name == "Institution":
                staff_initial_json = _staff_initial_json_from_post(request.POST)
            if request.htmx:
                return render(
                    request,
                    "lab/crud.html#create-form",
                    {
                        "form": form,
                        "model_name": model_name,
                        "app_label": app_label,
                        "staff_initial_json": staff_initial_json,
                        "institution_initial_json": institution_initial_json,
                    },
                )
            else:
                return render(
                    request,
                    "lab/index.html",
                    {
                        "create_form": form,
                        "model_name": model_name,
                        "app_label": app_label,
                        "staff_initial_json": staff_initial_json,
                        "institution_initial_json": institution_initial_json,
                    },
                )

    # GET request - show the form
    model_name = request.GET.get("model_name")
    app_label = request.GET.get("app_label", "lab")

    if not model_name:
        return HttpResponseBadRequest("Model name not specified.")

    # Get the model class
    try:
        model_class = apps.get_model(app_label=app_label, model_name=model_name)
    except LookupError:
        return HttpResponseBadRequest(f"Model {model_name} not found.")

    # Get the appropriate form
    form_class = FORMS_MAPPING.get(model_name)
    if not form_class:
        return HttpResponseBadRequest(f"No form available for {model_name}.")

    # Build initial data from query parameters when possible (e.g., preselect individual on Sample creation)
    initial_data = {}
    try:
        candidate_fields = form_class().fields
        for key, value in request.GET.items():
            if key in candidate_fields:
                initial_data[key] = value
    except Exception:
        initial_data = {}

    form = form_class(initial=initial_data)

    # Filter status field to only show statuses for this model class
    if hasattr(form, "fields") and "status" in form.fields:
        try:
            model_ct = ContentType.objects.get_for_model(model_class)
            # Filter statuses to only show those for this model type
            filtered_statuses = Status.objects.filter(
                Q(content_type=model_ct) | Q(content_type__isnull=True)
            ).order_by("name")
            
            # If this is Sample, exclude Individual-specific statuses
            if model_name == "Sample":
                from lab.models import Individual
                individual_ct = ContentType.objects.get_for_model(Individual)
                filtered_statuses = filtered_statuses.exclude(content_type=individual_ct)
            
            form.fields["status"].queryset = filtered_statuses
        except Exception as e:
            # Fallback to all statuses if filtering fails
            form.fields["status"].queryset = Status.objects.all().order_by("name")

    # Fetch related objects for smarter initial selections in generic create forms
    initial_individual = None
    initial_sample = None
    initial_test = None

    # For Sample creation, pre-select the Individual when provided
    if model_name == "Sample" and "individual" in initial_data:
        try:
            from lab.models import Individual

            individual_id = initial_data.get("individual")
            if individual_id:
                initial_individual = Individual.objects.filter(pk=individual_id).first()
        except Exception:
            # If anything goes wrong, we simply skip the prefill
            initial_individual = None

    # For Test creation, pre-select the Sample when provided
    if model_name == "Test" and "sample" in initial_data:
        try:
            from lab.models import Sample

            sample_id = initial_data.get("sample")
            if sample_id:
                initial_sample = Sample.objects.filter(pk=sample_id).first()
        except Exception:
            initial_sample = None

    # For Analysis creation, pre-select the Test when provided
    if model_name == "Analysis" and "test" in initial_data:
        try:
            from lab.models import Test

            test_id = initial_data.get("test")
            if test_id:
                initial_test = Test.objects.filter(pk=test_id).first()
        except Exception:
            initial_test = None

    staff_initial_json = "[]"
    institution_initial_json = "[]"
    if model_name == "Institution":
        staff_initial_json = _staff_initial_json_from_ids(
            _parse_staff_ids(initial_data.get("staff"))
        )
    if model_name == "Individual":
        institution_initial_json = _institution_initial_json_from_ids(
            _parse_id_list(initial_data.get("institution"))
        )

    if request.htmx:
        return render(
            request,
            "lab/crud.html#create-form",
            {
                "form": form,
                "model_name": model_name,
                "app_label": app_label,
                "initial_individual": initial_individual,
                "initial_sample": initial_sample,
                "initial_test": initial_test,
                # Prefixed Task form for sidebar inputs
                "task_form": TaskForm(prefix="task"),
                "staff_initial_json": staff_initial_json,
                "institution_initial_json": institution_initial_json,
            },
        )
    else:
        return render(
            request,
            "lab/index.html",
            {
                "create_form": form,
                "model_name": model_name,
                "app_label": app_label,
                "initial_individual": initial_individual,
                "initial_sample": initial_sample,
                "initial_test": initial_test,
                "staff_initial_json": staff_initial_json,
                "institution_initial_json": institution_initial_json,
            },
        )


@login_required
def generic_edit(request):
    """
    Generic view for editing objects of any model type.
    """
    if request.method == "POST":
        model_name = request.POST.get("model_name")
        app_label = request.POST.get("app_label", "lab")
        pk = request.POST.get("pk")

        if not all([model_name, pk]):
            return HttpResponseBadRequest("Model name and pk not specified.")

        # Get the model class
        try:
            model_class = apps.get_model(app_label=app_label, model_name=model_name)
        except LookupError:
            return HttpResponseBadRequest(f"Model {model_name} not found.")

        # Get the object
        obj = get_object_or_404(model_class, pk=pk)

        # Get the appropriate form
        form_class = FORMS_MAPPING.get(model_name)
        if not form_class:
            return HttpResponseBadRequest(f"No form available for {model_name}.")

        # Capture original M2M values to prevent unintended clearing when fields are omitted
        original_m2m_map = {}
        try:
            for m2m_field in obj._meta.many_to_many:
                try:
                    original_m2m_map[m2m_field.name] = list(
                        getattr(obj, m2m_field.name).values_list("pk", flat=True)
                    )
                except Exception:
                    original_m2m_map[m2m_field.name] = []
        except Exception:
            original_m2m_map = {}

        m2m_payloads = {}

        # Build a complete data dict by merging provided fields with instance defaults
        try:
            baseline_form = form_class(instance=obj)
            data = request.POST.copy()
            for field_name, field in getattr(baseline_form, "fields", {}).items():
                if field_name in data:
                    continue
                # Skip M2M; handled separately
                if isinstance(field, dj_forms.ModelMultipleChoiceField):
                    continue
                # Derive value from instance
                value_to_use = None
                try:
                    if isinstance(field, dj_forms.ModelChoiceField):
                        value_to_use = getattr(obj, f"{field_name}_id", None)
                    else:
                        value_to_use = getattr(obj, field_name, None)
                except Exception:
                    value_to_use = None
                if value_to_use is None:
                    # For unchecked booleans we explicitly send empty string to mean False
                    if isinstance(field, dj_forms.BooleanField):
                        data[field_name] = ""
                    continue
                # Normalize by field type
                try:
                    if isinstance(field, dj_forms.BooleanField):
                        data[field_name] = "on" if bool(value_to_use) else ""
                    else:
                        # Dates/DateTimes stringify nicely, as do PKs and simple types
                        data[field_name] = str(value_to_use)
                except Exception:
                    pass
        except Exception:
            data = request.POST

        # Normalize M2M payloads coming from comboboxes (<field>_ids) into the form data
        try:
            for m2m_field in obj._meta.many_to_many:
                field_name = m2m_field.name
                candidate_params = [f"{field_name}_ids"]
                if field_name.endswith("s"):
                    candidate_params.append(f"{field_name[:-1]}_ids")
                raw_val = None
                for pname in candidate_params:
                    raw_val = request.POST.get(pname)
                    if raw_val:
                        break
                id_list = _parse_id_list(raw_val) if raw_val else []
                if id_list:
                    data.setlist(field_name, id_list)
                    m2m_payloads[field_name] = id_list
                elif field_name not in data and original_m2m_map.get(field_name) is not None:
                    original_ids = [str(pk) for pk in original_m2m_map[field_name]]
                    if original_ids:
                        data.setlist(field_name, original_ids)
        except Exception:
            pass

        form = form_class(data, instance=obj)
        if form.is_valid():
            # Save the object with updated_at handled by the form
            obj = form.save()

            # Special handling for Task: allow updating associated content_type/object_id
            if model_name == "Task" and isinstance(obj, Task):
                content_type_id = request.POST.get("content_type")
                object_id = request.POST.get("object_id")
                if content_type_id and object_id:
                    try:
                        ct = ContentType.objects.get(pk=content_type_id)
                        obj.content_type = ct
                        obj.object_id = int(object_id)
                        obj.save()
                    except (ContentType.DoesNotExist, ValueError, TypeError):
                        # If anything goes wrong, keep the existing association
                        pass

            # Generic: handle any ManyToMany fields posted as JSON lists via <field_name>_ids
            try:
                for m2m_field in obj._meta.many_to_many:
                    field_name = m2m_field.name
                    payload_ids = m2m_payloads.get(field_name)
                    if payload_ids:
                        related_model = m2m_field.remote_field.model
                        related_qs = related_model.objects.filter(pk__in=payload_ids)
                        getattr(obj, field_name).set(related_qs)
                        continue

                    # If the field data was submitted normally, trust the form's handling
                    if data.getlist(field_name):
                        continue

                    # No payload provided for this M2M; restore original values to avoid clearing
                    try:
                        original_ids = original_m2m_map.get(field_name, None)
                        if original_ids is not None:
                            related_model = m2m_field.remote_field.model
                            related_qs = related_model.objects.filter(pk__in=original_ids)
                            getattr(obj, field_name).set(related_qs)
                    except Exception:
                        pass
            except Exception:
                pass

            # Return success response for HTMX
            if request.htmx:
                return render(
                    request,
                    "lab/crud.html#edit-success",
                    {
                        "object": obj,
                        "model_name": model_name,
                        "app_label": app_label,
                    },
                )
            else:
                return redirect(
                    "lab:generic_detail",
                    app_label=app_label,
                    model_name=model_name,
                    pk=obj.pk,
                )
        else:
            # Form validation failed
            staff_initial_json = "[]"
            institution_initial_json = "[]"
            if model_name == "Institution":
                staff_initial_json = _staff_initial_json_from_post(request.POST)
            if model_name == "Individual":
                institution_initial_json = _institution_initial_json_from_post(request.POST)
            if request.htmx:
                context = {
                    "form": form,
                    "object": obj,
                    "model_name": model_name,
                    "app_label": app_label,
                    "staff_initial_json": staff_initial_json,
                    "institution_initial_json": institution_initial_json,
                }
                try:
                    if model_name == "Individual":
                        initial = [
                            {"value": str(t.pk), "label": getattr(t, "label", str(t))}
                            for t in getattr(obj, "hpo_terms", []).all()
                        ]
                        context["hpo_initial_json"] = json.dumps(initial)
                except Exception:
                    context["hpo_initial_json"] = "[]"
                return render(request, "lab/crud.html#edit-form", context)
            else:
                return render(
                    request,
                    "lab/index.html",
                    {
                        "edit_form": form,
                        "object": obj,
                        "model_name": model_name,
                        "app_label": app_label,
                        "staff_initial_json": staff_initial_json,
                        "institution_initial_json": institution_initial_json,
                    },
                )

    # GET request - show the form
    model_name = request.GET.get("model_name")
    app_label = request.GET.get("app_label", "lab")
    pk = request.GET.get("pk")

    if not all([model_name, pk]):
        return HttpResponseBadRequest("Model name and pk not specified.")

    # Get the model class
    try:
        model_class = apps.get_model(app_label=app_label, model_name=model_name)
    except LookupError:
        return HttpResponseBadRequest(f"Model {model_name} not found.")

    # Get the object
    obj = get_object_or_404(model_class, pk=pk)

    # Get the appropriate form
    form_class = FORMS_MAPPING.get(model_name)
    if not form_class:
        return HttpResponseBadRequest(f"No form available for {model_name}.")

    form = form_class(instance=obj)

    # Filter status field to only show statuses for this model class
    if hasattr(form, "fields") and "status" in form.fields:
        try:
            model_ct = ContentType.objects.get_for_model(model_class)
            # Filter statuses to only show those for this model type
            filtered_statuses = Status.objects.filter(
                Q(content_type=model_ct) | Q(content_type__isnull=True)
            ).order_by("name")
            
            # If this is Sample, exclude Individual-specific statuses
            if model_name == "Sample":
                from lab.models import Individual
                individual_ct = ContentType.objects.get_for_model(Individual)
                filtered_statuses = filtered_statuses.exclude(content_type=individual_ct)
            
            form.fields["status"].queryset = filtered_statuses
        except Exception as e:
            # Fallback to all statuses if filtering fails
            form.fields["status"].queryset = Status.objects.all().order_by("name")

    staff_initial_json = "[]"
    if model_name == "Institution":
        staff_initial_json = _staff_initial_json_from_queryset(obj.staff.all())

    if request.htmx:
        context = {
            "form": form,
            "object": obj,
            "model_name": model_name,
            "app_label": app_label,
            "staff_initial_json": staff_initial_json,
                "institution_initial_json": "[]",
        }
        # For Task editing, provide info about the currently associated object
        try:
            if model_name == "Task" and getattr(obj, "content_object", None):
                context["associated_object_label"] = str(obj.content_object)
                ct = obj.content_type
                if ct is not None:
                    context["associated_app_label"] = ct.app_label
                    # Use the concrete model class name for the combobox
                    model_cls = ct.model_class()
                    if model_cls is not None:
                        context["associated_model_name"] = model_cls.__name__
        except Exception:
            # If anything goes wrong, we simply skip these optional hints
            pass
        # Provide initial JSON for HPO combobox in Individual edit form
        try:
            if model_name == "Individual":
                initial = [
                    {"value": str(t.pk), "label": getattr(t, "label", str(t))}
                    for t in getattr(obj, "hpo_terms", []).all()
                ]
                context["hpo_initial_json"] = json.dumps(initial)
                context["institution_initial_json"] = _institution_initial_json_from_queryset(
                    getattr(obj, "institution", []).all()
                )
        except Exception:
            context["hpo_initial_json"] = "[]"
            context["institution_initial_json"] = "[]"

        return render(request, "lab/crud.html#edit-form", context)
    else:
        return render(
            request,
            "lab/index.html",
            {
                "edit_form": form,
                "object": obj,
                "model_name": model_name,
                "app_label": app_label,
                "staff_initial_json": staff_initial_json,
            },
        )


@login_required
def generic_delete(request):
    """
    Generic view for deleting objects of any model type.
    """
    if request.method == "POST":
        model_name = request.POST.get("model_name")
        app_label = request.POST.get("app_label", "lab")
        pk = request.POST.get("pk")

        if not all([model_name, pk]):
            return HttpResponseBadRequest("Model name and pk not specified.")

        # Get the model class
        try:
            model_class = apps.get_model(app_label=app_label, model_name=model_name)
        except LookupError:
            return HttpResponseBadRequest(f"Model {model_name} not found.")

        # Get the object
        obj = get_object_or_404(model_class, pk=pk)

        # Store info before deletion for response
        object_name = str(obj)

        # Delete the object
        obj.delete()

        # Return success response for HTMX
        if request.htmx:
            return render(
                request,
                "lab/crud.html#delete-success",
                {
                    "model_name": model_name,
                    "app_label": app_label,
                    "object_name": object_name,
                },
            )
        else:
            # Redirect to index or search page
            return redirect("lab:index")

    # GET request - show confirmation
    model_name = request.GET.get("model_name")
    app_label = request.GET.get("app_label", "lab")
    pk = request.GET.get("pk")

    if not all([model_name, pk]):
        return HttpResponseBadRequest("Model name and pk not specified.")

    # Get the model class
    try:
        model_class = apps.get_model(app_label=app_label, model_name=model_name)
    except LookupError:
        return HttpResponseBadRequest(f"Model {model_name} not found.")

    # Get the object
    obj = get_object_or_404(model_class, pk=pk)

    if request.htmx:
        return render(
            request,
            "lab/crud.html#delete-confirm",
            {
                "object": obj,
                "model_name": model_name,
                "app_label": app_label,
            },
        )
    else:
        return render(
            request,
            "lab/index.html",
            {
                "delete_confirm": obj,
                "model_name": model_name,
                "app_label": app_label,
            },
        )


@login_required
def nl_search_page(request):
    """
    Standalone page for natural language search.
    """
    if request.headers.get("HX-Request"):
        # Return just the main content for HTMX insertion
        return render(request, "lab/nl_search.html#nl-search-content", {})
    else:
        # Return the main index page with the nl-search content injected
        from django.template.loader import render_to_string

        # Render the nl-search content
        nl_search_html = render_to_string(
            "lab/nl_search.html#nl-search-content", {}, request=request
        )

        # Return the main index page with the nl-search content injected
        return render(request, "lab/index.html", {"activeItem": "nl-search", "nl_search_html": nl_search_html})


def _get_or_create_family(request, user):
    """
    Helper to get or create a family from POST data.
    Returns (family, created, error_response).
    """
    family_id = request.POST.get("family_id")
    family_id_query = request.POST.get("family_id_query")
    family_description = request.POST.get("family_description", "")

    if not family_id and not (family_id_query and family_id_query.strip()):
        return None, False, HttpResponseBadRequest("Family ID is required.")

    desired_family_id = (family_id_query or "").strip() or family_id

    try:
        family = Family.objects.get(family_id=desired_family_id)
        # Update description if provided
        if family_description and family.description != family_description:
            family.description = family_description
            family.save(update_fields=["description"])
        return family, False, None
    except Family.DoesNotExist:
        try:
            family = Family.objects.create(
                family_id=desired_family_id,
                description=family_description,
                created_by=user,
            )
            return family, True, None
        except Exception as e:
            error_msg = f"Error creating family: {str(e)}"
            if request.htmx:
                return None, False, render(
                    request,
                    "lab/crud.html#family-create-error",
                    {"error": error_msg},
                )
            return None, False, HttpResponseBadRequest(error_msg)


def _parse_individuals_data(post_data):
    """
    Parses request.POST to extract individual data indexed by integer keys.
    Returns a dict: {index: {field: value, ...}}
    """
    individuals_data = {}
    for key, value in post_data.items():
        if key.startswith("individuals["):
            try:
                # key format: individuals[0][field_name]
                parts = key.split("][")
                if len(parts) >= 2:
                    index_str = parts[0].replace("individuals[", "")
                    field_name = parts[1].replace("]", "")
                    
                    if index_str.isdigit():
                        index = int(index_str)
                        if index not in individuals_data:
                            individuals_data[index] = {}
                        individuals_data[index][field_name] = value
            except Exception:
                continue
    return individuals_data


def _create_individual(data, family, user, default_status):
    """
    Creates or updates a single individual.
    Returns (individual, created, error_message).
    """
    if not data.get("full_name"):
        return None, False, "Full name is required"

    # Prepare form data
    form_data = {
        "id": data.get("id"),
        "full_name": data.get("full_name"),
        "tc_identity": data.get("tc_identity"),
        "birth_date": data.get("birth_date"),
        "icd11_code": data.get("icd11_code"),
        "council_date": data.get("council_date"),
        "diagnosis": data.get("diagnosis"),
        "diagnosis_date": data.get("diagnosis_date"),
        "mother": data.get("mother"),
        "father": data.get("father"),
        "institution": data.get("institution"),
        "hpo_terms": data.get("hpo_term_ids") or data.get("hpo_terms"),
        "status": data.get("status"),
        "family": family.id,
        "is_index": data.get("is_index") == "true",
        "is_affected": data.get("is_affected") == "true",
        "sex": data.get("sex"),
    }

    # Handle M2M fields (institution, hpo_terms)
    for field in ["institution", "hpo_terms"]:
        val = form_data.get(field)
        if isinstance(val, str):
            try:
                import json
                if val.strip().startswith("["):
                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        form_data[field] = parsed
                else:
                    if val.strip():
                        form_data[field] = [val]
                    else:
                        form_data.pop(field, None)
            except Exception:
                if val.strip():
                    form_data[field] = [val]
                else:
                    form_data.pop(field, None)

    # Clean up empty values
    form_data = {k: v for k, v in form_data.items() if v is not None and v != ""}
    
    # Ensure family is set
    form_data["family"] = family.id
    # Default status
    if not form_data.get("status") and default_status:
        form_data["status"] = default_status.id

    # Check if updating
    instance = None
    if form_data.get("id"):
        try:
            instance = Individual.objects.get(pk=int(form_data["id"]))
        except Exception:
            pass

    from .forms import IndividualForm
    if instance:
        form = IndividualForm(form_data, instance=instance)
    else:
        form = IndividualForm(form_data)

    if form.is_valid():
        indiv = form.save(commit=False)
        indiv.created_by = user
        indiv.save()
        form.save_m2m()
        return indiv, instance is None, None
    else:
        return None, False, f"Validation error: {form.errors}"


def _resolve_parent(val):
    """
    Resolves a parent individual from ID or CrossIdentifier value.
    """
    if not val:
        return None
    sval = str(val).strip()
    if not sval:
        return None
        
    # Try ID first
    if sval.isdigit():
        ind = Individual.objects.filter(pk=int(sval)).first()
        if ind:
            return ind
            
    # Try CrossIdentifier
    from .models import CrossIdentifier
    ci = CrossIdentifier.objects.filter(id_value=sval).first()
    if ci:
        return ci.individual
    return None


@login_required
def family_create_segway(request):
    """
    Segway view that handles family creation with multiple individuals.
    Parses the form data and calls generic_create for the family and individuals.
    """
    # GET: render the family create/edit modal
    if request.method == "GET":
        individual_id = request.GET.get("individual_id")
        lock_family = request.GET.get("lock_family") == "true"

        initial_family = None
        initial_individual = None
        if individual_id:
            try:
                initial_individual = Individual.objects.select_related("family").get(
                    pk=int(individual_id)
                )
                initial_family = initial_individual.family
            except (Individual.DoesNotExist, ValueError, TypeError):
                initial_individual = None
                initial_family = None

        family_initial_label = ""
        family_initial_value = ""
        if initial_family is not None:
            try:
                family_initial_label = getattr(initial_family, "family_id", "") or str(
                    initial_family
                )
                family_initial_value = str(initial_family.pk)
            except Exception:
                family_initial_label = ""
                family_initial_value = ""

        # Get individual statuses for the Status dropdown
        individual_statuses = Status.objects.filter(
            Q(content_type=ContentType.objects.get_for_model(Individual))
            | Q(content_type__isnull=True)
        ).order_by("name")
        
        # Get identifier types for the Primary ID dropdown
        identifier_types = IdentifierType.objects.all().order_by("name")
        
        return render(
            request,
            "lab/crud.html#family-create-form",
            {
                "initial_family": initial_family,
                "initial_individual": initial_individual,
                "lock_family": lock_family,
                "family_initial_label": family_initial_label,
                "family_initial_value": family_initial_value,
                "individual_statuses": individual_statuses,
                "identifier_types": identifier_types,
            },
        )

    if request.method == "POST":
        try:
            # 1. Get or Create Family
            family, family_created, error_response = _get_or_create_family(request, request.user)
            if error_response:
                return error_response

            # 2. Parse Individuals Data
            individuals_data = _parse_individuals_data(request.POST)

            # 3. Create Individuals
            created_individuals = []
            updated_individuals = []
            created_individuals = []
            updated_individuals = []
            reassigned_individuals = []
            individual_errors = []
            
            # Get default status for individuals
            try:
                indiv_ct = ContentType.objects.get_for_model(Individual)
                default_status = Status.objects.filter(
                    Q(content_type=indiv_ct) | Q(content_type__isnull=True)
                ).order_by("name").first()
            except Exception:
                default_status = None

            for index, data in individuals_data.items():
                individual, is_created, error_msg = _create_individual(
                    data, family, request.user, default_status
                )
                
                if error_msg:
                    print(f"Error creating individual at index {index}: {error_msg}")
                    individual_errors.append(f"Individual {index}: {error_msg}")
                    continue

                if individual:
                    if is_created:
                        created_individuals.append((index, individual))
                    else:
                        updated_individuals.append((index, individual))

            # 4. Resolve Relationships (Mother/Father)
            all_individuals = created_individuals + updated_individuals
            index_to_individual = {idx: ind for idx, ind in all_individuals}

            def _parent_from_index(idx_str):
                try:
                    if idx_str in (None, ""):
                        return None
                    return index_to_individual.get(int(idx_str))
                except (TypeError, ValueError):
                    return None

            for idx, individual in all_individuals:
                data = individuals_data.get(idx, {}) or {}

                # Prefer within-form index-based parents for this segway view
                mother_index = data.get("mother_index")
                father_index = data.get("father_index")

                m_obj = _parent_from_index(mother_index)
                f_obj = _parent_from_index(father_index)

                # Fallback to legacy resolution (e.g. if values came from search fields)
                if not m_obj:
                    mother_val = data.get("mother") or data.get("mother_query")
                    m_obj = _resolve_parent(mother_val)
                if not f_obj:
                    father_val = data.get("father") or data.get("father_query")
                    f_obj = _resolve_parent(father_val)

                changed = False
                if m_obj and individual.mother_id != m_obj.id:
                    individual.mother = m_obj
                    changed = True
                if f_obj and individual.father_id != f_obj.id:
                    individual.father = f_obj
                    changed = True
                if changed:
                    individual.save()

                # Handle CrossIdentifiers (IDs)
                prefix = f"individuals[{idx}][ids]"
                id_rows = {}
                for key, value in request.POST.items():
                    if key.startswith(prefix):
                        try:
                            parts = key.split("][")
                            if len(parts) >= 4:
                                row_idx = int(parts[2])
                                field = parts[3].replace("]", "")
                                if row_idx not in id_rows:
                                    id_rows[row_idx] = {}
                                id_rows[row_idx][field] = value
                        except Exception:
                            continue
                
                # Local import removed as they are imported globally
                for row_idx, id_data in id_rows.items():
                    id_type_id = id_data.get("type")
                    id_value = id_data.get("value")
                    if id_type_id and id_value:
                        try:
                            id_type = IdentifierType.objects.get(pk=id_type_id)
                            if not individual.cross_ids.filter(id_type=id_type, id_value=id_value).exists():
                                CrossIdentifier.objects.create(
                                    individual=individual,
                                    id_type=id_type,
                                    id_value=id_value,
                                    created_by=request.user
                                )
                        except Exception:
                            pass

                # Handle Notes
                note_prefix = f"individuals[{idx}][notes]"
                note_rows = {}
                for key, value in request.POST.items():
                    if key.startswith(note_prefix):
                        try:
                            parts = key.split("][")
                            if len(parts) >= 4:
                                row_idx = int(parts[2])
                                field = parts[3].replace("]", "")
                                if row_idx not in note_rows:
                                    note_rows[row_idx] = {}
                                note_rows[row_idx][field] = value
                        except Exception:
                            continue
                            
                for row_idx, note_data in note_rows.items():
                    content = note_data.get("content")
                    if content:
                        from .models import Note
                        Note.objects.create(
                            content_object=individual,
                            content=content,
                            user=request.user
                        )

                # Handle Task Creation
                if data.get("task-assigned_to") and data.get("task-status"):
                    try:
                        from django.utils.dateparse import parse_datetime
                        due_raw = data.get("task-due_date")
                        due_dt = parse_datetime(due_raw) if due_raw else None
                        
                        Task.objects.create(
                            title=data.get("task-title") or f"Follow-up for {individual.full_name}",
                            description=data.get("task-description", ""),
                            assigned_to_id=data.get("task-assigned_to"),
                            created_by=request.user,
                            due_date=due_dt,
                            priority=data.get("task-priority") or "medium",
                            status_id=data.get("task-status"),
                            project_id=data.get("task-project") or None,
                            content_object=individual
                        )
                    except Exception as e:
                        print(f"Error creating task for individual {index}: {e}")

            # Prepare lists for success summary
            created_only = [ind for _, ind in created_individuals]
            updated_only = [ind for _, ind in updated_individuals]

            # Individuals in this family after changes
            all_family_individuals = list(getattr(family, "individuals").all())
            changed_ids = {ind.id for ind in created_only + updated_only}
            unchanged_individuals = [
                ind for ind in all_family_individuals if ind.id not in changed_ids
            ]

            # Statuses for Individual cards/badges in the success popup
            try:
                indiv_ct = ContentType.objects.get_for_model(Individual)
                individual_statuses = Status.objects.filter(
                    Q(content_type=indiv_ct) | Q(content_type__isnull=True)
                ).order_by("name")
            except Exception:
                individual_statuses = Status.objects.all().order_by("name")

            # Return success response
            if request.htmx:
                return render(
                    request,
                    "lab/crud.html#family-create-success",
                    {
                        "family": family,
                        "family_was_created": family_created,
                        "count_created": len(created_only),
                        "count_updated": len(updated_only),
                        "created_individuals": created_only,
                        "updated_individuals": updated_only,
                        "unchanged_individuals": unchanged_individuals,
                        "reassigned_individuals": reassigned_individuals,
                        "individual_errors": individual_errors,
                        "individual_statuses": individual_statuses,
                    },
                )
            return redirect("lab:index")

        except Exception as e:
            import traceback
            traceback.print_exc()
            error_msg = f"Unexpected error: {str(e)}"
            if request.htmx:
                return render(
                    request,
                    "lab/crud.html#family-create-error",
                    {"error": error_msg},
                )
            return HttpResponseBadRequest(error_msg)

    # GET request - show the form
    if request.htmx:
        return render(
            request,
            "lab/crud.html#family-create-form",
            {
                "institutions": Institution.objects.all(),
                "individual_statuses": Status.objects.filter(
                    Q(content_type=ContentType.objects.get_for_model(Individual))
                    | Q(content_type__isnull=True)
                ).order_by("name"),
                "identifier_types": IdentifierType.objects.all().order_by("name"),
                "existing_families": Family.objects.all().order_by("family_id"),
                "users": User.objects.all().order_by("username"),
                "task_statuses": Status.objects.filter(
                    Q(content_type=ContentType.objects.get_for_model(Task))
                    | Q(content_type__isnull=True)
                ).order_by("name"),
                "projects": Project.objects.all().order_by("name"),
            },
        )
    else:
        return redirect("lab:index")


def plots(request):
    return render(request, "lab/index.html", {"activeItem": "plots"})


def map_page(request):
    """Render the map page template."""
    return render(request, "lab/map.html")


@login_required
def map_view(request):
    """
    Generate a scatter map visualization showing institutions of filtered individuals.
    """
    
    # Start with base queryset for individuals
    individuals_queryset = Individual.objects.all()
    
    # Get individual type filter from POST or GET request
    individual_types = ['all']  # Default to all
    if request.method == 'GET':
        raw_types = request.GET.get('individual_types')
        if raw_types:
            try:
                parsed = json.loads(raw_types)
                if isinstance(parsed, list) and parsed:
                    individual_types = parsed
            except Exception:
                # Fallback to getlist if not JSON
                values = request.GET.getlist('individual_types')
                if values:
                    individual_types = values
        if not individual_types or 'all' in individual_types:
            individual_types = ['all']
    
    # Get clustering toggle from POST or GET request
    enable_clustering = request.GET.get('enable_clustering', 'false').lower() == 'true'
    
    # Apply individual type filtering
    if individual_types != ['all']:
        if 'families' in individual_types:
            # Only one individual per family - get the first one from each family
            family_ids = individuals_queryset.filter(
                family__isnull=False
            ).values('family').annotate(
                first_individual_id=Min('id')
            ).values_list('first_individual_id', flat=True)
            
            individuals_queryset = individuals_queryset.filter(id__in=family_ids)
        elif 'probands' in individual_types:
            # Only probands selected
            individuals_queryset = individuals_queryset.filter(is_index=True)
    
    # Apply global filters using the shared filter engine (accepting both GET/POST)
    # Apply global filters using the shared filter engine (GET-only)
    individuals_queryset = apply_filters(request, "Individual", individuals_queryset)
    
    # Generate map data using the visualization module
    chart_data = generate_map_data(individuals_queryset, individual_types, enable_clustering)
    
    # Add clustering state to context
    chart_data['enable_clustering'] = enable_clustering
    
    # Return HTML for HTMX requests, render template for page requests
    if request.htmx:
        return render(request, 'lab/map.html#map-partial', chart_data)
    else:
        return render(request, 'lab/map.html', chart_data)





def pie_chart_view(request, model_name, attribute_name):
    """
    Generate a pie chart for any model and attribute combination.
    
    Args:
        model_name: The name of the Django model (e.g., 'Individual', 'Sample')
        attribute_name: The name of the attribute to group by (e.g., 'status__name', 'type__name')
    """
    import plotly.graph_objects as go
    
    try:
        # Get the model class
        model_class = apps.get_model('lab', model_name)
        
        # Validate that the attribute exists
        if not hasattr(model_class, attribute_name.split('__')[0]):
            return JsonResponse({
                'error': f'Attribute "{attribute_name}" does not exist on model "{model_name}"'
            }, status=400)
        
        # Start with base queryset
        queryset = model_class.objects.all()
        
        # Apply global filters
        active_filters = request.session.get('active_filters', {})
        if active_filters:
            filter_conditions = Q()
            
            for filter_key, filter_values in active_filters.items():
                if filter_values:  # Only apply non-empty filters
                    # Handle different filter types
                    if isinstance(filter_values, list):
                        if filter_values:  # Non-empty list
                            filter_conditions &= Q(**{filter_key: filter_values[0]})  # Take first value for now
                    else:
                        filter_conditions &= Q(**{filter_key: filter_values})
            
            if filter_conditions:
                queryset = queryset.filter(filter_conditions)
        
        # Get the data with filters applied
        queryset = queryset.values(attribute_name).annotate(count=Count('id')).order_by('-count')
        
        if not queryset:
            return JsonResponse({
                'error': f'No data found for {model_name}.{attribute_name}'
            }, status=404)
        
        # Prepare data for pie chart
        labels = []
        values = []
        
        for item in queryset:
            # Handle None values
            label = item[attribute_name] if item[attribute_name] is not None else 'Unknown'
            labels.append(str(label))
            values.append(item['count'])
        
        # Create pie chart
        fig = go.Figure(data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.3,  # Creates a donut chart
                textinfo='value',
                textposition='outside',
                marker=dict(colors=['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F'])
            )
        ])
        
        fig.update_layout(
            title=f'{model_name} Distribution by {attribute_name.replace("__", " ").title()}',
            height=400,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        # Calculate percentages
        total = sum(values)
        data_with_percentages = []
        for label, value in zip(labels, values):
            percentage = (value / total * 100) if total > 0 else 0
            data_with_percentages.append((label, value, percentage))
        
        # Prepare response data
        chart_data = {
            'chart_json': json.dumps(fig.to_dict()),
            'model_name': model_name,
            'attribute_name': attribute_name,
            'total_count': total,
            'unique_values': len(values),
            'data': data_with_percentages
        }
        
        if request.htmx:
            return render(request, 'lab/pie_chart_partial.html', chart_data)
        else:
            return render(request, 'lab/pie_chart.html', chart_data)
            
    except LookupError:
        return JsonResponse({
            'error': f'Model "{model_name}" not found in app "lab"'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'error': f'Error generating pie chart: {str(e)}'
        }, status=500)


@login_required
def get_stats_counts(request):

    active_filters = request.session.get('active_filters', {})
    filter_conditions = Q()
    if active_filters:
        for filter_key, filter_values in active_filters.items():
            if filter_values:
                if isinstance(filter_values, list):
                    if filter_values:
                        filter_conditions &= Q(**{filter_key: filter_values[0]})
                else:
                    filter_conditions &= Q(**{filter_key: filter_values})
    individuals_queryset = Individual.objects.all()
    samples_queryset = Sample.objects.all().exclude(sample_type__name="Placeholder")
    tests_queryset = Test.objects.all().exclude(sample__sample_type__name="Placeholder")
    analyses_queryset = Analysis.objects.all()
    if filter_conditions:
        individuals_queryset = individuals_queryset.filter(filter_conditions)
        samples_queryset = samples_queryset.filter(filter_conditions)
        tests_queryset = tests_queryset.filter(filter_conditions)
        analyses_queryset = analyses_queryset.filter(filter_conditions)
    data = {
        'individuals': individuals_queryset.count(),
        'samples': samples_queryset.count(),
        'tests': tests_queryset.count(),
        'analyses': analyses_queryset.count(),
    }
    return JsonResponse(data)


@login_required
def edit_individual_hpo_terms(request):
    """
    Return the edit form for HPO terms inline (not in a modal).
    """
    individual_id = request.GET.get("individual_id")
    
    if not individual_id:
        return HttpResponseBadRequest("Individual ID not specified.")
    
    try:
        individual = Individual.objects.get(pk=individual_id)
    except Individual.DoesNotExist:
        return HttpResponseBadRequest("Individual not found.")
    
    # Check permissions
    if not request.user.has_perm("lab.change_individual"):
        return HttpResponseForbidden("You don't have permission to edit individuals.")
    
    # Build initial JSON for HPO terms combobox
    try:
        hpo_initial = [
            {"value": str(t.pk), "label": getattr(t, "label", str(t))}
            for t in getattr(individual, "hpo_terms", []).all()
        ]
        hpo_initial_json = json.dumps(hpo_initial)
    except Exception:
        hpo_initial_json = "[]"
    
    if request.htmx:
        return render(
            request,
            "lab/individual.html#hpo-terms-edit",
            {
                "item": individual,
                "hpo_initial_json": hpo_initial_json,
            },
        )
    else:
        return redirect("lab:generic_detail", app_label="lab", model_name="Individual", pk=individual.pk)


@login_required
def view_individual_hpo_terms(request):
    """
    Return the view mode for HPO terms (used by cancel button).
    """
    individual_id = request.GET.get("individual_id")
    
    if not individual_id:
        return HttpResponseBadRequest("Individual ID not specified.")
    
    try:
        individual = Individual.objects.get(pk=individual_id)
    except Individual.DoesNotExist:
        return HttpResponseBadRequest("Individual not found.")
    
    # Build initial JSON for HPO terms (for potential future use)
    try:
        hpo_initial = [
            {"value": str(t.pk), "label": getattr(t, "label", str(t))}
            for t in getattr(individual, "hpo_terms", []).all()
        ]
        hpo_initial_json = json.dumps(hpo_initial)
    except Exception:
        hpo_initial_json = "[]"
    
    if request.htmx:
        return render(
            request,
            "lab/individual.html#hpo-terms-section",
            {
                "item": individual,
                "hpo_initial_json": hpo_initial_json,
            },
        )
    else:
        return redirect("lab:generic_detail", app_label="lab", model_name="Individual", pk=individual.pk)


@login_required
@require_POST
def update_individual_hpo_terms(request):
    """
    Update HPO terms for an individual.
    """
    individual_id = request.POST.get("individual_id")
    hpo_term_ids = request.POST.get("hpo_term_ids")
    
    if not individual_id:
        return HttpResponseBadRequest("Individual ID not specified.")
    
    try:
        individual = Individual.objects.get(pk=individual_id)
    except Individual.DoesNotExist:
        return HttpResponseBadRequest("Individual not found.")
    
    # Check permissions
    if not request.user.has_perm("lab.change_individual"):
        return HttpResponseForbidden("You don't have permission to update individuals.")
    
    # Parse HPO term IDs
    try:
        if hpo_term_ids:
            if isinstance(hpo_term_ids, str) and hpo_term_ids.strip().startswith("["):
                term_ids = json.loads(hpo_term_ids)
            else:
                term_ids = [v for v in (hpo_term_ids or "").split(",") if v]
        else:
            term_ids = []
    except Exception:
        term_ids = []
    
    # Get Term model
    try:
        Term = apps.get_model(app_label="ontologies", model_name="Term")
        # Filter to only HPO terms (ontology type 1)
        terms = Term.objects.filter(
            pk__in=term_ids,
            ontology__type=1
        )
        individual.hpo_terms.set(terms)
    except Exception as e:
        return HttpResponseBadRequest(f"Error updating HPO terms: {str(e)}")
    
    # Return the updated HPO terms section
    if request.htmx:
        # Build initial JSON for HPO terms combobox (for modal)
        try:
            hpo_initial = [
                {"value": str(t.pk), "label": getattr(t, "label", str(t))}
                for t in getattr(individual, "hpo_terms", []).all()
            ]
            hpo_initial_json = json.dumps(hpo_initial)
        except Exception:
            hpo_initial_json = "[]"
        return render(
            request,
            "lab/individual.html#hpo-terms-section",
            {
                "item": individual,
                "hpo_initial_json": hpo_initial_json,
            },
        )
    else:
        return redirect("lab:generic_detail", app_label="lab", model_name="Individual", pk=individual.pk)