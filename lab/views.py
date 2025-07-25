from django.apps import apps
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.views.decorators.http import require_http_methods, require_GET
from django.contrib.contenttypes.models import ContentType
from .models import (
    Individual,
    Sample,
    TestType,
    SampleType,
    Status,
    Task,
    Note,
    Family,
    Test,
    Project,
    Analysis,
    AnalysisType,
    Institution,
)
from .forms import (
    IndividualForm,
    SampleForm,
    TestTypeForm,
    SampleTypeForm,
    TaskForm,
    NoteForm,
    ProjectForm,
    TestForm,
)
from django.db.models import Q
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.contrib.auth.models import User
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.http import QueryDict
from ontologies.models import Term

import networkx as nx
import urllib.request
import fastobo
import warnings
import plotly.graph_objects as go
import json


@login_required
def dashboard(request):
    """Dashboard view that serves as the main landing page"""
    # Gather some summary statistics for the dashboard
    context = {
        "individual_count": Individual.objects.count(),
        "sample_count": Sample.objects.count(),
        "test_count": Test.objects.count(),
        "analysis_count": Analysis.objects.count(),
        "pending_tasks": Task.objects.filter(is_completed=False).count(),
    }

    # If it's an HTMX request, return just the requested partial
    if request.headers.get("HX-Request"):
        partial = request.GET.get("partial", "dashboard-index")
        if partial == "dashboard-stats":
            return render(request, "lab/dashboard.html#dashboard-stats", context)
        elif partial == "dashboard-activity":
            return render(request, "lab/dashboard.html#dashboard-activity", context)
        elif partial == "dashboard-charts":
            return render(request, "lab/dashboard.html#dashboard-charts", context)
        else:
            return render(request, "lab/dashboard.html#dashboard-index", context)

    # For regular requests, return the full page
    return render(request, "lab/dashboard.html", context)


@login_required
def select_search(request):
    """
    Generic search endpoint for select2-like dropdown functionality.

    Parameters:
    - model: The model name to search (e.g., 'Individual', 'SampleType')
    - field: The field to search (default is 'name')
    - search: The search query
    - page: The page number for pagination (optional)

    Returns:
    - Rendered HTML with search results
    """
    search_query = request.GET.get("search", "").strip()
    model_name = request.GET.get("model", "")
    field_name = request.GET.get("field", "name")
    page = request.GET.get("page", 1)

    # Protect against 'undefined' values coming from JavaScript
    if search_query == "undefined":
        search_query = ""
    if model_name == "undefined":
        return render(
            request,
            "lab/components/search_results.html",
            {"error": "Invalid model parameter"},
        )
    if field_name == "undefined":
        field_name = "name"  # Default to name field

    try:
        # Get the model class dynamically
        model = apps.get_model(app_label="lab", model_name=model_name)

        # Build the query for the specified field
        filter_kwargs = {}
        if search_query:
            filter_kwargs[f"{field_name}__icontains"] = search_query
            queryset = model.objects.filter(**filter_kwargs)
        else:
            queryset = model.objects.all()

        # Customize queryset based on model
        if model_name == "Individual":
            # Apply any specific filtering for Individual model
            queryset = queryset.order_by("lab_id")
        else:
            # Default ordering
            queryset = queryset.order_by(field_name)

        # Apply pagination
        paginator = Paginator(queryset, 10)  # 10 items per page
        page_obj = paginator.get_page(page)

        # Format items for the response
        items = []
        for item in page_obj:
            # Handle different models - customize the text display based on model
            if model_name == "Individual":
                text = item.lab_id
                if hasattr(request.user, "has_perm") and request.user.has_perm(
                    "lab.view_individual_sensitive_data"
                ):
                    text = f"{item.lab_id} ({item.full_name})"
                items.append({"id": item.id, "text": text})
            elif hasattr(item, "name"):
                items.append({"id": item.id, "text": item.name})
            elif model_name == "Family" and hasattr(item, "family_id"):
                items.append({"id": item.id, "text": item.family_id})
            else:
                # Default fallback
                items.append({"id": item.id, "text": str(item)})

        context = {
            "items": items,
            "query": search_query,
            "paginator": paginator,
            "page_obj": page_obj,
        }

        return render(request, "lab/components/search_results.html", context)

    except (LookupError, ValueError, AttributeError) as e:
        # Return error in development, generic message in production
        if settings.DEBUG:
            error_message = str(e)
        else:
            error_message = "An error occurred while searching."

        return render(
            request, "lab/components/search_results.html", {"error": error_message}
        )


@login_required
def individual_index(request):
    individuals = Individual.objects.all()

    # Get all the necessary data for filters
    context = {
        "individuals": individuals,
        "individual_statuses": Status.objects.filter(
            content_type=ContentType.objects.get_for_model(Individual)
        ),
        "families": Family.objects.all(),
        "tests": Test.objects.all(),
        "test_statuses": Status.objects.filter(
            content_type=ContentType.objects.get_for_model(Test)
        ),
    }

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        # The specific partial to return depends on what was requested
        if "search" in request.path:
            return render(request, "lab/individual/index.html#individual-list", context)
        return render(request, "lab/individual/index.html#individual-index", context)

    # For regular requests, return the full page
    return render(request, "lab/individual/index.html", context)


# TODO: implement
@login_required
@permission_required("lab.add_individual")
def individual_create(request):
    if request.method == "POST":
        form = IndividualForm(request.POST)
        if form.is_valid():
            individual = form.save(commit=False)
            individual.created_by = request.user
            individual.save()
            individuals = Individual.objects.all()
            return TemplateResponse(
                request, "lab/individual/list.html", {"individuals": individuals}
            )
    return TemplateResponse(
        request,
        "lab/individual/edit.html",
        {"individual": None, "families": Family.objects.all()},
    )


