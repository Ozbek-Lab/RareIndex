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
import json

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


from .filters import apply_filters, FILTER_CONFIG, get_available_statuses, get_available_types

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


def _staff_initial_json_from_queryset(qs):
    if not qs:
        return "[]"
    data = [{"value": str(user.pk), "label": _format_user_label(user)} for user in qs]
    return json.dumps(data)


def _parse_staff_ids(raw_value):
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
    }
    print("index 00")

    if request.headers.get("HX-Request"):
        print("index 01")
        return render(request, "lab/index.html#index", context)
    print("index 02")
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

    num_items = filtered_items.count()

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
                        base_qs = base_qs.filter(cross_ids__id_value__icontains=own_search_term).distinct()
                    else:
                        # Try direct icontains on specified label field
                        # BUT ALSO include cross_id search for related models if applicable
                        q_label = _Q(**{f"{label_field}__icontains": own_search_term})
                        
                        if target_model_name == "Sample":
                            q_label |= _Q(individual__cross_ids__id_value__icontains=own_search_term)
                        elif target_model_name == "Test":
                            q_label |= _Q(sample__individual__cross_ids__id_value__icontains=own_search_term)
                        elif target_model_name == "Analysis":
                            q_label |= _Q(test__sample__individual__cross_ids__id_value__icontains=own_search_term)
                        elif target_model_name == "Variant":
                            q_label |= _Q(individual__cross_ids__id_value__icontains=own_search_term)
                            
                        base_qs = base_qs.filter(q_label).distinct()
                else:
                    # Fallback: OR over all CharField/TextField
                    from django.db.models import Q as _Q

                    text_fields = []
                    try:
                        for f in target_model._meta.get_fields():
                            internal = getattr(f, "get_internal_type", lambda: None)()
                            if internal in ("CharField", "TextField"):
                                text_fields.append(f.name)
                    except Exception:
                        text_fields = []
                    if text_fields:
                        qobj = _Q()
                        for fname in text_fields:
                            qobj |= _Q(**{f"{fname}__icontains": own_search_term})
                        
                        # Special handling for Individual: also search cross_ids
                        if target_model_name == "Individual":
                            qobj |= _Q(cross_ids__id_value__icontains=own_search_term)
                        elif target_model_name == "Sample":
                            qobj |= _Q(individual__cross_ids__id_value__icontains=own_search_term)
                        elif target_model_name == "Test":
                            qobj |= _Q(sample__individual__cross_ids__id_value__icontains=own_search_term)
                        elif target_model_name == "Analysis":
                            qobj |= _Q(test__sample__individual__cross_ids__id_value__icontains=own_search_term)
                        elif target_model_name == "Variant":
                            qobj |= _Q(individual__cross_ids__id_value__icontains=own_search_term)
                            
                        base_qs = base_qs.filter(qobj).distinct()
            except Exception:
                # If filtering fails, leave base_qs as-is
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
        "search": own_search_term,
        "app_label": target_app_label,
        "model_name": target_model_name,
        "all_filters": {
            k: v for k, v in request.GET.items() if k.startswith("filter_")
        },
        "view_mode": view_mode,
        "card": card_partial,
        "icon_class": icon_class,
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
    elif target_model_name == "Sample":
        context["analyses"] = [
            analysis for test in obj.tests.all() for analysis in test.analyses.all()
        ]
        # Get all available Sample statuses for status dropdown
        sample_ct = ContentType.objects.get_for_model(Sample)
        context["sample_statuses"] = Status.objects.filter(
            Q(content_type=sample_ct) | Q(content_type__isnull=True)
        ).order_by("name")
    
    # Add statuses for any model that has a status field
    if hasattr(target_model, 'status'):
        model_ct = ContentType.objects.get_for_model(target_model)
        statuses_var_name = f"{target_model_name.lower()}_statuses"
        if statuses_var_name not in context:  # Only add if not already added above
            context[statuses_var_name] = Status.objects.filter(
                Q(content_type=model_ct) | Q(content_type__isnull=True)
            ).order_by("name")

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
        
        # Render the single generic combobox partial
        # We need to pass the correct context for the combobox controller
        context = {
            "app_label": app_label,
            "model_name": model_class.__name__, # Use class name for display/logic
            "value_field": "pk",
            "name": "object_id",
            "icon_class": "fa-magnifying-glass",
            "initial": "", # No initial value when switching types
            "initial_value": "",
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
        response = HttpResponse(status=204)
        response["HX-Refresh"] = "true"
        return response

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
        response = HttpResponse(status=204)
        response["HX-Refresh"] = "true"
        return response

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

        notifications = Notification.objects.filter(recipient=request.user).order_by(
            "-timestamp"
        )

        # Mark notifications as read when viewed
        unread_notifications = notifications.filter(unread=True)
        unread_notifications.update(unread=False)

        context = {
            "notifications": notifications,
            "unread_count": unread_notifications.count(),
        }
    except ImportError:
        context = {"notifications": [], "unread_count": 0}

    # Handle HTMX requests for partial rendering
    if request.headers.get("HX-Request"):
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
        profile.email_notifications = email_settings
        profile.save()
        messages.success(request, "Notification settings updated successfully.")
        return redirect("lab:profile_settings")

    # Merge with defaults for display
    # Default to True for all keys if not present
    current_settings = profile.email_notifications or {}
    display_settings = {
        "task_assigned": current_settings.get("task_assigned", True),
        "status_change": current_settings.get("status_change", True),
        "group_message": current_settings.get("group_message", True),
    }

    context = {
        "profile": profile,
        "display_settings": display_settings,
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

        form = form_class(request.POST)
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
                    candidate_params = [f"{field_name}_ids"]
                    if field_name.endswith("s"):
                        candidate_params.append(f"{field_name[:-1]}_ids")
                    json_val = None
                    for pname in candidate_params:
                        json_val = request.POST.get(pname)
                        if json_val:
                            break
                    if not json_val:
                        continue
                    try:
                        id_list = json.loads(json_val)
                    except Exception:
                        id_list = [v for v in (json_val or "").split(",") if v]
                    if isinstance(id_list, list) and id_list:
                        related_model = m2m_field.remote_field.model
                        related_qs = related_model.objects.filter(pk__in=id_list)
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
                response = render(
                    request,
                    "lab/crud.html#create-success",
                    {
                        "object": obj,
                        "model_name": model_name,
                        "app_label": app_label,
                    },
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
            print(
                f"DEBUG: Filtered statuses for {model_name}: {filtered_statuses.count()} statuses found"
            )
            print(f"DEBUG: Model CT: {model_ct}")
            print(f"DEBUG: Available statuses: {[s.name for s in filtered_statuses]}")
        except Exception as e:
            print(f"Error filtering statuses for {model_name}: {e}")
            # Fallback to all statuses if filtering fails
            form.fields["status"].queryset = Status.objects.all().order_by("name")

    # Fetch Individual object if individual is in initial_data (for Sample form)
    initial_individual = None
    if model_name == "Sample" and "individual" in initial_data:
        try:
            from lab.models import Individual
            individual_id = initial_data.get("individual")
            if individual_id:
                initial_individual = Individual.objects.filter(pk=individual_id).first()
        except Exception:
            pass

    staff_initial_json = "[]"
    if model_name == "Institution":
        staff_initial_json = _staff_initial_json_from_ids(
            _parse_staff_ids(initial_data.get("staff"))
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
                # Prefixed Task form for sidebar inputs
                "task_form": TaskForm(prefix="task"),
                "staff_initial_json": staff_initial_json,
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
                "staff_initial_json": staff_initial_json,
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

        form = form_class(data, instance=obj)
        if form.is_valid():
            # Save the object with updated_at handled by the form
            obj = form.save()

            # Generic: handle any ManyToMany fields posted as JSON lists via <field_name>_ids
            try:
                for m2m_field in obj._meta.many_to_many:
                    field_name = m2m_field.name
                    candidate_params = [f"{field_name}_ids"]
                    if field_name.endswith("s"):
                        candidate_params.append(f"{field_name[:-1]}_ids")
                    json_val = None
                    for pname in candidate_params:
                        json_val = request.POST.get(pname)
                        if json_val:
                            break
                    if not json_val:
                        # No payload provided for this M2M; restore original values to avoid clearing
                        try:
                            original_ids = original_m2m_map.get(field_name, None)
                            if original_ids is not None:
                                related_model = m2m_field.remote_field.model
                                related_qs = related_model.objects.filter(
                                    pk__in=original_ids
                                )
                                getattr(obj, field_name).set(related_qs)
                        except Exception:
                            pass
                        continue
                    try:
                        id_list = json.loads(json_val)
                    except Exception:
                        id_list = [v for v in (json_val or "").split(",") if v]
                    if isinstance(id_list, list):
                        related_model = m2m_field.remote_field.model
                        related_qs = related_model.objects.filter(pk__in=id_list)
                        getattr(obj, field_name).set(related_qs)
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
            if model_name == "Institution":
                staff_initial_json = _staff_initial_json_from_post(request.POST)
            if request.htmx:
                context = {
                    "form": form,
                    "object": obj,
                    "model_name": model_name,
                    "app_label": app_label,
                    "staff_initial_json": staff_initial_json,
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
            print(
                f"DEBUG: Filtered statuses for {model_name}: {filtered_statuses.count()} statuses found"
            )
            print(f"DEBUG: Model CT: {model_ct}")
            print(f"DEBUG: Available statuses: {[s.name for s in filtered_statuses]}")
        except Exception as e:
            print(f"Error filtering statuses for {model_name}: {e}")
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
        }
        # Provide initial JSON for HPO combobox in Individual edit form
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
        return render(
            request, "lab/index.html", {"initial_nl_search_html": nl_search_html}
        )


@login_required
def family_create_segway(request):
    """
    Segway view that handles family creation with multiple individuals.
    Parses the form data and calls generic_create for the family and individuals.
    """
    if request.method == "POST":
        try:
            # Debug: Print all POST data
            print("=== DEBUG: All POST data ===")
            for key, value in request.POST.items():
                print(f"{key}: {value}")
            print("=== END POST data ===")

            # Extract family data
            family_id = request.POST.get("family_id")
            family_id_query = request.POST.get("family_id_query")
            family_description = request.POST.get("family_description", "")

            print(f"=== DEBUG: Received family_id: '{family_id}' ===")
            print(f"=== DEBUG: Received family_description: '{family_description}' ===")

            if not family_id and not (family_id_query and family_id_query.strip()):
                return HttpResponseBadRequest("Family ID is required.")

            # Determine the desired family identifier (typed query has precedence when different)
            desired_family_id = (family_id_query or "").strip() or family_id

            # Check if family already exists
            existing_family = None
            try:
                existing_family = Family.objects.get(family_id=desired_family_id)
                print(f"=== DEBUG: Family with ID '{family_id}' already exists ===")
            except Family.DoesNotExist:
                print(
                    f"=== DEBUG: Family with ID '{desired_family_id}' does not exist, will create new ==="
                )

            # If family exists, use it; otherwise create new one
            if existing_family:
                family = existing_family
                family_was_created = False
                print(f"=== DEBUG: Using existing family with ID: {family.id} ===")
                # Update description if provided
                try:
                    if family_description is not None and family.description != family_description:
                        family.description = family_description
                        family.save(update_fields=["description"])
                        print("=== DEBUG: Updated family description ===")
                except Exception as _e:
                    print(f"=== DEBUG: Failed to update family description: {_e}")
            else:
                # Create new family directly without form validation
                # This bypasses the ChoiceField validation issue
                try:
                    family = Family.objects.create(
                        family_id=desired_family_id,
                        description=family_description,
                        created_by=request.user,
                    )
                    family_was_created = True
                    print(f"=== DEBUG: Family created with ID: {family.id} ===")
                except Exception as e:
                    error_msg = f"Error creating family: {str(e)}"
                    print(f"=== DEBUG: {error_msg} ===")
                    if request.htmx:
                        return render(
                            request,
                            "lab/crud.html#family-create-error",
                            {
                                "error": error_msg,
                            },
                        )
                    else:
                        return HttpResponseBadRequest(error_msg)

            # Extract individual data
            individuals_data = {}
            for key, value in request.POST.items():
                if key.startswith("individuals[") and "]" in key:
                    # Parse key like "individuals[0][full_name]" -> index=0, field=full_name
                    parts = key.split("[")
                    if len(parts) == 3:
                        index = parts[1].rstrip("]")
                        field = parts[2].rstrip("]")

                        if index not in individuals_data:
                            individuals_data[index] = {}
                        individuals_data[index][field] = value

            print(f"=== DEBUG: Extracted individuals data: {individuals_data} ===")

            created_individuals = []  # list of tuples: (index, individual)
            updated_individuals = []  # list of tuples: (index, individual)
            reassigned_individuals = []  # list of tuples: (index, individual, old_family_id)
            mother_individual = None
            father_individual = None

            # First pass: create all individuals
            # Pre-compute a default status for Individuals if not provided
            try:
                indiv_ct = ContentType.objects.get_for_model(Individual)
                default_individual_status = (
                    Status.objects.filter(
                        Q(content_type=indiv_ct) | Q(content_type__isnull=True)
                    )
                    .order_by("name")
                    .first()
                )
                print(
                    f"=== DEBUG: Default individual status: {default_individual_status} ==="
                )
            except Exception as e:
                print(f"=== DEBUG: Error getting default status: {e} ===")
                default_individual_status = None

            for index, individual_data in individuals_data.items():
                print(
                    f"=== DEBUG: Processing individual {index}: {individual_data} ==="
                )
                # If updating existing individual (id present), we don't require role
                is_update = bool(individual_data.get("id"))
                if not individual_data.get("full_name"):
                    print(f"=== DEBUG: Skipping individual {index} - no full_name ===")
                    continue

                if not is_update and not individual_data.get("role"):
                    print(f"=== DEBUG: Skipping individual {index} - no role for new individual ===")
                    continue

                # Get required fields (allow raw values; M2Ms handled by the form)
                individual_form_data = {
                    # If explicit id is provided, pass it through; otherwise omit
                    "id": individual_data.get("id"),
                    "full_name": individual_data.get("full_name"),
                    "tc_identity": individual_data.get("tc_identity") or None,
                    "birth_date": individual_data.get("birth_date") or None,
                    "icd11_code": individual_data.get("icd11_code") or None,
                    "council_date": individual_data.get("council_date") or None,
                    "diagnosis": individual_data.get("diagnosis") or None,
                    "diagnosis_date": individual_data.get("diagnosis_date") or None,
                    # explicit mother/father relations (single combobox -> user id)
                    "mother": individual_data.get("mother") or None,
                    "father": individual_data.get("father") or None,
                    # IMPORTANT: generic-combobox posts JSON list under the same field name
                    # so we pass it as-is; Django form field will parse list values for M2M
                    "institution": individual_data.get("institution"),
                    # HPO terms may arrive as JSON list; pass through
                    "hpo_terms": individual_data.get("hpo_term_ids") or individual_data.get("hpo_terms"),
                    # FKs and scalar fields
                    "status": individual_data.get("status"),
                    "family": family.id,
                    "is_index": individual_data.get("is_index") == "true",
                    "is_affected": individual_data.get("is_affected") == "true",
                }

                # Normalize M2M payloads coming as JSON strings from comboboxes
                try:
                    import json as _json
                except Exception:
                    _json = None

                # Institutions (ManyToMany) should be a list of IDs
                inst_val = individual_form_data.get("institution")
                if isinstance(inst_val, str):
                    try:
                        if _json and inst_val.strip().startswith("["):
                            parsed = _json.loads(inst_val)
                            if isinstance(parsed, list):
                                individual_form_data["institution"] = parsed
                        else:
                            # fallback: single value string -> single-item list
                            individual_form_data["institution"] = [inst_val]
                    except Exception:
                        individual_form_data["institution"] = [inst_val]

                # HPO terms (ManyToMany) can also arrive as a JSON string
                hpo_val = individual_form_data.get("hpo_terms")
                if isinstance(hpo_val, str):
                    try:
                        if _json and hpo_val.strip().startswith("["):
                            parsed = _json.loads(hpo_val)
                            if isinstance(parsed, list):
                                individual_form_data["hpo_terms"] = parsed
                            else:
                                individual_form_data.pop("hpo_terms", None)
                        else:
                            # if empty string or non-list, drop to avoid validation error
                            if not hpo_val.strip():
                                individual_form_data.pop("hpo_terms", None)
                            else:
                                individual_form_data["hpo_terms"] = [hpo_val]
                    except Exception:
                        individual_form_data.pop("hpo_terms", None)

                print(
                    f"=== DEBUG: Individual form data for {index}: {individual_form_data} ==="
                )

                # Create the individual
                from .forms import IndividualForm

                # Remove id if blank to avoid validation errors
                if not individual_form_data.get("id"):
                    individual_form_data.pop("id", None)

                # If status not provided, inject a default one
                if not individual_form_data.get("status") and default_individual_status:
                    individual_form_data["status"] = default_individual_status.id
                    print(
                        f"=== DEBUG: Added default status {default_individual_status.id} for individual {index} ==="
                    )

                # If updating, bind to instance so save() updates instead of creating
                individual_instance = None
                if is_update:
                    try:
                        individual_instance = Individual.objects.get(pk=int(individual_form_data.get("id")))
                    except Exception:
                        individual_instance = None
                if individual_instance:
                    # Remove id from form data for binding
                    individual_form_data.pop("id", None)
                    individual_form = IndividualForm(individual_form_data, instance=individual_instance)
                else:
                    individual_form = IndividualForm(individual_form_data)
                print(
                    f"=== DEBUG: Individual form is_valid: {individual_form.is_valid()} ==="
                )
                if individual_form.is_valid():
                    # Keep track of previous family for reassignment warnings
                    previous_family_id = None
                    if individual_instance:
                        previous_family_id = getattr(individual_instance, "family_id", None)

                    individual = individual_form.save(commit=False)
                    individual.created_by = request.user
                    individual.save()
                    individual_form.save_m2m()

                    print(
                        f"=== DEBUG: Individual {index} created successfully with ID: {individual.id} ==="
                    )
                    if individual_instance:
                        updated_individuals.append((index, individual))
                        # Detect reassignment to a different family
                        try:
                            if previous_family_id and previous_family_id != getattr(individual, "family_id", None):
                                reassigned_individuals.append((index, individual, previous_family_id))
                        except Exception:
                            pass
                    else:
                        created_individuals.append((index, individual))

                    # Store mother and father for later reference
                    role = individual_data.get("role", "")
                    if role == "mother":
                        mother_individual = individual
                        print(f"=== DEBUG: Individual {index} marked as mother ===")
                    elif role == "father":
                        father_individual = individual
                        print(f"=== DEBUG: Individual {index} marked as father ===")
                else:
                    print(
                        f"=== DEBUG: Individual form validation failed for {index}: {individual_form.errors} ==="
                    )

            print(
                f"=== DEBUG: Total individuals created: {len(created_individuals)} ==="
            )

            # No requirement for mother/father presence across multi-member families

            # Second pass: resolve mother/father from selection or free-typed query, then create/sync identifiers and notes
            for idx, individual in (list(created_individuals) + list(updated_individuals)):
                # Find the corresponding individual data directly by index
                individual_data = individuals_data.get(idx, {})
                # Resolve parent references after all individuals exist
                try:
                    def resolve_parent(val):
                        if not val:
                            return None
                        sval = str(val).strip()
                        if sval.isdigit():
                            return Individual.objects.filter(pk=int(sval)).first()
                        from .models import CrossIdentifier as _CI
                        ci = _CI.objects.filter(id_value=sval).first()
                        return getattr(ci, 'individual', None)

                    mother_val = individual_data.get("mother") or individual_data.get("mother_query")
                    father_val = individual_data.get("father") or individual_data.get("father_query")
                    m_obj = resolve_parent(mother_val)
                    f_obj = resolve_parent(father_val)
                    changed = False
                    if m_obj and individual.mother_id != m_obj.id:
                        individual.mother = m_obj
                        changed = True
                    if f_obj and individual.father_id != f_obj.id:
                        individual.father = f_obj
                        changed = True
                    if changed:
                        individual.save()
                except Exception:
                    pass

                # Create/Sync CrossIdentifier rows for this individual
                try:
                    idx_prefix = f"individuals[{idx}]"
                    # discover all rows present for this individual's ids
                    rows = set()
                    for key in request.POST.keys():
                        if key.startswith(f"{idx_prefix}[ids][") and key.endswith(
                            "][value]"
                        ):
                            try:
                                after_ids = key.split("[ids][", 1)[1]
                                row_str = after_ids.split("]", 1)[0]
                                rows.add(row_str)
                            except Exception:
                                continue
                    submitted_pairs = set()
                    for row in rows:
                        value_key = f"{idx_prefix}[ids][{row}][value]"
                        value = request.POST.get(value_key, "").strip()
                        type_key = f"{idx_prefix}[ids][{row}][type]"
                        type_id = request.POST.get(type_key, "").strip()
                        if value and type_id:
                            key = (int(type_id), value)
                            if key in submitted_pairs:
                                # skip duplicate within submitted payload
                                continue
                            try:
                                # Try exact match first
                                exact = CrossIdentifier.objects.filter(
                                    individual=individual,
                                    id_type_id=key[0],
                                    id_value=key[1],
                                ).first()
                                if exact:
                                    pass  # already correct
                                else:
                                    # See if there is an entry for this type with a different value → update one and remove extras
                                    same_type_qs = CrossIdentifier.objects.filter(
                                        individual=individual,
                                        id_type_id=key[0],
                                    ).order_by("id")
                                    first_same = same_type_qs.first()
                                    if first_same and (first_same.id_value or "").strip() != key[1]:
                                        first_same.id_value = key[1]
                                        first_same.save(update_fields=["id_value"])
                                        # remove other duplicates of this type not equal to new value
                                        same_type_qs.exclude(pk=first_same.pk).exclude(id_value=key[1]).delete()
                                        print(f"=== DEBUG: Updated CrossIdentifier for individual {idx}: type={type_id} new={value} ===")
                                    elif not first_same:
                                        CrossIdentifier.objects.create(
                                            individual=individual,
                                            id_type_id=key[0],
                                            id_value=key[1],
                                            created_by=request.user,
                                        )
                                        print(f"=== DEBUG: Created CrossIdentifier for individual {idx}: {type_id}={value} ===")
                                submitted_pairs.add(key)
                            except Exception as e:
                                print(
                                    f"=== DEBUG: Error creating CrossIdentifier for individual {idx}: {e} ==="
                                )
                                # Ignore malformed IDs silently for now
                                pass

                    # Removal sync: delete any existing identifiers for this individual
                    # that are not present in the submitted payload. If no id rows submitted, remove all.
                    try:
                        existing_cis = list(CrossIdentifier.objects.filter(individual=individual))
                        for ci in existing_cis:
                            pair = (int(ci.id_type_id), (ci.id_value or "").strip())
                            if pair not in submitted_pairs:
                                ci.delete()
                                print(
                                    f"=== DEBUG: Deleted CrossIdentifier for individual {idx}: {ci.id_type_id}={ci.id_value} ==="
                                )
                    except Exception as e:
                        print(f"=== DEBUG: Error syncing CrossIdentifiers for individual {idx}: {e} ===")
                except Exception as e:
                    print(
                        f"=== DEBUG: Error processing IDs for individual {idx}: {e} ==="
                    )
                    # If parsing fails, skip creating IDs for this individual
                    pass

                # Create Note rows for this individual
                try:
                    idx_prefix = f"individuals[{idx}]"
                    print(
                        f"=== DEBUG: Processing notes for individual {idx} with prefix: {idx_prefix} ==="
                    )

                    # discover all rows present for this individual's notes
                    note_rows = set()
                    print(f"=== DEBUG: All POST keys for notes processing: ===")
                    for key in request.POST.keys():
                        if key.startswith(f"{idx_prefix}[notes][") and key.endswith(
                            "][content]"
                        ):
                            print(f"  Found note key: {key}")
                            try:
                                after_notes = key.split("[notes][", 1)[1]
                                row_str = after_notes.split("]", 1)[0]
                                note_rows.add(row_str)
                                print(f"  Extracted row: {row_str}")
                            except Exception as e:
                                print(f"  Error parsing key {key}: {e}")
                                continue

                    print(
                        f"=== DEBUG: Total note rows found for individual {idx}: {len(note_rows)} ==="
                    )
                    print(f"=== DEBUG: Note rows set: {note_rows} ===")

                    for row in note_rows:
                        content_key = f"{idx_prefix}[notes][{row}][content]"
                        content = request.POST.get(content_key, "").strip()
                        print(f"=== DEBUG: Processing note row {row}: ===")
                        print(f"  Content key: {content_key}")
                        print(f"  Raw content: '{content}'")
                        print(f"  Content length: {len(content)}")
                        print(f"  Content trimmed: '{content.strip()}'")

                        if content:
                            try:
                                print(
                                    f"=== DEBUG: Creating Note object for individual {idx}, row {row} ==="
                                )
                                print(f"  Content: {content[:100]}...")
                                print(f"  User: {request.user}")
                                print(
                                    f"  Content type: {ContentType.objects.get_for_model(Individual)}"
                                )
                                print(f"  Object ID: {individual.id}")

                                Note.objects.create(
                                    content=content,
                                    user=request.user,
                                    content_type=ContentType.objects.get_for_model(
                                        Individual
                                    ),
                                    object_id=individual.id,
                                )
                                print(
                                    f"=== DEBUG: Successfully created Note for individual {idx}, row {row}: {content[:50]}... ==="
                                )
                            except Exception as e:
                                print(
                                    f"=== DEBUG: Error creating Note for individual {idx}, row {row}: {e} ==="
                                )
                                print(f"  Exception type: {type(e).__name__}")
                                import traceback

                                traceback.print_exc()
                                # Ignore malformed notes silently for now
                                pass
                        else:
                            print(
                                f"=== DEBUG: Skipping empty note for individual {idx}, row {row} ==="
                            )
                except Exception as e:
                    print(
                        f"=== DEBUG: Error processing notes for individual {idx}: {e} ==="
                    )
                    print(f"  Exception type: {type(e).__name__}")
                    import traceback

                    traceback.print_exc()
                    # If parsing fails, skip creating notes for this individual
                    pass

                # Generic: attach any ManyToMany posted as JSON lists per-individual
                try:
                    idx_prefix = f"individuals[{idx}]"
                    for m2m_field in individual._meta.many_to_many:
                        field_name = m2m_field.name
                        candidate_params = [f"{idx_prefix}[{field_name}_ids]"]
                        if field_name.endswith("s"):
                            candidate_params.append(
                                f"{idx_prefix}[{field_name[:-1]}_ids]"
                            )
                        json_val = None
                        for pname in candidate_params:
                            json_val = request.POST.get(pname)
                            if json_val:
                                break
                        if not json_val:
                            continue
                        try:
                            id_list = json.loads(json_val)
                        except Exception:
                            id_list = [v for v in (json_val or "").split(",") if v]
                        if isinstance(id_list, list) and id_list:
                            related_model = m2m_field.remote_field.model
                            related_qs = related_model.objects.filter(pk__in=id_list)
                            getattr(individual, field_name).set(related_qs)
                except Exception:
                    pass

            # Per-individual optional Task creation
            try:
                from django.utils.dateparse import parse_datetime
                task_ct = ContentType.objects.get_for_model(Individual)
                for idx, individual in created_individuals:
                    prefix = f"individuals[{idx}]"
                    if not request.POST.get(f"{prefix}[create_task]"):
                        continue
                    title = request.POST.get(f"{prefix}[task-title]") or f"Follow-up for {individual}"
                    description = request.POST.get(f"{prefix}[task-description]", "")
                    assigned_to_id = request.POST.get(f"{prefix}[task-assigned_to]") or getattr(request.user, "id", None)
                    due_raw = request.POST.get(f"{prefix}[task-due_date]")
                    due_dt = parse_datetime(due_raw) if due_raw else None
                    priority = request.POST.get(f"{prefix}[task-priority]") or "medium"
                    status_id = request.POST.get(f"{prefix}[task-status]")
                    if not status_id:
                        active = Status.objects.filter(name__iexact="active").first()
                        status_id = getattr(active, "id", None) or getattr(Status.objects.first(), "id", None)
                    project_id = request.POST.get(f"{prefix}[task-project]") or None

                    task_kwargs = {
                        "title": title,
                        "description": description,
                        "assigned_to_id": assigned_to_id,
                        "created_by": request.user,
                        "due_date": due_dt,
                        "priority": priority,
                        "status_id": status_id,
                        "content_type": task_ct,
                        "object_id": individual.pk,
                    }
                    if project_id:
                        task_kwargs["project_id"] = project_id
                    if task_kwargs.get("assigned_to_id") and task_kwargs.get("status_id"):
                        Task.objects.create(**task_kwargs)
            except Exception:
                pass

            # Return success response
            if request.htmx:
                response = render(
                    request,
                    "lab/crud.html#family-create-success",
                    {
                        "family": family,
                        "created_individuals": [ind for _, ind in created_individuals],
                        "updated_individuals": [ind for _, ind in updated_individuals],
                        "count_created": len(created_individuals),
                        "count_updated": len(updated_individuals),
                        "reassigned_individuals": reassigned_individuals,
                        "family_was_created": family_was_created,
                    },
                )
                # Emit events so UI components listening for created Individuals refresh
                try:
                    created_pks = [ind.id for _, ind in created_individuals]
                    updated_pks = [ind.id for _, ind in updated_individuals]
                    trigger_payload = {
                        # Created events
                        "created-Individual": {
                            "pks": created_pks,
                            "count": len(created_pks),
                            "family_pk": getattr(family, "pk", None),
                        },
                        "create-individual": {
                            "pks": created_pks,
                            "count": len(created_pks),
                            "family_pk": getattr(family, "pk", None),
                        },
                        # Updated events
                        "updated-Individual": {
                            "pks": updated_pks,
                            "count": len(updated_pks),
                            "family_pk": getattr(family, "pk", None),
                        },
                        # Also refresh global filters-dependent UI
                        "filters-updated": True,
                    }
                    # Add object-specific events per individual
                    for pk in created_pks:
                        trigger_payload[f"created-Individual-{pk}"] = True
                        trigger_payload[f"create-individual-{pk}"] = True
                    for pk in updated_pks:
                        trigger_payload[f"updated-Individual-{pk}"] = True
                    response["HX-Trigger"] = json.dumps(trigger_payload)
                except Exception:
                    response["HX-Trigger"] = "created-Individual"
                return response
            else:
                # Redirect to the family detail page
                return redirect(
                    f"/detail/?app_label=lab&model_name=Family&pk={family.pk}"
                )
        except Exception as e:
            print(f"Error in family_create_segway: {e}")
            import traceback

            traceback.print_exc()
            if request.htmx:
                return render(
                    request,
                    "lab/crud.html#family-create-error",
                    {"error": str(e)},
                )
            else:
                return HttpResponseBadRequest(f"Error creating family: {str(e)}")

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
                # For per-individual task selects
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
    print("VIEWS PLOTS")
    return render(request, "lab/index.html", {"activeItem": "plots"})


def map_page(request):
    """Render the map page template."""
    return render(request, "lab/map.html")


@login_required
def map_view(request):
    """
    Generate a scatter map visualization showing institutions of filtered individuals.
    """
    print(f"=== DEBUG: Map view request: {request} ===")
    print(f"=== DEBUG: Map view request GET: {request.GET} ===")
    
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