from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.views.decorators.http import require_http_methods
from django.contrib.contenttypes.models import ContentType
from . import models, forms


@login_required
def app(request, page=None):
    """Main SPA entry point"""
    context = {}

    if page == "individuals":
        individuals = models.Individual.objects.all()
        context["individuals"] = individuals
        context["initial_view"] = "individuals/list.html"
    elif page == "samples":
        samples = models.Sample.objects.all()
        context["samples"] = samples
        context["initial_view"] = "samples/list.html"
    elif page == "tests":
        tests = models.Test.objects.all()
        context["tests"] = tests
        context["initial_view"] = "tests/list.html"
    elif page == "sample_types":
        sample_types = models.SampleType.objects.all()
        context["sample_types"] = sample_types
        context["initial_view"] = "sample_types/list.html"

    return TemplateResponse(request, "lab/app.html", context)


@login_required
def individual_list(request):
    individuals = models.Individual.objects.all()
    template = "lab/individuals/list.html"

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        return TemplateResponse(request, template, {"individuals": individuals})

    # Otherwise, redirect to the main app with individuals view
    return app(request, page="individuals")


@login_required
@permission_required("lab.add_individual")
def individual_create(request):
    if request.method == "POST":
        form = forms.IndividualForm(request.POST)
        if form.is_valid():
            individual = form.save(commit=False)
            individual.created_by = request.user
            individual.save()
            individuals = models.Individual.objects.all()
            return TemplateResponse(
                request, "lab/individuals/list.html", {"individuals": individuals}
            )
    return TemplateResponse(
        request,
        "lab/individuals/card_edit.html",
        {"individual": None, "families": models.Family.objects.all()},
    )


@login_required
@permission_required("lab.change_individual")
def individual_edit(request, pk):
    individual = get_object_or_404(models.Individual, pk=pk)
    if request.method == "POST":
        form = forms.IndividualForm(request.POST, instance=individual)
        if form.is_valid():
            individual = form.save()
            return TemplateResponse(
                request, "lab/individuals/card.html", {"individual": individual}
            )
    return TemplateResponse(
        request,
        "lab/individuals/card_edit.html",
        {"individual": individual, "families": models.Family.objects.all()},
    )


@login_required
@permission_required("lab.delete_individual")
@require_http_methods(["DELETE"])
def individual_delete(request, pk):
    individual = get_object_or_404(models.Individual, pk=pk)
    individual.delete()
    return HttpResponse(status=200)


@login_required
def individual_search(request):
    query = request.GET.get("q", "")
    individuals = models.Individual.objects.filter(lab_id__icontains=query)
    # Return the same list template but only the grid will be swapped due to hx-select
    return TemplateResponse(
        request, "lab/individuals/list.html", {"individuals": individuals}
    )


@login_required
def sample_list(request):
    samples = models.Sample.objects.all()
    template = "lab/samples/list.html"

    # If it's an HTMX request, return just the list content
    if request.headers.get("HX-Request"):
        return TemplateResponse(request, template, {"samples": samples})

    # Otherwise, redirect to the main app with samples view
    return app(request, page="samples")


@login_required
@permission_required("lab.add_sample")
def sample_create(request):
    if request.method == 'POST':
        form = forms.SampleForm(request.POST)
        if form.is_valid():
            sample = form.save(commit=False)
            sample.created_by = request.user
            sample.save()
            return HttpResponse('')  # Return empty string with 200 status
    
    # If button=true is in query params, return the add button instead of the form
    if request.GET.get('button') == 'true':
        return TemplateResponse(request, 'lab/samples/_add_button.html')
        
    # For GET requests, return the form
    return TemplateResponse(request, 'lab/samples/card_edit.html', {
        'sample': None,
        'individuals': models.Individual.objects.all(),
        'sample_types': models.SampleType.objects.all(),
        'status_choices': models.Sample.STATUS_CHOICES,
    })