@login_required
@permission_required("lab.change_individual")
def individual_edit(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    if request.method == "POST":
        form = IndividualForm(request.POST, instance=individual)
        if form.is_valid():
            individual = form.save()
            # If it's an HTMX request, return the detail partial
            if request.headers.get("HX-Request"):
                return TemplateResponse(
                    request,
                    "lab/individual/detail.html#individual-detail",
                    {"individual": individual},
                )
            # Otherwise return the card view
            return TemplateResponse(
                request, "lab/individual/card.html", {"individual": individual}
            )

    # For GET requests, return the edit form
    context = {
        "individual": individual,
        "families": Family.objects.all(),
        "form": IndividualForm(instance=individual),
    }

    # If it's an HTMX request, return just the form partial
    if request.headers.get("HX-Request"):
        return TemplateResponse(
            request, "lab/individual/edit.html#individual-edit-form", context
        )

    # Otherwise return the full edit page
    return TemplateResponse(request, "lab/individual/edit.html", context)


@login_required
@permission_required("lab.delete_individual")
@require_http_methods(["DELETE"])
def individual_delete(request, pk):
    individual = get_object_or_404(Individual, pk=pk)
    individual.delete()
    return HttpResponse(status=200)


@login_required
def individual_search(request):
    queryset = Individual.objects.all()

    # Status filter
    status_id = request.POST.get("status")
    if status_id:
        queryset = queryset.filter(status_id=status_id)

    # Lab ID filter - now supports multiple IDs
    lab_ids = request.POST.get("lab_id", "")
    if lab_ids:
        # Split comma-separated IDs
        lab_id_list = lab_ids.split(",")
        queryset = queryset.filter(id__in=lab_id_list)

    # Test filter
    test_id = request.POST.get("test")
    if test_id:
        # Check if it's a comma-separated list
        if "," in test_id:
            test_ids = test_id.split(",")
            queryset = queryset.filter(samples__test__test_id__in=test_ids)
        else:
            queryset = queryset.filter(samples__test__test_id=test_id)

    # Sample Test Status filter
    test_status_id = request.POST.get("test_status")
    if test_status_id:
        queryset = queryset.filter(samples__test__status_id=test_status_id)

    # Family ID filter - now supports multiple families
    family_ids = request.POST.get("family")
    if family_ids:
        family_id_list = family_ids.split(",")
        queryset = queryset.filter(family_id__in=family_id_list)

    # ICD11 code filter
    icd11_code = request.POST.get("icd11_code")
    if icd11_code:
        queryset = queryset.filter(icd11_code__icontains=icd11_code)

    # HPO codes filter
    hpo_codes = request.POST.get("hpo_codes")
    if hpo_codes:
        queryset = queryset.filter(hpo_codes__icontains=hpo_codes)

    # Remove duplicates and order results
    queryset = queryset.distinct().order_by("lab_id")

    # Get total count before pagination
    total_count = queryset.count()

    # Paginate results
    page = request.POST.get("page", 1)
    paginator = Paginator(queryset, 12)  # 12 items per page
    individuals = paginator.get_page(page)
    return TemplateResponse(
        request,
        "lab/individual/index.html#individual-list",
        {
            "individuals": individuals,
            "total_count": total_count,
            "individual_statuses": Status.objects.filter(
                content_type=ContentType.objects.get_for_model(Individual)
            ),
            "test_statuses": Status.objects.filter(
                content_type=ContentType.objects.get_for_model(Test)
            ),
            "filters": {  # Pass filters for subsequent page loads
                "status": status_id,
                "test": request.POST.get("test"),
                "test_status": request.POST.get("test_status"),
                "lab_id": request.POST.get("lab_id"),
                "family": request.POST.get("family"),
                "icd11_code": request.POST.get("icd11_code"),
                "hpo_codes": request.POST.get("hpo_codes"),
            },
        },
    )


@login_required
def individual_detail(request, pk):
    """Detailed view for an individual with all related data"""
    individual = get_object_or_404(Individual, pk=pk)

    # Prefetch related data for efficiency
    individual.samples.prefetch_related("tests", "sample_type", "status")
    individual.tasks.prefetch_related("assigned_to", "completed_by", "target_status")
    individual.notes.prefetch_related("user")
    individual.status_logs.prefetch_related(
        "changed_by", "previous_status", "new_status"
    )

    context = {
        "individual": individual,
    }

    # If it's an HTMX request, return just the detail content
    if request.headers.get("HX-Request"):
        return render(request, "lab/individual/detail.html#individual-detail", context)

    # For regular requests, return the full page
    return render(request, "lab/individual/detail.html", context)


@login_required
def sample_list(request):
    """Sample list view"""
    # Get all samples with related data
    samples = (
        Sample.objects.all()
        .select_related("individual", "sample_type", "status", "isolation_by")
        .prefetch_related("tests", "tasks", "notes")
    )

    # Get data for filters
    context = {
        "samples": samples,
        "individuals": Individual.objects.all(),
        "sample_types": SampleType.objects.all(),
        "sample_statuses": Status.objects.filter(
            content_type=ContentType.objects.get_for_model(Sample)
        ),
    }

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        # The specific partial to return depends on what was requested
        if "search" in request.path:
            return render(request, "lab/sample/index.html#sample-list", context)
        return render(request, "lab/sample/index.html#sample-index", context)

    # For regular requests, return the full page
    return render(request, "lab/sample/index.html", context)


@login_required
def sample_search(request):
    """Search samples with filters."""
    if request.headers.get("HX-Request"):
        # Get filter parameters
        status = request.POST.get("status")
        sample_type = request.POST.get("sample_type")
        individual = request.POST.get("individual")
        date_from = request.POST.get("date_from")
        date_to = request.POST.get("date_to")
        page = request.POST.get("page", 1)

        # Build query
        samples = Sample.objects.all()

        if status:
            samples = samples.filter(status_id=status)
        if sample_type:
            samples = samples.filter(sample_type_id=sample_type)
        if individual:
            samples = samples.filter(individual_id=individual)
        if date_from:
            samples = samples.filter(receipt_date__gte=date_from)
        if date_to:
            samples = samples.filter(receipt_date__lte=date_to)

        # Order by created_at descending
        samples = samples.order_by("-created_at")

        # Paginate
        paginator = Paginator(samples, 12)
        samples = paginator.get_page(page)

        # Prepare context
        context = {
            "samples": samples,
            "filters": {
                "status": status,
                "sample_type": sample_type,
                "individual": individual,
                "date_from": date_from,
                "date_to": date_to,
            },
        }

        # Return partial for HTMX request
        return render(request, "lab/sample/list.html#sample-list", context)

    # For regular requests, return the full search page
    context = {
        "sample_statuses": SampleStatus.objects.all(),
        "sample_types": SampleType.objects.all(),
        "individuals": Individual.objects.all(),
    }
    return render(request, "lab/sample/search.html", context)


@login_required
def sample_detail(request, pk):
    """Detailed view for a sample with all related data"""
    # Get sample with all related data
    sample = (
        Sample.objects.select_related(
            "individual",
            "sample_type",
            "status",
            "isolation_by",
            "created_by",
        )
        .prefetch_related(
            "tests",
            "tasks",
            "notes",
            "status_logs",
            "tests",
            "tests__test_type",
            "tests__status",
            "tests__performed_by",
        )
        .get(pk=pk)
    )

    # Get the active tab from query params or default to 'notes'
    active_tab = request.GET.get("tab", "notes")

    # If card_only=true is in the query params, return just the card
    if request.GET.get("card_only") == "true":
        return TemplateResponse(request, "lab/sample/card.html", {"sample": sample})

    context = {
        "sample": sample,
        "activeTab": active_tab,
    }

    if request.headers.get("HX-Request"):
        return TemplateResponse(
            request, "lab/sample/detail.html#sample-detail", context
        )
    return TemplateResponse(request, "lab/sample/detail.html", context)


@login_required
@permission_required("lab.add_sample")
def sample_create(request):
    """Create a new sample"""
    if request.method == "POST":
        form = SampleForm(request.POST)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.created_by = request.user

            # Set the sending institution (assuming default for now)
            if (
                not hasattr(sample, "sending_institution")
                or not sample.sending_institution
            ):
                # Get the first institution or create a default one
                try:
                    sample.sending_institution = Institution.objects.first()
                except Institution.DoesNotExist:
                    # Create a default institution if none exists
                    sample.sending_institution = Institution.objects.create(
                        name="Default Institution"
                    )

            sample.save()
            form.save_m2m()  # Save many-to-many relationships

            # If it's an HTMX request, return the detail partial
            if request.headers.get("HX-Request"):
                return render(
                    request,
                    "lab/sample/detail.html#sample-detail",
                    {"sample": sample},
                )

            # Otherwise redirect to the detail page
            return redirect("lab:sample_detail", pk=sample.pk)

    # For GET requests, prepare the form
    context = {
        "form": SampleForm(),
        "individuals": Individual.objects.all(),
        "sample_types": SampleType.objects.all(),
        "sample_statuses": Status.objects.filter(
            content_type=ContentType.objects.get_for_model(Sample)
        ),
    }

    # If it's an HTMX request, return just the form partial
    if request.headers.get("HX-Request"):
        return render(request, "lab/sample/create.html#sample-create", context)

    # Otherwise return the full create page
    return render(request, "lab/sample/create.html", context)


@login_required
@permission_required("lab.change_sample")
def sample_edit(request, pk):
    """Edit an existing sample"""
    sample = get_object_or_404(Sample, pk=pk)

    if request.method == "POST":
        form = SampleForm(request.POST, instance=sample)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.updated_by = request.user
            sample.save()
            form.save_m2m()  # Save many-to-many relationships

            # If it's an HTMX request, return the detail partial
            if request.headers.get("HX-Request"):
                return render(
                    request,
                    "lab/sample/detail.html#sample-detail",
                    {"sample": sample},
                )

            # Otherwise redirect to the detail page
            return redirect("lab:sample_detail", pk=sample.pk)

    # For GET requests, prepare the form
    context = {
        "form": SampleForm(instance=sample),
        "sample": sample,
        "individuals": Individual.objects.all(),
        "sample_types": SampleType.objects.all(),
        "sample_statuses": Status.objects.filter(
            content_type=ContentType.objects.get_for_model(Sample)
        ),
    }

    # If it's an HTMX request, return just the form partial
    if request.headers.get("HX-Request"):
        return render(request, "lab/sample/edit.html#sample-edit", context)

    # Otherwise return the full edit page
    return render(request, "lab/sample/edit.html", context)


@login_required
@permission_required("lab.delete_sample")
def sample_delete(request, pk):
    """Delete a sample"""
    sample = get_object_or_404(Sample, pk=pk)

    if request.method == "POST":
        sample.delete()

        # If it's an HTMX request, return an empty response to remove the element
        if request.headers.get("HX-Request"):
            return HttpResponse("")

        # Otherwise redirect to the list page
        return redirect("lab:samples")

    # For GET requests, prepare the confirmation form
    context = {
        "sample": sample,
    }

    # If it's an HTMX request, return just the form partial
    if request.headers.get("HX-Request"):
        return render(request, "lab/sample/delete.html#sample-delete", context)

    # Otherwise return the full delete page
    return render(request, "lab/sample/delete.html", context)


# Sample Test Views


@login_required
@permission_required("lab.add_test")
def test_create(request):
    """Create a new test record for a sample"""
    sample_id = request.GET.get("sample")
    sample = get_object_or_404(Sample, pk=sample_id)

    if request.method == "POST":
        # Handle the form submission
        test_id = request.POST.get("test_type")
        status_id = request.POST.get("status")
        performed_date = request.POST.get("performed_date")

        if test_id and status_id and performed_date:
            test_type = get_object_or_404(Test_Type, pk=test_id)
            status = get_object_or_404(Status, pk=status_id)

            # Create the sample test
            test = Test.objects.create(
                sample=sample,
                test_type=test_type,
                status=status,
                performed_date=performed_date,
                performed_by=request.user,
            )

            return TemplateResponse(request, "lab/tests/list.html", {"sample": sample})

    # For GET requests, render the form
    test_content_type = ContentType.objects.get_for_model(Test)

    return TemplateResponse(
        request,
        "lab/samples/test_form.html",
        {
            "sample": sample,
            "tests": Test.objects.all(),
            "statuses": Status.objects.filter(content_type=test_content_type),
        },
    )


@login_required
@permission_required("lab.change_test")
def test_edit(request, pk):
    sampletest = get_object_or_404(Test, pk=pk)

    if request.method == "GET":
        form = TestForm(instance=sampletest)
        return TemplateResponse(
            request,
            "lab/samples/test_edit_form.html",
            {"form": form, "sampletest": sampletest},
        )

    elif request.method == "PUT":
        # Parse the PUT data
        put_data = QueryDict(request.body)
        form = TestForm(put_data, instance=sampletest)
        if form.is_valid():
            sampletest = form.save()
            # Return the updated card view
            return TemplateResponse(
                request, "lab/tests/card.html", {"sampletest": sampletest}
            )
        else:
            # Return the form with errors
            return TemplateResponse(
                request,
                "lab/samples/test_edit_form.html",
                {"form": form, "sampletest": sampletest},
                status=422,
            )


@login_required
@permission_required("lab.delete_test")
@require_http_methods(["DELETE"])
def test_delete(request, pk):
    """Delete a test record"""
    test = get_object_or_404(Test, pk=pk)
    test.delete()
    return HttpResponse(status=200)


@login_required
def note_list(request, model, pk):
    content_type = ContentType.objects.get(app_label="lab", model=model)
    obj = content_type.get_object_for_this_type(pk=pk)
    notes = obj.notes.all()
    return TemplateResponse(
        request, "lab/note/note_list.html", {"notes": notes, "content_object": obj}
    )


@login_required
@require_http_methods(["DELETE"])
def note_delete(request, pk):
    note = get_object_or_404(Note, pk=pk)
    note.delete()
    return HttpResponse(status=200)


@login_required
def test_list(request):
    tests = Test.objects.all()

    # Get all the necessary data for filters
    context = {
        "tests": tests,
        "test_statuses": Status.objects.filter(
            content_type=ContentType.objects.get_for_model(Test)
        ),
        "test_types": TestType.objects.all(),
        "individuals": Individual.objects.all(),
    }

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        # The specific partial to return depends on what was requested
        if "search" in request.path:
            return render(request, "lab/test/index.html#test-list", context)
        return render(request, "lab/test/index.html#test-index", context)

    # For regular requests, return the full page
    return render(request, "lab/test/index.html", context)


@login_required
@permission_required("lab.add_test")
def test_type_create(request):
    """Create a new test_type, associated with a test"""
    sample = None
    if sample_id := request.GET.get("sample"):
        sample = get_object_or_404(Sample, pk=sample_id)

    if request.method == "POST":
        form = TestTypeForm(request.POST)
        if form.is_valid():
            test = form.save(commit=False)
            test.created_by = request.user
            test.save()

            # If we have a sample, create a Test
            if sample:
                Test.objects.create(
                    sample=sample,
                    test=test,
                    performed_date=timezone.now().date(),
                    performed_by=request.user,
                    status=Status.objects.get(name="Pending"),
                )
                return redirect("lab:sample_detail", pk=sample.pk)

            return redirect("lab:test_list")
    else:
        form = TestTypeForm()

    return TemplateResponse(
        request,
        "lab/tests/create.html",
        {
            "form": form,
            "sample": sample,
        },
    )


@login_required
@permission_required("lab.change_test")
def test_type_edit(request, pk):
    test_type = get_object_or_404(TestType, pk=pk)
    if request.method == "POST":
        form = TestTypeForm(request.POST, instance=test_type)
        if form.is_valid():
            test_type = form.save()
            return TemplateResponse(
                request, "lab/test_type/card.html", {"test_type": test_type}
            )
    return TemplateResponse(
        request, "lab/test_type/edit.html", {"test_type": test_type}
    )


@login_required
@permission_required("lab.delete_test")
@require_http_methods(["DELETE"])
def test_type_delete(request, pk):
    test_type = get_object_or_404(TestType, pk=pk)
    test_type.delete()
    return HttpResponse(status=200)


@login_required
def test_type_search(request):
    query = request.GET.get("q", "")
    test_types = TestType.objects.filter(name__icontains=query)
    return TemplateResponse(
        request, "lab/test_type/list.html", {"test_types": test_types}
    )


@login_required
def sample_type_list(request):
    sample_types = SampleType.objects.all()
    template = "lab/sample_type/list.html"
    context = {"sample_types": sample_types}

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        return TemplateResponse(request, template, contenxt)

    # Otherwise, redirect to the main app with sample_types view
    return render(request, template, context)


@login_required
@permission_required("lab.add_sampletype")
def sample_type_create(request):
    if request.method == "POST":
        form = SampleTypeForm(request.POST)
        if form.is_valid():
            sample_type = form.save(commit=False)
            sample_type.created_by = request.user
            sample_type.save()
            # Return the card view instead of the list
            return TemplateResponse(
                request, "lab/sample_type/card.html", {"sample_type": sample_type}
            )

    # For GET requests, check if it's a cancel action
    if request.headers.get("HX-Request") and request.GET.get("action") == "cancel":
        # Return an empty div that will be removed
        return HttpResponse("")

    # For normal GET requests, return the form
    return TemplateResponse(request, "lab/sample_type/edit.html", {"sample_type": None})


@login_required
@permission_required("lab.change_sampletype")
def sample_type_edit(request, pk):
    sample_type = get_object_or_404(SampleType, pk=pk)
    if request.method == "POST":
        form = SampleTypeForm(request.POST, instance=sample_type)
        if form.is_valid():
            sample_type = form.save()
            return TemplateResponse(
                request, "lab/sample_type/card.html", {"sample_type": sample_type}
            )
    return TemplateResponse(
        request, "lab/sample_type/edit.html", {"sample_type": sample_type}
    )


@login_required
@permission_required("lab.delete_sampletype")
@require_http_methods(["DELETE"])
def sample_type_delete(request, pk):
    """Delete a sample type"""
    sample_type = get_object_or_404(SampleType, pk=pk)
    sample_type.delete()
    return HttpResponse(status=200)


@login_required
def sample_type_search(request):
    query = request.GET.get("q", "")
    sample_types = SampleType.objects.filter(name__icontains=query)
    # Return the same list template but only the grid will be swapped due to hx-select
    return TemplateResponse(
        request, "lab/sample_type/list.html", {"sample_types": sample_types}
    )


@login_required
def task_index(request):
    """List all tasks with filtering options"""
    # Get filter parameters
    project_id = request.GET.get("project")
    status = request.GET.get("status", "open")
    assigned_to = request.GET.get("assigned_to")
    page = request.GET.get("page", 1)

    # Base queryset
    tasks = Task.objects.select_related(
        "project",
        "assigned_to",
        "created_by",
    )

    # Apply filters
    if project_id:
        tasks = tasks.filter(project_id=project_id)
    if status == "open":
        tasks = tasks.filter(is_completed=False)
    elif status == "completed":
        tasks = tasks.filter(is_completed=True)
    elif status == "all":
        pass  # No filter needed

    if assigned_to == "me":
        tasks = tasks.filter(assigned_to=request.user)
    elif assigned_to:
        tasks = tasks.filter(assigned_to_id=assigned_to)

    # Get all projects for the filter dropdown
    projects = Project.objects.all()

    # Get all users for the assigned to filter
    users = User.objects.filter(is_active=True)

    # Paginate tasks
    paginator = Paginator(tasks, 10)  # Show 10 tasks per page
    try:
        tasks = paginator.page(page)
    except PageNotAnInteger:
        tasks = paginator.page(1)
    except EmptyPage:
        tasks = paginator.page(paginator.num_pages)

    # Prepare context
    context = {
        "tasks": tasks,
        "projects": projects,
        "users": users,
        "current_filters": {
            "project": project_id,
            "status": status,
            "assigned_to": assigned_to,
        },
    }

    # If it's an HTMX request, return just the list partial
    if request.headers.get("HX-Request"):
        return render(request, "lab/task/list.html#task-list", context)

    # Otherwise return the full page
    return render(request, "lab/task/list.html", context)


@login_required
def task_create(request, model=None, pk=None):
    """Create a task, optionally associated with an object and/or project"""
    content_object = None
    content_type = None

    # If model and pk provided, get the related object
    if model and pk:
        content_type = get_object_or_404(ContentType, app_label="lab", model=model)
        content_object = get_object_or_404(content_type.model_class(), pk=pk)

    if request.method == "POST":
        form = TaskForm(request.POST, content_object=content_object)
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user

            # Set the content object if we have one
            if content_type and content_object:
                task.content_type = content_type
                task.object_id = pk

            task.save()

            # Determine where to redirect based on the context
            if request.headers.get("HX-Request"):
                return TemplateResponse(
                    request, "lab/task/task_card.html", {"task": task}
                )

            if task.project:
                return redirect("lab:project_detail", pk=task.project.pk)

            return redirect("lab:task_list")
    else:
        # Get the project_id from query params if it exists
        project_id = request.GET.get("project")
        initial_data = {}

        if project_id:
            initial_data["project"] = project_id

        form = TaskForm(content_object=content_object, initial=initial_data)

    # Determine template based on context
    if request.headers.get("HX-Request"):
        template = "lab/task/task_form.html"
    else:
        template = "lab/task/create.html"

    return TemplateResponse(
        request,
        template,
        {
            "form": form,
            "content_object": content_object,
            "model": model,
            "pk": pk,
            "projects": Project.objects.all(),
        },
    )


@login_required
def task_create_standalone(request):
    """Create a task not associated with any specific object"""
    # Handle cancel action
    if request.headers.get("HX-Request") and request.GET.get("action") == "cancel":
        return HttpResponse("")

    if request.method == "POST":
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user
            task.save()

            # If it's an HTMX request, return the task card
            if request.headers.get("HX-Request"):
                return TemplateResponse(
                    request, "lab/task/task_card.html", {"task": task}
                )

            return redirect("lab:task_list")

    # For GET requests, prepare the form
    form = TaskForm()

    # Make sure target_status field shows all available statuses for standalone tasks
    form.fields["target_status"].queryset = Status.objects.all()

    return TemplateResponse(request, "lab/task/create.html", {"form": form})


@login_required
def task_complete(request, pk):
    """Mark a task as complete and update the related object's status"""
    task = get_object_or_404(Task, pk=pk)

    if request.method == "POST":
        notes = request.POST.get("notes", "")
        success = task.complete(request.user, notes=notes)

        if success:
            return TemplateResponse(request, "lab/task/task_card.html", {"task": task})

    return HttpResponse(status=400)


@login_required
def my_tasks(request):
    """View for a user to see their assigned tasks"""
    tasks = Task.objects.filter(
        assigned_to=request.user, is_completed=False
    ).select_related("content_type", "assigned_to", "target_status")

    return TemplateResponse(request, "lab/task/my_tasks.html", {"tasks": tasks})


@login_required
def task_search(request):
    """Search tasks by title or description"""
    query = request.GET.get("q", "")

    # Base queryset - filter by the search query
    tasks = Task.objects.filter(
        Q(title__icontains=query) | Q(description__icontains=query)
    )
    # If user is not staff/admin, limit to tasks they created or are assigned to them
    if not request.user.is_staff:
        tasks = tasks.filter(Q(assigned_to=request.user) | Q(created_by=request.user))
    else:
        tasks = tasks.all()

    # Select related fields for performance
    tasks = tasks.select_related(
        "content_type", "assigned_to", "created_by", "completed_by", "target_status"
    )

    return TemplateResponse(
        request, "lab/task/my_tasks.html", {"tasks": tasks, "query": query}
    )


@login_required
def note_create(request):
    """Create a new note for a specific object"""
    if request.method == "POST":
        content_type_str = request.POST.get("content_type")
        object_id = request.POST.get("object_id")

        # Get the content type and object
        model = apps.get_model("lab", content_type_str.capitalize())
        content_type = ContentType.objects.get_for_model(model)
        obj = model.objects.get(id=object_id)

        # Create the note
        Note.objects.create(
            content=request.POST.get("content"),
            user=request.user,
            content_type=content_type,
            object_id=object_id,
        )

        # Return the updated list
        return TemplateResponse(
            request,
            "lab/note/list.html",
            {
                "object": obj,
                "content_type": content_type_str,
                "user": request.user,
            },
        )

    # For GET requests, return the form
    content_type_str = request.GET.get("content_type")
    object_id = request.GET.get("object_id")

    # Get the content type and object
    model = apps.get_model("lab", content_type_str.capitalize())
    content_type = ContentType.objects.get_for_model(model)
    obj = model.objects.get(id=object_id)

    return TemplateResponse(
        request,
        "lab/note/form.html",
        {
            "object": obj,
            "content_type": content_type_str,
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
                "lab/note/list.html",
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
            "lab/note/summary.html",
            context={
                "object": obj,
                "content_type": content_type_str,
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
            "lab/note/list.html",
            context={
                "object": obj,
                "content_type": content_type_str,
                "user": request.user,
            },
        )


# Project Views
@login_required
def project_index(request):
    """List all projects"""
    projects = Project.objects.all()

    # Get counts for filters
    open_count = projects.filter(is_completed=False).count()
    completed_count = projects.filter(is_completed=True).count()

    context = {
        "projects": projects,
        "open_count": open_count,
        "completed_count": completed_count,
    }

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        # The specific partial to return depends on what was requested
        if "search" in request.path:
            return render(request, "lab/project/index.html#project-list", context)
        return render(request, "lab/project/index.html#project-index", context)

    # For regular requests, return the full page
    return render(request, "lab/project/index.html", context)


@login_required
@permission_required("lab.add_project")
def project_create(request):
    """Create a new project"""
    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.created_by = request.user
            project.save()

            # If requested via HTMX, return to the list
            if request.headers.get("HX-Request"):
                projects = Project.objects.all()
                return TemplateResponse(
                    request, "lab/project/list.html", {"projects": projects}
                )

            # Otherwise redirect to the detail view
            return redirect("lab:project_detail", pk=project.pk)

    # Return the form for GET requests
    return TemplateResponse(request, "lab/project/create.html", {"form": ProjectForm()})


@login_required
def project_detail(request, pk):
    """View project details including tasks"""
    project = get_object_or_404(Project, pk=pk)

    # Get tasks for this project with prefetch
    tasks = project.tasks.select_related(
        "assigned_to", "created_by", "target_status"
    ).order_by("-priority", "created_at")

    # Group tasks by completion status
    open_tasks = tasks.filter(is_completed=False)
    completed_tasks = tasks.filter(is_completed=True)

    context = {
        "project": project,
        "open_tasks": open_tasks,
        "completed_tasks": completed_tasks,
    }

    # If it's an HTMX request, return just the content
    if request.headers.get("HX-Request"):
        # If card_only=true is in the query params, return just the card
        if request.GET.get("card_only") == "true":
            return TemplateResponse(
                request, "lab/project/card.html", {"project": project}
            )
        # Otherwise return the main content
        return TemplateResponse(
            request, "lab/project/detail.html#project-detail", context
        )

    # For regular requests, return the full page
    return TemplateResponse(request, "lab/project/detail.html", context)


@login_required
@permission_required("lab.change_project")
def project_edit(request, pk):
    """Edit an existing project"""
    project = get_object_or_404(Project, pk=pk)

    if request.method == "POST":
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            project = form.save()

            # If requested via HTMX, return to the card
            if request.headers.get("HX-Request"):
                return TemplateResponse(
                    request, "lab/project/card.html", {"project": project}
                )

            # Otherwise redirect to the detail view
            return redirect("lab:project_detail", pk=project.pk)

    # Return the form for GET requests
    return TemplateResponse(
        request,
        "lab/project/edit.html",
        {"project": project, "form": ProjectForm(instance=project)},
    )


@login_required
@permission_required("lab.delete_project")
@require_http_methods(["DELETE"])
def project_delete(request, pk):
    """Delete a project"""
    project = get_object_or_404(Project, pk=pk)
    project.delete()
    return HttpResponse(status=200)


@login_required
def project_toggle_complete(request, pk):
    """Toggle the completion status of a project"""
    project = get_object_or_404(Project, pk=pk)

    if request.method == "POST":
        project.is_completed = not project.is_completed
        project.save()

        # If requested via HTMX, return the updated card
        if request.headers.get("HX-Request"):
            return TemplateResponse(
                request, "lab/project/card.html", {"project": project}
            )

    # Return 400 for anything other than POST
    return HttpResponse(status=400)


@login_required
def project_search(request):
    """Search and filter projects"""
    query = request.GET.get("q", "")
    status_filter = request.GET.get("status", "all")

    projects = Project.objects.all()

    # Apply text search if provided
    if query:
        projects = projects.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )

    # Apply status filter
    if status_filter == "open":
        projects = projects.filter(is_completed=False)
    elif status_filter == "completed":
        projects = projects.filter(is_completed=True)

    # Order by status (incomplete first) then by creation date
    projects = projects.order_by("is_completed", "-created_at")

    return TemplateResponse(
        request,
        "lab/project/list.html",
        {"projects": projects, "query": query, "status_filter": status_filter},
    )


# Updated Task Views
@login_required
def task_list(request):
    """View for listing all tasks with improved filtering"""
    # Base queryset
    tasks = Task.objects.select_related(
        "content_type", "assigned_to", "created_by", "project", "target_status"
    )

    # Apply filters from query params
    project_id = request.GET.get("project")
    if project_id:
        tasks = tasks.filter(project_id=project_id)

    status_filter = request.GET.get("status", "open")
    if status_filter == "open":
        tasks = tasks.filter(is_completed=False)
    elif status_filter == "completed":
        tasks = tasks.filter(is_completed=True)

    assigned_to = request.GET.get("assigned_to")
    if assigned_to == "me":
        tasks = tasks.filter(assigned_to=request.user)
    elif assigned_to:
        tasks = tasks.filter(assigned_to_id=assigned_to)

    # Get projects for filter dropdown
    projects = Project.objects.all().order_by("name")

    # Get users for assignment filter
    users = User.objects.filter(is_active=True).order_by("username")

    context = {
        "tasks": tasks,
        "projects": projects,
        "users": users,
        "current_filters": {
            "project": project_id,
            "status": status_filter,
            "assigned_to": assigned_to,
        },
    }

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        # The specific partial to return depends on what was requested
        if "search" in request.path:
            return render(request, "lab/task/index.html#task-list", context)
        return render(request, "lab/task/index.html#task-index", context)

    # For regular requests, return the full page
    return render(request, "lab/task/index.html", context)


@login_required
def task_detail(request, pk):
    """View for displaying task details"""
    task = get_object_or_404(Task, pk=pk)
    context = {
        "task": task,
    }
    return render(request, "lab/task/detail.html", context)


@login_required
def task_reopen(request, pk):
    """Reopen a completed task"""
    task = get_object_or_404(Task, pk=pk)

    if request.method == "POST":
        task.is_completed = False
        task.completed_at = None
        task.completed_by = None
        task.save()

        return TemplateResponse(request, "lab/task/task_card.html", {"task": task})

    return HttpResponse(status=400)


class TestListView(LoginRequiredMixin, ListView):
    model = Test
    template_name = "lab/test_list.html"
    context_object_name = "tests"
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset()

        # Add select_related to optimize queries
        queryset = queryset.select_related(
            "sample", "sample__individual", "test", "status", "performed_by"
        )

        # Filter by search query if provided
        search_query = self.request.GET.get("search", "")
        if search_query:
            queryset = queryset.filter(
                models.Q(sample__individual__lab_id__icontains=search_query)
                | models.Q(test__name__icontains=search_query)
            )

        # Filter by status if provided
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status_id=status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("search", "")
        context["current_status"] = self.request.GET.get("status", "")
        context["statuses"] = models.Status.objects.all()
        return context


@login_required
def test_detail(request, pk):
    """Detailed view for a test"""
    test = get_object_or_404(
        Test.objects.select_related(
            "test_type",
            "sample",
            "sample__individual",
            "sample__sample_type",
            "performed_by",
            "status",
        ).prefetch_related(
            "analyses",
            "analyses__type",
            "analyses__status",
            "notes",
            "status_logs",
            "notes__user",
        ),
        pk=pk,
    )

    # Get the active tab from query params or default to 'notes'
    active_tab = request.GET.get("tab", "notes")

    # If card_only=true is in the query params, return just the card
    if request.GET.get("card_only") == "true":
        return TemplateResponse(request, "lab/test/card.html", {"test": test})

    context = {
        "test": test,
        "activeTab": active_tab,
    }

    return TemplateResponse(request, "lab/test/detail.html", context)


# Add a new view for returning just the card
@login_required
def test_card(request, pk):
    test = get_object_or_404(Test, pk=pk)
    return TemplateResponse(request, "lab/test/card.html", {"test": test})


@login_required
def test_search(request):
    """Search view for tests with filters"""
    # Get filter parameters
    status = request.POST.getlist("status", [])
    test_type = request.POST.getlist("test_type", [])
    individual = request.POST.getlist("individual", [])
    date_from = request.POST.get("date_from", "")
    date_to = request.POST.get("date_to", "")
    page = request.POST.get("page", 1)

    # Build the query
    query = Q()
    if status:
        query &= Q(status__in=status)
    if test_type:
        query &= Q(test_type__in=test_type)
    if individual:
        query &= Q(sample__individual__in=individual)
    if date_from:
        query &= Q(created_at__gte=date_from)
    if date_to:
        query &= Q(created_at__lte=date_to)

    # Get filtered tests
    tests = Test.objects.filter(query).order_by("-created_at")

    # Apply pagination
    paginator = Paginator(tests, 12)  # 12 items per page
    page_obj = paginator.get_page(page)

    context = {
        "tests": page_obj,
        "total_count": tests.count(),
        "filters": {
            "status": status,
            "test_type": test_type,
            "individual": individual,
            "date_from": date_from,
            "date_to": date_to,
        },
    }

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        return render(request, "lab/test/list.html", context)

    # For regular requests, return the full page
    return render(request, "lab/test/index.html", context)


@login_required
def types_list(request):
    """View to display sample types, test types, and analysis types."""
    sample_types = SampleType.objects.all().order_by("name")
    test_types = TestType.objects.all().order_by("name")
    analysis_types = AnalysisType.objects.all().order_by("name")

    context = {
        "sample_types": sample_types,
        "test_types": test_types,
        "analysis_types": analysis_types,
    }

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        # The specific partial to return depends on what was requested
        if "search" in request.path:
            return render(request, "lab/type/index.html#type-list", context)
        return render(request, "lab/type/index.html#type-index", context)

    # For regular requests, return the full page
    return render(request, "lab/type/index.html", context)


@login_required
def analysis_list(request):
    """List view for all analyses"""
    analyses = Analysis.objects.select_related(
        "test",
        "test__sample",
        "test__sample__individual",
        "type",
        "status",
        "performed_by",
    ).order_by("-created_at")

    context = {
        "analyses": analyses,
        "analysis_types": AnalysisType.objects.all(),
        "analysis_statuses": Status.objects.filter(
            content_type=ContentType.objects.get_for_model(Analysis)
        ),
    }

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        # The specific partial to return depends on what was requested
        if "search" in request.path:
            return render(request, "lab/analysis/index.html#analysis-list", context)
        return render(request, "lab/analysis/index.html#analysis-index", context)

    # For regular requests, return the full page
    return render(request, "lab/analysis/index.html", context)


@login_required
def analysis_search(request):
    """Search and filter analyses"""
    queryset = Analysis.objects.select_related(
        "test",
        "test__sample",
        "test__sample__individual",
        "type",
        "status",
        "performed_by",
    )

    # Apply filters
    # Status filter
    status_id = request.POST.get("status")
    if status_id:
        queryset = queryset.filter(status_id=status_id)

    # Analysis Type filter
    analysis_type_ids = request.POST.get("analysis_type")
    if analysis_type_ids:
        if "," in analysis_type_ids:
            type_id_list = analysis_type_ids.split(",")
            queryset = queryset.filter(type_id__in=type_id_list)
        else:
            queryset = queryset.filter(type_id=analysis_type_ids)

    # Individual filter
    individual_ids = request.POST.get("individual")
    if individual_ids:
        if "," in individual_ids:
            individual_id_list = individual_ids.split(",")
            queryset = queryset.filter(
                test__sample__individual_id__in=individual_id_list
            )
        else:
            queryset = queryset.filter(test__sample__individual_id=individual_ids)

    # Test filter
    test_ids = request.POST.get("test")
    if test_ids:
        if "," in test_ids:
            test_id_list = test_ids.split(",")
            queryset = queryset.filter(test_id__in=test_id_list)
        else:
            queryset = queryset.filter(test_id=test_ids)

    # Date range (performed date)
    date_from = request.POST.get("date_from")
    if date_from:
        queryset = queryset.filter(performed_date__gte=date_from)

    date_to = request.POST.get("date_to")
    if date_to:
        queryset = queryset.filter(performed_date__lte=date_to)

    # Order results
    queryset = queryset.order_by("-performed_date")

    # Get total count before pagination
    total_count = queryset.count()

    # Paginate results
    page = request.POST.get("page", 1)
    paginator = Paginator(queryset, 12)  # 12 items per page
    analyses = paginator.get_page(page)

    return TemplateResponse(
        request,
        "lab/analysis/list.html",
        {
            "analyses": analyses,
            "total_count": total_count,
            "analysis_statuses": Status.objects.filter(
                content_type=ContentType.objects.get_for_model(Analysis)
            ),
            "filters": {
                "status": status_id,
                "analysis_type": analysis_type_ids,
                "individual": individual_ids,
                "test": test_ids,
                "date_from": date_from,
                "date_to": date_to,
            },
        },
    )


@login_required
def analysis_detail(request, pk):
    """Detailed view for an analysis"""
    analysis = get_object_or_404(
        Analysis.objects.select_related(
            "test",
            "test__sample",
            "test__sample__individual",
            "test__test_type",
            "type",
            "status",
            "performed_by",
            "created_by",
        ).prefetch_related("notes", "status_logs", "notes__user"),
        pk=pk,
    )

    # Get the active tab from query params or default to 'notes'
    active_tab = request.GET.get("tab", "notes")

    # If card_only=true is in the query params, return just the card
    if request.GET.get("card_only") == "true":
        return TemplateResponse(
            request, "lab/analysis/card.html", {"analysis": analysis}
        )

    context = {
        "analysis": analysis,
        "activeTab": active_tab,
    }

    return TemplateResponse(request, "lab/analysis/detail.html", context)


@login_required
@permission_required("lab.add_analysis")
def analysis_create(request):
    """Create a new analysis"""
    test_id = request.GET.get("test")
    test = get_object_or_404(Test, pk=test_id) if test_id else None

    if request.method == "POST":
        # Handle form submission
        type_id = request.POST.get("type")
        status_id = request.POST.get("status")
        performed_date = request.POST.get("performed_date")

        if type_id and status_id and performed_date:
            analysis_type = get_object_or_404(AnalysisType, pk=type_id)
            status = get_object_or_404(Status, pk=status_id)

            analysis = Analysis.objects.create(
                test=test,
                type=analysis_type,
                status=status,
                performed_date=performed_date,
                performed_by=request.user,
                created_by=request.user,
            )

            # Return the appropriate response based on context
            if test:
                return TemplateResponse(
                    request,
                    "lab/tests/detail.html",
                    {"test": test, "active_tab": "analyses"},
                )
            else:
                return TemplateResponse(request, "lab/analysis/_add_button.html")

    # For GET requests
    analysis_content_type = ContentType.objects.get_for_model(Analysis)
    context = {
        "analysis": None,
        "test": test,
        "analysis_types": AnalysisType.objects.all(),
        "statuses": Status.objects.filter(content_type=analysis_content_type),
    }

    # If button=true is in query params, return the add button instead of the form
    if request.GET.get("button") == "true":
        context["test"] = test_id
        return TemplateResponse(request, "lab/analysis/_add_button.html", context)

    return TemplateResponse(request, "lab/analysis/edit.html", context)


@login_required
@permission_required("lab.change_analysis")
def analysis_edit(request, pk):
    """Edit an existing analysis"""
    analysis = get_object_or_404(Analysis, pk=pk)

    if request.method == "POST":
        type_id = request.POST.get("type")
        status_id = request.POST.get("status")
        performed_date = request.POST.get("performed_date")

        if type_id and status_id and performed_date:
            analysis.type = get_object_or_404(AnalysisType, pk=type_id)
            analysis.status = get_object_or_404(Status, pk=status_id)
            analysis.performed_date = performed_date
            analysis.save()

            # If return_to_detail is true, redirect to the detail view
            if request.GET.get("return_to_detail") == "true":
                return TemplateResponse(
                    request, "lab/analysis/detail.html", {"analysis": analysis}
                )

            # Otherwise return the card view
            return TemplateResponse(
                request, "lab/analysis/card.html", {"analysis": analysis}
            )

    # Get appropriate statuses for Analyses
    analysis_content_type = ContentType.objects.get_for_model(Analysis)
    analysis_statuses = Status.objects.filter(content_type=analysis_content_type)

    return TemplateResponse(
        request,
        "lab/analysis/edit.html",
        {
            "analysis": analysis,
            "analysis_types": AnalysisType.objects.all(),
            "statuses": analysis_statuses,
        },
    )


@login_required
@permission_required("lab.delete_analysis")
@require_http_methods(["DELETE"])
def analysis_delete(request, pk):
    """Delete an analysis"""
    analysis = get_object_or_404(Analysis, pk=pk)
    analysis.delete()
    return HttpResponse(status=200)


@login_required
@permission_required("lab.add_analysistype")
def analysis_type_create(request):
    """Create a new analysis type"""
    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("description")
        version = request.POST.get("version", "")
        source_url = request.POST.get("source_url", "")
        results_url = request.POST.get("results_url", "")

        if name:
            analysis_type = AnalysisType.objects.create(
                name=name,
                description=description,
                version=version,
                source_url=source_url,
                results_url=results_url,
                created_by=request.user,
            )

            return TemplateResponse(
                request,
                "lab/types/list.html",
                {
                    "sample_types": SampleType.objects.all().order_by("name"),
                    "test_types": TestType.objects.all().order_by("name"),
                    "analysis_types": AnalysisType.objects.all().order_by("name"),
                },
            )

    return TemplateResponse(request, "lab/types/analysis_type_form.html")


@login_required
@permission_required("lab.change_analysistype")
def analysis_type_edit(request, pk):
    """Edit an existing analysis type"""
    analysis_type = get_object_or_404(AnalysisType, pk=pk)

    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("description")
        version = request.POST.get("version", "")
        source_url = request.POST.get("source_url", "")
        results_url = request.POST.get("results_url", "")

        if name:
            analysis_type.name = name
            analysis_type.description = description
            analysis_type.version = version
            analysis_type.source_url = source_url
            analysis_type.results_url = results_url
            analysis_type.save()

            return TemplateResponse(
                request,
                "lab/types/list.html",
                {
                    "sample_types": SampleType.objects.all().order_by("name"),
                    "test_types": TestType.objects.all().order_by("name"),
                    "analysis_types": AnalysisType.objects.all().order_by("name"),
                },
            )

    return TemplateResponse(
        request, "lab/types/analysis_type_form.html", {"analysis_type": analysis_type}
    )


@login_required
@permission_required("lab.delete_analysistype")
def analysis_type_delete(request, pk):
    """Delete an analysis type"""
    analysis_type = get_object_or_404(AnalysisType, pk=pk)
    analysis_type.delete()
    return HttpResponse(status=200)


@login_required
def type_search(request):
    """
    Search for types (sample, test, and analysis types) based on various criteria.
    """
    # Get search parameters
    name = request.POST.get("name", "").strip()
    category = request.POST.get("category", "")
    version = request.POST.get("version", "").strip()
    source_url = request.POST.get("source_url", "").strip()
    results_url = request.POST.get("results_url", "").strip()

    # Build query for each type
    sample_types = SampleType.objects.all()
    test_types = TestType.objects.all()
    analysis_types = AnalysisType.objects.all()

    if name:
        sample_types = sample_types.filter(name__icontains=name)
        test_types = test_types.filter(name__icontains=name)
        analysis_types = analysis_types.filter(name__icontains=name)

    if category:
        sample_types = sample_types.filter(category_id=category)
        test_types = test_types.filter(category_id=category)
        analysis_types = analysis_types.filter(category_id=category)

    if version:
        analysis_types = analysis_types.filter(version__icontains=version)

    if source_url:
        analysis_types = analysis_types.filter(source_url__icontains=source_url)

    if results_url:
        analysis_types = analysis_types.filter(results_url__icontains=results_url)

    context = {
        "sample_types": sample_types,
        "test_types": test_types,
        "analysis_types": analysis_types,
    }

    # If it's an HTMX request, return just the list partial
    if request.headers.get("HX-Request"):
        return render(request, "lab/type/list.html#type-list", context)

    # For regular requests, return the full page
    return render(request, "lab/type/index.html", context)


@login_required
@require_GET
def search_hpo_terms(request):
    """Search for HPO terms with autocomplete functionality"""
    query = request.GET.get("q", "")
    terms = Term.objects.filter(
        ontology__type=2, label__icontains=query  # HP ontology
    ).select_related("ontology")[:10]

    return render(request, "lab/partials/hpo_term_results.html", {"terms": terms})


@login_required
def hpo_visualization(request):
    """View for displaying HPO term visualization"""

    # Load HPO ontology
    try:
        # Check if we have cached the graph
        if not hasattr(hpo_visualization, "graph"):
            obo_url = "https://purl.obolibrary.org/obo/hp.obo"
            graph = nx.DiGraph()

            with urllib.request.urlopen(obo_url) as response:
                hpo = fastobo.load(response)

            for frame in hpo:
                if isinstance(frame, fastobo.term.TermFrame):
                    graph.add_node(str(frame.id))
                    for clause in frame:
                        if isinstance(clause, fastobo.term.IsAClause):
                            graph.add_edge(str(frame.id), str(clause.term))

            hpo_visualization.graph = graph
            hpo_visualization.hpo = hpo

        # Get HPO terms from all individuals in the database
        individuals = Individual.objects.all()

        # Create a dictionary of sample_id -> list of HPO terms
        sample_terms = {}
        for individual in individuals:
            terms = [term.term for term in individual.hpo_terms.all()]
            if terms:  # Only include if there are terms
                sample_terms[individual.lab_id] = terms

        # Count terms
        term_counts = {}
        for sample_id, terms in sample_terms.items():
            for term in terms:
                if term in term_counts:
                    term_counts[term] += 1
                else:
                    term_counts[term] = 1

        # Consolidate terms for better visualization
        threshold = int(request.GET.get("threshold", 3))
        consolidated_counts = consolidate_terms(
            hpo_visualization.graph, term_counts, threshold=threshold
        )

        # Generate the Plotly figure
        fig, subgraph = plotly_hpo_network(
            hpo_visualization.graph,
            hpo_visualization.hpo,
            consolidated_counts,
            min_count=1,
        )

        # Convert the figure to JSON for embedding in the template
        plot_json = json.dumps(fig.to_dict())

        template_name = "lab/visualization/hpo_network.html"
        if request.headers.get("HX-Request"):
            template_name += "#hpo-network"

        return render(
            request,
            template_name,
            {
                "plot_json": plot_json,
                "threshold": threshold,
                "term_count": len(consolidated_counts),
            },
        )

    except Exception as e:
        template_name = "lab/visualization/hpo_network.html"
        if request.headers.get("HX-Request"):
            template_name += "#hpo-network"
            
        return render(
            request,
            template_name,
            {
                "error": str(e),
            },
        )


def consolidate_terms(graph, terms, threshold=3):
    # Create a working copy of the counts
    working_counts = terms.copy()

    # Check if all terms exist in the graph, remove those that don't
    invalid_terms = []
    for term in working_counts:
        if term not in graph:
            warnings.warn(
                f"The node {term} is not in the graph. Removing from consolidation."
            )
            invalid_terms.append(term)

    for term in invalid_terms:
        working_counts.pop(term, None)

    # Keep track of consolidation history
    consolidated_terms = {}  # Maps original term -> ancestor that replaced it

    # Continue until we can't consolidate further
    iteration = 0
    while True:
        iteration += 1

        # Get all current terms that are below threshold
        rare_terms = [
            term for term, count in working_counts.items() if count < threshold
        ]

        # If we have less than 2 rare terms, we can't consolidate further
        if len(rare_terms) < 2:
            break

        # Try to find a pair to consolidate
        consolidated_pair = False

        for i in range(len(rare_terms)):
            for j in range(i + 1, len(rare_terms)):
                term1 = rare_terms[i]
                term2 = rare_terms[j]

                # Find their closest common ancestor
                ancestor = find_closest_ancestor(graph, term1, term2)

                if ancestor:
                    # Calculate the combined count
                    combined_count = working_counts.get(term1, 0) + working_counts.get(
                        term2, 0
                    )

                    # Remove the consolidated terms from working counts
                    count1 = working_counts.pop(term1)
                    count2 = working_counts.pop(term2)

                    # Add or update the ancestor count
                    if ancestor in working_counts:
                        working_counts[ancestor] += combined_count
                    else:
                        working_counts[ancestor] = combined_count

                    # Update consolidation history
                    consolidated_terms[term1] = ancestor
                    consolidated_terms[term2] = ancestor

                    consolidated_pair = True
                    break

            if consolidated_pair:
                break

        # If we couldn't find any pair to consolidate, we're done
        if not consolidated_pair:
            break

    return working_counts


def find_closest_ancestor(graph, term1, term2):
    # Check if both terms exist in the graph
    if term1 not in graph:
        warnings.warn(f"The node {term1} is not in the graph. Skipping this term.")
        return None
    if term2 not in graph:
        warnings.warn(f"The node {term2} is not in the graph. Skipping this term.")
        return None

    try:
        # Get all ancestors for each term
        ancestors1 = nx.descendants(graph, term1)
        ancestors1.add(term1)  # Include the term itself

        ancestors2 = nx.descendants(graph, term2)
        ancestors2.add(term2)  # Include the term itself

        # Find common ancestors
        common_ancestors = ancestors1.intersection(ancestors2)
        if not common_ancestors:
            return None

        common_ancestors = list(common_ancestors)
        try:
            common_ancestors.remove("HP:0000118")
            common_ancestors.remove("HP:0000001")
        except:
            pass

        # Find the closest common ancestor
        # (The one with the longest path from the root)
        root = "HP:0000118"  # HPO root term

        closest_ancestor = None
        max_distance = -1

        for ancestor in common_ancestors:
            try:
                distance = len(nx.shortest_path(graph, ancestor, root)) - 1
                if distance > max_distance:
                    max_distance = distance
                    closest_ancestor = ancestor
            except nx.NetworkXNoPath:
                continue

        return closest_ancestor

    except nx.NetworkXError as e:
        warnings.warn(f"NetworkX error: {e}. Skipping this pair.")
        return None


def plotly_hpo_network(graph, hpo, term_counts, output_file=None, min_count=1):
    # Function to extract term name from the HPO ontology
    def get_term_name(term_id):
        for frame in hpo:
            if isinstance(frame, fastobo.term.TermFrame) and str(frame.id) == term_id:
                for clause in frame:
                    if isinstance(clause, fastobo.term.NameClause):
                        return str(clause.name)
        return term_id

    # Root node for phenotypic abnormality
    root_node = "HP:0000118"  # Phenotypic abnormality

    # Create a subgraph with terms and paths to root
    subgraph = nx.DiGraph()

    # Add nodes with their counts
    for term_id, count in term_counts.items():
        if term_id in graph and count >= min_count:
            name = get_term_name(term_id)
            name = name.replace("system", "sys.")
            name = name.replace("morphology", "morph.")
            name = name.replace("Abnormality of the", "")
            name = name.replace("abnormality", "")
            name = name.replace("Abnormality of", "")
            name = name.replace("Abnormal", "")

            if len(name) > 30:
                name = name[:27] + "..."
            subgraph.add_node(term_id, name=name, count=count, term_id=term_id)

            # Add path from this term to the root node
            try:
                path = nx.shortest_path(graph, term_id, root_node)
                for i in range(len(path) - 1):
                    source = path[i]
                    target = path[i + 1]

                    if source not in subgraph:
                        subgraph.add_node(
                            source,
                            name=get_term_name(source),
                            count=term_counts.get(source, 0),
                            term_id=source,
                        )
                    if target not in subgraph:
                        subgraph.add_node(
                            target,
                            name=get_term_name(target),
                            count=term_counts.get(target, 0),
                            term_id=target,
                        )

                    subgraph.add_edge(source, target)
            except nx.NetworkXNoPath:
                print(f"No path from {term_id} to root node {root_node}")

    # Add the root node if not already in the graph
    if root_node not in subgraph:
        subgraph.add_node(
            root_node,
            name=get_term_name(root_node),
            count=term_counts.get(root_node, 0),
            term_id=root_node,
        )

    # Use Graphviz layout - need to have graphviz installed
    try:
        pos = nx.nx_agraph.graphviz_layout(subgraph, prog="twopi", args="")
    except ImportError:
        print("Graphviz not available, falling back to spring layout")
        pos = nx.spring_layout(subgraph, seed=42, k=2.0, iterations=500)

    # Create edges as lines
    edge_x = []
    edge_y = []
    for edge in subgraph.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.append(x0)
        edge_x.append(x1)
        edge_x.append(None)
        edge_y.append(y0)
        edge_y.append(y1)
        edge_y.append(None)

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        line=dict(width=0.5, color="rgba(150, 150, 150, 0.6)"),
        hoverinfo="none",
        mode="lines",
    )

    # Create nodes
    node_x = []
    node_y = []
    for node in subgraph.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)

    # Get node counts and names for hover text
    node_counts = []
    node_text = []
    node_sizes = []

    # Separate arrays for labels (only for nodes with count > 0)
    label_x = []
    label_y = []
    label_text = []

    for i, node in enumerate(subgraph.nodes()):
        count = subgraph.nodes[node]["count"]
        name = subgraph.nodes[node]["name"]
        term_id = subgraph.nodes[node]["term_id"]

        node_counts.append(count)
        node_text.append(f"{name}<br>{term_id}<br>Count: {count}")

        # Simple scaling for node sizes
        size = min(100, count) if count > 0 else 8
        node_sizes.append(size)

        # Only add labels for nodes with count > 0
        if count > 0:
            label_x.append(node_x[i])
            label_y.append(node_y[i])
            short_name = name if len(name) < 20 else name[:17] + "..."
            label_text.append(f"{short_name}<br>({count})")

    # Create node trace with a small colorbar
    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers",
        hoverinfo="text",
        marker=dict(
            showscale=True,
            colorscale="Jet",
            reversescale=False,
            color=node_counts,
            size=node_sizes,
            colorbar=dict(
                thickness=10,
                title="Count",
                len=0.3,
                y=0.5,
                yanchor="middle",
                outlinewidth=0,
                tickfont=dict(size=8),
                nticks=4,
            ),
            line=dict(width=0.5, color="#888"),
        ),
        text=node_text,
    )

    # Add text labels
    labels_trace = go.Scatter(
        x=label_x,
        y=label_y,
        mode="text",
        text=label_text,
        textposition="bottom center",
        textfont=dict(family="Arial, sans-serif", size=14, color="rgba(0, 0, 0, 0.7)"),
        hoverinfo="none",
    )

    # Create a simple, clean figure
    fig = go.Figure(
        data=[edge_trace, node_trace, labels_trace],
        layout=go.Layout(
            title="HPO Term Network",
            showlegend=False,
            hovermode="closest",
            margin=dict(b=20, l=20, r=20, t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(
                showgrid=False,
                zeroline=False,
                showticklabels=False,
                scaleanchor="x",
                scaleratio=1,
            ),
            paper_bgcolor="white",
            plot_bgcolor="white",
            width=1000,
            height=1000,
        ),
    )

    return fig, subgraph
