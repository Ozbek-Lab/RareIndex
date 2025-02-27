from django.apps import apps
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.views.decorators.http import require_http_methods
from django.contrib.contenttypes.models import ContentType
from .models import (
    Individual,
    Sample,
    Test,
    SampleType,
    Status,
    Task,
    Note,
    Family,
    SampleTest,
)
from .forms import (
    IndividualForm,
    SampleForm,
    TestForm,
    SampleTypeForm,
    TaskForm,
    NoteForm,
)
from django.db.models import Q
from django.core.paginator import Paginator


def app(request, page=None, context=None):
    """Main SPA entry point that handles both authenticated and unauthenticated states"""

    # Initialize context if not provided
    if context is None:
        context = {}

    # Set initial view if provided
    if page == "individuals":
        context["initial_view"] = "individuals/index.html"
    elif page == "samples":
        context["initial_view"] = "samples/list.html"
    elif page == "tests":
        context["initial_view"] = "tests/list.html"
    elif page == "sample_types":
        context["initial_view"] = "sample_types/list.html"

    # If user is not authenticated, app.html will automatically show the login page
    return render(request, "lab/app.html", context)


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
            content_type=ContentType.objects.get_for_model(SampleTest)
        ),
    }

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        return TemplateResponse(request, "lab/individuals/index.html", context)

    # For regular requests, return via the main app
    return app(request, page="individuals", context=context)


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
                request, "lab/individuals/list.html", {"individuals": individuals}
            )
    return TemplateResponse(
        request,
        "lab/individuals/card_edit.html",
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
            return TemplateResponse(
                request, "lab/individuals/card.html", {"individual": individual}
            )
    return TemplateResponse(
        request,
        "lab/individuals/card_edit.html",
        {"individual": individual, "families": Family.objects.all()},
    )


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

    # Sample Test filter
    test_id = request.POST.get("test")
    if test_id:
        queryset = queryset.filter(samples__sampletest__test_id=test_id)

    # Sample Test Status filter
    test_status_id = request.POST.get("test_status")
    if test_status_id:
        queryset = queryset.filter(samples__sampletest__status_id=test_status_id)

    # Lab ID filter
    lab_id = request.POST.get("lab_id")
    if lab_id:
        queryset = queryset.filter(lab_id__icontains=lab_id)

    # Family ID filter
    family_id = request.POST.get("family")
    if family_id:
        queryset = queryset.filter(family_id=family_id)

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
        "lab/individuals/list.html",
        {
            "individuals": individuals,
            "total_count": total_count,
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

    return TemplateResponse(request, "lab/individuals/detail.html", context)


@login_required
def sample_list(request):
    samples = Sample.objects.all()
    template = "lab/samples/list.html"

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        return TemplateResponse(request, template, {"samples": samples})

    # Otherwise, redirect to the main app with samples view
    return app(request, page="samples")


@login_required
@permission_required("lab.add_sample")
def sample_create(request):
    if request.method == "POST":
        form = SampleForm(request.POST)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.created_by = request.user
            sample.save()

            # Return the add button template instead of empty string
            return TemplateResponse(request, "lab/samples/_add_button.html")

    # If button=true is in query params, return the add button instead of the form
    if request.GET.get("button") == "true":
        return TemplateResponse(request, "lab/samples/_add_button.html")

    # For GET requests, return the form with all available statuses
    return TemplateResponse(
        request,
        "lab/samples/card_edit.html",
        {
            "sample": None,
            "individuals": Individual.objects.all(),
            "sample_types": SampleType.objects.all(),
            "status_choices": [
                (status.id, status.name) for status in Status.objects.all()
            ],
        },
    )


@login_required
@permission_required("lab.change_sample")
def sample_edit(request, pk):
    sample = get_object_or_404(Sample, pk=pk)
    if request.method == "POST":
        form = SampleForm(request.POST, instance=sample)
        if form.is_valid():
            sample = form.save()
            return TemplateResponse(
                request, "lab/samples/card.html", {"sample": sample}
            )

    # Get appropriate statuses for Samples
    sample_content_type = ContentType.objects.get_for_model(Sample)
    sample_statuses = Status.objects.filter(content_type=sample_content_type)

    return TemplateResponse(
        request,
        "lab/samples/card_edit.html",
        {
            "sample": sample,
            "individuals": Individual.objects.all(),
            "sample_types": SampleType.objects.all(),
            "statuses": sample_statuses,  # Use the statuses from the database
        },
    )


@login_required
@permission_required("lab.delete_sample")
@require_http_methods(["DELETE"])
def sample_delete(request, pk):
    sample = get_object_or_404(Sample, pk=pk)
    sample.delete()
    return HttpResponse(status=200)


@login_required
def sample_search(request):
    query = request.GET.get("q", "")
    samples = Sample.objects.filter(individual__lab_id__icontains=query)
    return TemplateResponse(request, "lab/samples/list.html", {"samples": samples})


@login_required
def sample_detail(request, pk):
    sample = get_object_or_404(Sample, pk=pk)
    return TemplateResponse(request, "lab/sample/detail.html", {"sample": sample})


@login_required
def sample_status_update(request, pk):
    sample = get_object_or_404(Sample, pk=pk)
    if request.method == "POST":
        status_id = request.POST.get("status")

        try:
            # Get the status object from the database
            new_status = Status.objects.get(pk=status_id)

            # Verify status is appropriate for samples
            sample_content_type = ContentType.objects.get_for_model(Sample)
            if new_status.content_type == sample_content_type:
                # Use the StatusMixin method to properly update status with logging
                sample.update_status(
                    new_status, request.user, "Status updated via form"
                )

                return TemplateResponse(
                    request,
                    "lab/sample/partials/status_badge.html",
                    {"status": new_status},
                )

        except Status.DoesNotExist:
            pass  # Invalid status ID

    return HttpResponse(status=400)


@login_required
def note_list(request, model, pk):
    content_type = ContentType.objects.get(app_label="lab", model=model)
    obj = content_type.get_object_for_this_type(pk=pk)
    notes = obj.notes.all()
    return TemplateResponse(
        request, "lab/notes/note_list.html", {"notes": notes, "content_object": obj}
    )


@login_required
def note_form(request, model=None, pk=None, note_pk=None):
    note = None if note_pk is None else get_object_or_404(Note, pk=note_pk)

    if request.method == "POST":
        form = NoteForm(request.POST, instance=note)
        if form.is_valid():
            note = form.save(commit=False)
            if model and pk:
                content_type = ContentType.objects.get(app_label="lab", model=model)
                note.content_type = content_type
                note.object_id = pk
            note.user = request.user
            note.save()
            return TemplateResponse(
                request, "lab/notes/partials/note.html", {"note": note}
            )
    else:
        form = NoteForm(instance=note)

    return TemplateResponse(
        request, "lab/notes/partials/note_form.html", {"form": form, "note": note}
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
    template = "lab/tests/list.html"

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        return TemplateResponse(request, template, {"tests": tests})

    # Otherwise, redirect to the main app with tests view
    return app(request, page="tests")


@login_required
@permission_required("lab.add_test")
def test_create(request):
    if request.method == "POST":
        form = TestForm(request.POST)
        if form.is_valid():
            test = form.save(commit=False)
            test.created_by = request.user
            test.save()
            tests = Test.objects.all()
            return TemplateResponse(request, "lab/tests/list.html", {"tests": tests})
    # For GET requests, return just the form
    return TemplateResponse(
        request,
        "lab/tests/card_edit.html",
        {"test": None},  # Add this context
    )


@login_required
@permission_required("lab.change_test")
def test_edit(request, pk):
    test = get_object_or_404(Test, pk=pk)
    if request.method == "POST":
        form = TestForm(request.POST, instance=test)
        if form.is_valid():
            test = form.save()
            return TemplateResponse(request, "lab/tests/card.html", {"test": test})
    return TemplateResponse(request, "lab/tests/card_edit.html", {"test": test})


@login_required
@permission_required("lab.delete_test")
@require_http_methods(["DELETE"])
def test_delete(request, pk):
    test = get_object_or_404(Test, pk=pk)
    test.delete()
    return HttpResponse(status=200)


@login_required
def test_search(request):
    query = request.GET.get("q", "")
    tests = Test.objects.filter(name__icontains=query)
    # Return the same list template but only the grid will be swapped due to hx-select
    return TemplateResponse(request, "lab/tests/list.html", {"tests": tests})


@login_required
def sample_type_list(request):
    sample_types = SampleType.objects.all()
    template = "lab/sample_types/list.html"

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        return TemplateResponse(request, template, {"sample_types": sample_types})

    # Otherwise, redirect to the main app with sample_types view
    return app(request, page="sample_types")


@login_required
@permission_required("lab.add_sampletype")
def sample_type_create(request):
    if request.method == "POST":
        form = SampleTypeForm(request.POST)
        if form.is_valid():
            sample_type = form.save(commit=False)
            sample_type.created_by = request.user
            sample_type.save()
            sample_types = SampleType.objects.all()
            return TemplateResponse(
                request, "lab/sample_types/list.html", {"sample_types": sample_types}
            )
    return TemplateResponse(
        request,
        "lab/sample_types/card_edit.html",
        {"sample_type": None, "container_id": "sample-type-add-button"},
    )


@login_required
@permission_required("lab.change_sampletype")
def sample_type_edit(request, pk):
    sample_type = get_object_or_404(SampleType, pk=pk)
    if request.method == "POST":
        form = SampleTypeForm(request.POST, instance=sample_type)
        if form.is_valid():
            sample_type = form.save()
            return TemplateResponse(
                request, "lab/sample_types/card.html", {"sample_type": sample_type}
            )
    return TemplateResponse(
        request, "lab/sample_types/card_edit.html", {"sample_type": sample_type}
    )


@login_required
@permission_required("lab.delete_sampletype")
@require_http_methods(["DELETE"])
def sample_type_delete(request, pk):
    sample_type = get_object_or_404(SampleType, pk=pk)
    sample_type.delete()
    return HttpResponse(status=200)


@login_required
def sample_type_search(request):
    query = request.GET.get("q", "")
    sample_types = SampleType.objects.filter(name__icontains=query)
    # Return the same list template but only the grid will be swapped due to hx-select
    return TemplateResponse(
        request, "lab/sample_types/list.html", {"sample_types": sample_types}
    )


@login_required
def task_create(request, model, pk):
    """Create a task for a specific object"""
    content_type = get_object_or_404(ContentType, app_label="lab", model=model)
    content_object = get_object_or_404(content_type.model_class(), pk=pk)

    if request.method == "POST":
        form = TaskForm(request.POST, content_object=content_object)
        if form.is_valid():
            task = form.save(commit=False)
            task.content_type = content_type
            task.object_id = pk
            task.created_by = request.user
            task.save()

            return TemplateResponse(request, "lab/tasks/task_card.html", {"task": task})
    else:
        form = TaskForm(content_object=content_object)

    return TemplateResponse(
        request,
        "lab/tasks/task_form.html",
        {"form": form, "content_object": content_object, "model": model, "pk": pk},
    )


@login_required
def task_complete(request, pk):
    """Mark a task as complete and update the related object's status"""
    task = get_object_or_404(Task, pk=pk)

    if request.method == "POST":
        notes = request.POST.get("notes", "")
        success = task.complete(request.user, notes=notes)

        if success:
            return TemplateResponse(request, "lab/tasks/task_card.html", {"task": task})

    return HttpResponse(status=400)


@login_required
def my_tasks(request):
    """View for a user to see their assigned tasks"""
    tasks = Task.objects.filter(
        assigned_to=request.user, is_completed=False
    ).select_related("content_type", "assigned_to", "target_status")

    return TemplateResponse(request, "lab/tasks/my_tasks.html", {"tasks": tasks})


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

    # Select related fields for performance
    tasks = tasks.select_related(
        "content_type", "assigned_to", "created_by", "completed_by", "target_status"
    )

    return TemplateResponse(
        request, "lab/tasks/my_tasks.html", {"tasks": tasks, "query": query}
    )


@login_required
def note_create(request):
    if request.method == "POST":
        content = request.POST.get("content")
        content_type_str = request.POST.get("content_type")
        object_id = request.POST.get("object_id")

        # Get the content type
        model = apps.get_model("lab", content_type_str.capitalize())
        content_type = ContentType.objects.get_for_model(model)

        # Get the object
        obj = model.objects.get(id=object_id)

        # Create the note
        Note.objects.create(
            content=content,
            user=request.user,
            content_type=content_type,
            object_id=object_id,
        )

        response = render(
            request,
            "lab/notes/list.html",
            {
                "object": obj,
                "content_type": content_type_str,
                "user": request.user,
            },
        )
        response["HX-Trigger"] = f"noteCountUpdate-{content_type_str}-{object_id}"
        return response


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
                "lab/notes/list.html",
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
            "lab/notes/summary.html",
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
            "lab/notes/list.html",
            context={
                "object": obj,
                "content_type": content_type_str,
                "user": request.user,
            },
        )