@login_required
@permission_required("lab.change_sample")
def sample_edit(request, pk):
    sample = get_object_or_404(models.Sample, pk=pk)
    if request.method == "POST":
        form = forms.SampleForm(request.POST, instance=sample)
        if form.is_valid():
            sample = form.save()
            return TemplateResponse(
                request, "lab/samples/card.html", {"sample": sample}
            )
    return TemplateResponse(
        request,
        "lab/samples/card_edit.html",
        {
            "sample": sample,
            "individuals": models.Individual.objects.all(),
            "sample_types": models.SampleType.objects.all(),
            "status_choices": models.Sample.STATUS_CHOICES,
        },
    )


@login_required
@permission_required("lab.delete_sample")
@require_http_methods(["DELETE"])
def sample_delete(request, pk):
    sample = get_object_or_404(models.Sample, pk=pk)
    sample.delete()
    return HttpResponse(status=200)


@login_required
def sample_search(request):
    query = request.GET.get("q", "")
    samples = models.Sample.objects.filter(individual__lab_id__icontains=query)
    return TemplateResponse(request, "lab/samples/list.html", {"samples": samples})


@login_required
def sample_detail(request, pk):
    sample = get_object_or_404(models.Sample, pk=pk)
    return TemplateResponse(request, "lab/sample/detail.html", {"sample": sample})


@login_required
def sample_status_update(request, pk):
    sample = get_object_or_404(models.Sample, pk=pk)
    if request.method == "POST":
        status = request.POST.get("status")
        if status in dict(models.Sample.STATUS_CHOICES):
            sample.status = status
            sample.save()
            return TemplateResponse(
                request, "lab/sample/partials/status_badge.html", {"status": status}
            )
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
    note = None if note_pk is None else get_object_or_404(models.Note, pk=note_pk)

    if request.method == "POST":
        form = forms.NoteForm(request.POST, instance=note)
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
        form = forms.NoteForm(instance=note)

    return TemplateResponse(
        request, "lab/notes/partials/note_form.html", {"form": form, "note": note}
    )


@login_required
@require_http_methods(["DELETE"])
def note_delete(request, pk):
    note = get_object_or_404(models.Note, pk=pk)
    note.delete()
    return HttpResponse(status=200)


@login_required
def test_list(request):
    tests = models.Test.objects.all()
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
        form = forms.TestForm(request.POST)
        if form.is_valid():
            test = form.save(commit=False)
            test.created_by = request.user
            test.save()
            tests = models.Test.objects.all()
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
    test = get_object_or_404(models.Test, pk=pk)
    if request.method == "POST":
        form = forms.TestForm(request.POST, instance=test)
        if form.is_valid():
            test = form.save()
            return TemplateResponse(request, "lab/tests/card.html", {"test": test})
    return TemplateResponse(request, "lab/tests/card_edit.html", {"test": test})


@login_required
@permission_required("lab.delete_test")
@require_http_methods(["DELETE"])
def test_delete(request, pk):
    test = get_object_or_404(models.Test, pk=pk)
    test.delete()
    return HttpResponse(status=200)


@login_required
def test_search(request):
    query = request.GET.get("q", "")
    tests = models.Test.objects.filter(name__icontains=query)
    # Return the same list template but only the grid will be swapped due to hx-select
    return TemplateResponse(request, "lab/tests/list.html", {"tests": tests})


@login_required
def sample_type_list(request):
    sample_types = models.SampleType.objects.all()
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
        form = forms.SampleTypeForm(request.POST)
        if form.is_valid():
            sample_type = form.save(commit=False)
            sample_type.created_by = request.user
            sample_type.save()
            sample_types = models.SampleType.objects.all()
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
    sample_type = get_object_or_404(models.SampleType, pk=pk)
    if request.method == "POST":
        form = forms.SampleTypeForm(request.POST, instance=sample_type)
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
    sample_type = get_object_or_404(models.SampleType, pk=pk)
    sample_type.delete()
    return HttpResponse(status=200)


@login_required
def sample_type_search(request):
    query = request.GET.get("q", "")
    sample_types = models.SampleType.objects.filter(name__icontains=query)
    # Return the same list template but only the grid will be swapped due to hx-select
    return TemplateResponse(
        request, "lab/sample_types/list.html", {"sample_types": sample_types}
    )
