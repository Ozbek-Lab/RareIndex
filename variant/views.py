from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from lab.models import Analysis, Pipeline, Individual
from .models import Variant
from .forms import VARIANT_FORM_CLASSES, VariantContextForm, VariantUpdateForm
from django.urls import reverse
from urllib.parse import urlencode

@login_required
@require_http_methods(["GET", "POST"])
def variant_create(request):
    analysis_id = request.GET.get("analysis_id") or request.GET.get("analysis")
    pipeline_id = request.GET.get("pipeline_id") or request.GET.get("pipeline")
    variant_type = request.GET.get("type") or request.GET.get("variant_type")
    
    # If we don't have pipeline_id or variant_type, show the selection form
    # We also check if this is NOT a specific variant form submission (POST)
    if (not (analysis_id or pipeline_id) or not variant_type) and request.method == "GET":
        # If this is an HTMX request for the selection form (filtering)
        # We re-render the form with the current data to update querysets
        form = VariantContextForm(data=request.GET)
        
        context = {"form": form}
        
        # If individual is selected, get the name for the autocomplete initial value
        individual_id = request.GET.get("individual")
        if individual_id:
            try:
                individual = Individual.objects.get(pk=individual_id)
                context["individual_name"] = individual.full_name
            except (Individual.DoesNotExist, ValueError):
                pass
                
        return render(request, "variant/variant_create_select.html", context)

    # If we have analysis/pipeline context and variant_type, proceed to specific form
    analysis = None
    pipeline = None
    if analysis_id:
        analysis = get_object_or_404(
            Analysis.objects.select_related("pipeline__test__sample__individual"),
            pk=analysis_id,
        )
        pipeline = analysis.pipeline
    elif pipeline_id:
        pipeline = get_object_or_404(Pipeline.objects.select_related("test__sample__individual"), pk=pipeline_id)
        analysis = pipeline.analyses.order_by("id").first()

    if not pipeline:
        return HttpResponseBadRequest("Selected analysis has no pipeline.")

    form_class = VARIANT_FORM_CLASSES.get(variant_type)
    
    if not form_class:
        return HttpResponseBadRequest("Invalid Variant Type.")
        
    if request.method == "POST":
        individual = pipeline.test.sample.individual
        form = form_class(request.POST, individual=individual)
        if form.is_valid():
            variant = form.save(commit=False)
            variant.analysis = analysis
            variant.individual = individual
            variant.created_by = request.user
            variant.save()
            
            # If HTMX, return the updated variant list or close modal
            if request.headers.get("HX-Request"):
                # Return a success message and trigger refresh
                response = render(request, "variant/variant.html#compact-card", {"item": variant})
                response["HX-Trigger"] = "variant-added" 
                return response
            
            url = reverse("lab:generic_detail")
            params = urlencode({"app_label": "lab", "model_name": "Pipeline", "pk": pipeline.id})
            return redirect(f"{url}?{params}")
    else:
        form = form_class()
        
    return render(request, "variant/variant_form.html", {
        "form": form,
        "analysis": analysis,
        "pipeline": pipeline,
        "variant_type": variant_type
    })

@login_required
def variant_update(request, pk):
    variant = get_object_or_404(Variant, pk=pk)
    
    # Handle cancel request
    if request.GET.get("cancel") == "true":
         return render(request, "variant/partials/variant_analysis_display.html", {"item": variant})

    if request.method == "POST":
        form = VariantUpdateForm(request.POST, instance=variant)
        if form.is_valid():
            form.save()
            
            if request.headers.get("HX-Request"):
                return render(request, "variant/partials/variant_analysis_display.html", {"item": variant})
            
            url = reverse("lab:generic_detail")
            params = urlencode({"app_label": "variant", "model_name": "Variant", "pk": variant.pk})
            return redirect(f"{url}?{params}")
    else:
        form = VariantUpdateForm(instance=variant)
        
    if request.headers.get("HX-Request"):
        return render(request, "variant/partials/variant_update_inline.html", {
            "form": form,
            "variant": variant
        })

    return render(request, "variant/variant_update.html", {
        "form": form,
        "variant": variant
    })
