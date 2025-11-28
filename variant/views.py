from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from lab.models import Analysis
from .forms import SNVForm, CNVForm, SVForm, RepeatForm, VariantContextForm
from django.urls import reverse
from urllib.parse import urlencode

@login_required
@require_http_methods(["GET", "POST"])
def variant_create(request):
    analysis_id = request.GET.get("analysis_id") or request.GET.get("analysis")
    variant_type = request.GET.get("type") or request.GET.get("variant_type")
    
    # If we don't have analysis_id or variant_type, show the selection form
    # We also check if this is NOT a specific variant form submission (POST)
    if (not analysis_id or not variant_type) and request.method == "GET":
        # If this is an HTMX request for the selection form (filtering)
        # We re-render the form with the current data to update querysets
        form = VariantContextForm(data=request.GET)
        return render(request, "variant/variant_create_select.html", {"form": form})

    # If we have analysis_id and variant_type, proceed to specific form
    analysis = get_object_or_404(Analysis, pk=analysis_id)
    
    form_class = {
        "snv": SNVForm,
        "cnv": CNVForm,
        "sv": SVForm,
        "repeat": RepeatForm,
    }.get(variant_type)
    
    if not form_class:
        return HttpResponseBadRequest("Invalid Variant Type.")
        
    if request.method == "POST":
        form = form_class(request.POST)
        if form.is_valid():
            variant = form.save(commit=False)
            variant.analysis = analysis
            variant.individual = analysis.test.sample.individual
            variant.created_by = request.user
            variant.save()
            
            # If HTMX, return the updated variant list or close modal
            if request.headers.get("HX-Request"):
                # Return a success message and trigger refresh
                response = render(request, "variant/variant.html#compact-card", {"item": variant})
                response["HX-Trigger"] = "variant-added" 
                return response
            
            url = reverse("lab:generic_detail")
            params = urlencode({"app_label": "lab", "model_name": "Analysis", "pk": analysis.id})
            return redirect(f"{url}?{params}")
    else:
        form = form_class()
        
    return render(request, "variant/variant_form.html", {
        "form": form,
        "analysis": analysis,
        "variant_type": variant_type
    })
