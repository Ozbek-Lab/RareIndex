from django.urls import path
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.shortcuts import render


from neapolitan.views import CRUDView, Role
from lab.models import (
    Sample,
    Family,
    Individual,
    SampleType,
    Status,
    Institution,
    Note,
)


def index(request):
    context = {}
    return render(request, "lab/index.html", context)


class IndividualView(CRUDView):
    model = Individual
    fields = [
        "lab_id",
        "biobank_id",
        "full_name",
        "tc_identity",
        "birth_date",
        "icd11_code",
        "hpo_codes",
        "family",
        "status",
        "diagnosis",
        "diagnosis_date",
    ]


class SampleView(CRUDView):
    model = Sample
    fields = [
        "individual",
        "sample_type",
        "status",
        "receipt_date",
        "processing_date",
        "service_send_date",
        "data_receipt_date",
        "council_date",
        "sending_institution",
        "isolation_by",
        "sample_measurements",
    ]


# @method_decorator(login_required, name="dispatch")
# class IndividualView(CRUDView):
#     model = Individual
#     template_name = "lab/individual.html"  # Use your single template file
#     fields = [
#         "lab_id",
#         "biobank_id",
#         "full_name",
#         "tc_identity",
#         "birth_date",
#         "icd11_code",
#         "hpo_codes",
#         "family",
#         "status",
#         "diagnosis",
#         "diagnosis_date",
#     ]

#     # Add additional context data for templates
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)

#         # Add the action to context based on role
#         if hasattr(self, "role"):
#             context["action"] = self.role.value

#         # Add statuses for dropdown filters and forms
#         context["statuses"] = Status.objects.filter(
#             content_type=ContentType.objects.get_for_model(Individual)
#         )

#         # Add families for form selection
#         context["families"] = Family.objects.all()

#         # For detail view, add status logs
#         if self.role == Role.DETAIL and self.object:
#             context["status_logs"] = self.object.status_logs.all()

#         return context

#     # Add search and filter functionality for list view
#     def get_queryset(self):
#         queryset = super().get_queryset()

#         # Handle search
#         search = self.request.GET.get("search") or self.request.POST.get("search")
#         if search:
#             queryset = queryset.filter(
#                 Q(lab_id__icontains=search)
#                 | Q(full_name__icontains=search)
#                 | Q(biobank_id__icontains=search)
#             )

#         # Handle status filter
#         status_filter = self.request.GET.get("status") or self.request.POST.get(
#             "status"
#         )
#         if status_filter:
#             queryset = queryset.filter(status_id=status_filter)

#         return queryset

#     # Custom form handling to set created_by field
#     def form_valid(self, form):
#         if not form.instance.pk:  # New instance
#             form.instance.created_by = self.request.user

#         # If status has changed, create a status log
#         if form.instance.pk:
#             original = Individual.objects.get(pk=form.instance.pk)
#             if original.status != form.cleaned_data["status"]:
#                 from your_app_name.models import StatusLog

#                 StatusLog.objects.create(
#                     content_object=form.instance,
#                     changed_by=self.request.user,
#                     previous_status=original.status,
#                     new_status=form.cleaned_data["status"],
#                     notes=f"Status updated via form by {self.request.user.username}",
#                 )

#         return super().form_valid(form)

#     # Add note functionality
#     def add_note(self, request, pk):
#         individual = get_object_or_404(Individual, pk=pk)

#         if request.method == "POST":
#             content = request.POST.get("content")
#             if content:
#                 Note.objects.create(
#                     content=content, user=request.user, content_object=individual
#                 )

#                 # Redirect back to the detail view to see the new note
#                 if request.headers.get("HX-Request"):
#                     # For HTMX requests, return the updated detail view
#                     self.object = individual
#                     context = self.get_context_data(object=individual)
#                     return self.render_to_response(context)
#                 else:
#                     return redirect("individual-detail", pk=pk)

#         # If not a POST or no content, redirect back
#         return redirect("individual-detail", pk=pk)

#     # Handle status update directly
#     def update_status(self, request, pk):
#         individual = get_object_or_404(Individual, pk=pk)

#         if request.method == "POST":
#             new_status_id = request.POST.get("status")
#             notes = request.POST.get("notes", "")

#             if new_status_id:
#                 new_status = get_object_or_404(Status, pk=new_status_id)
#                 individual.update_status(new_status, request.user, notes)

#                 if request.headers.get("HX-Request"):
#                     # For HTMX requests, return only the status badge
#                     return HttpResponse(
#                         f'<span class="status-badge" style="background-color: {new_status.color}">'
#                         f"{new_status.name}</span>"
#                     )
#                 else:
#                     return redirect("individual-detail", pk=pk)

#         return redirect("individual-detail", pk=pk)

#     # Get URLs for all actions
#     @classmethod
#     def get_urls(cls):
#         # Use Role enum from neapolitan instead of string actions
#         return [
#             # Standard CRUD URLs from Role enum
#             path("individual/", cls.as_view(role=Role.LIST), name="individual-list"),
#             path(
#                 "individual/new/",
#                 cls.as_view(role=Role.CREATE),
#                 name="individual-create",
#             ),
#             path(
#                 "individual/<int:pk>/",
#                 cls.as_view(role=Role.DETAIL),
#                 name="individual-detail",
#             ),
#             path(
#                 "individual/<int:pk>/edit/",
#                 cls.as_view(role=Role.UPDATE),
#                 name="individual-update",
#             ),
#             path(
#                 "individual/<int:pk>/delete/",
#                 cls.as_view(role=Role.DELETE),
#                 name="individual-delete",
#             ),
#             # Custom action URLs
#             path(
#                 "individual/<int:pk>/add-note/",
#                 login_required(lambda request, pk: cls().add_note(request, pk)),
#                 name="individual-add-note",
#             ),
#             path(
#                 "individual/<int:pk>/update-status/",
#                 login_required(lambda request, pk: cls().update_status(request, pk)),
#                 name="individual-update-status",
#             ),
#         ]


# @method_decorator(login_required, name="dispatch")
# class SampleView(CRUDView):
#     model = Sample
#     template_name = "lab/sample.html"  # Use your single template file
#     fields = [
#         "individual",
#         "sample_type",
#         "status",
#         "receipt_date",
#         "processing_date",
#         "service_send_date",
#         "data_receipt_date",
#         "council_date",
#         "sending_institution",
#         "isolation_by",
#         "sample_measurements",
#     ]

#     # Add additional context data for templates
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)

#         # Add the action to context based on role
#         if hasattr(self, "role"):
#             context["action"] = self.role.value

#         # Add statuses for dropdown filters and forms
#         context["statuses"] = Status.objects.filter(
#             content_type=ContentType.objects.get_for_model(Sample)
#         )

#         # Add other required data for forms
#         context["individuals"] = Individual.objects.all()
#         context["sample_types"] = SampleType.objects.all()
#         context["institutions"] = Institution.objects.all()

#         # For detail view, add status logs
#         if self.role == Role.DETAIL and self.object:
#             context["status_logs"] = self.object.status_logs.all()
#             context["tests"] = self.object.tests.all()

#         return context

#     # Add search and filter functionality for list view
#     def get_queryset(self):
#         queryset = super().get_queryset()

#         # Handle search
#         search = self.request.GET.get("search") or self.request.POST.get("search")
#         if search:
#             queryset = queryset.filter(
#                 Q(individual__lab_id__icontains=search)
#                 | Q(individual__full_name__icontains=search)
#                 | Q(sample_measurements__icontains=search)
#             )

#         # Handle status filter
#         status_filter = self.request.GET.get("status") or self.request.POST.get(
#             "status"
#         )
#         if status_filter:
#             queryset = queryset.filter(status_id=status_filter)

#         # Handle individual filter
#         individual_filter = self.request.GET.get("individual") or self.request.POST.get(
#             "individual"
#         )
#         if individual_filter:
#             queryset = queryset.filter(individual_id=individual_filter)

#         # Handle sample type filter
#         sample_type_filter = self.request.GET.get(
#             "sample_type"
#         ) or self.request.POST.get("sample_type")
#         if sample_type_filter:
#             queryset = queryset.filter(sample_type_id=sample_type_filter)

#         return queryset

#     # Custom form handling to set created_by field
#     def form_valid(self, form):
#         if not form.instance.pk:  # New instance
#             form.instance.created_by = self.request.user

#         # If status has changed, create a status log
#         if form.instance.pk:
#             original = Sample.objects.get(pk=form.instance.pk)
#             if original.status != form.cleaned_data["status"]:
#                 from your_app_name.models import StatusLog

#                 StatusLog.objects.create(
#                     content_object=form.instance,
#                     changed_by=self.request.user,
#                     previous_status=original.status,
#                     new_status=form.cleaned_data["status"],
#                     notes=f"Status updated via form by {self.request.user.username}",
#                 )

#         return super().form_valid(form)

#     # Add note functionality
#     def add_note(self, request, pk):
#         sample = get_object_or_404(Sample, pk=pk)

#         if request.method == "POST":
#             content = request.POST.get("content")
#             if content:
#                 Note.objects.create(
#                     content=content, user=request.user, content_object=sample
#                 )

#                 # Redirect back to the detail view to see the new note
#                 if request.headers.get("HX-Request"):
#                     # For HTMX requests, return the updated detail view
#                     self.object = sample
#                     context = self.get_context_data(object=sample)
#                     return self.render_to_response(context)
#                 else:
#                     return redirect("sample-detail", pk=pk)

#         # If not a POST or no content, redirect back
#         return redirect("sample-detail", pk=pk)

#     # Handle status update directly
#     def update_status(self, request, pk):
#         sample = get_object_or_404(Sample, pk=pk)

#         if request.method == "POST":
#             new_status_id = request.POST.get("status")
#             notes = request.POST.get("notes", "")

#             if new_status_id:
#                 new_status = get_object_or_404(Status, pk=new_status_id)
#                 sample.update_status(new_status, request.user, notes)

#                 if request.headers.get("HX-Request"):
#                     # For HTMX requests, return only the status badge
#                     return HttpResponse(
#                         f'<span class="status-badge" style="background-color: {new_status.color}">'
#                         f"{new_status.name}</span>"
#                     )
#                 else:
#                     return redirect("sample-detail", pk=pk)

#         return redirect("sample-detail", pk=pk)

#     # Get URLs for all actions
#     @classmethod
#     def get_urls(cls):
#         # Use Role enum from neapolitan instead of string actions
#         return [
#             # Standard CRUD URLs from Role enum
#             path("sample/", cls.as_view(role=Role.LIST), name="sample-list"),
#             path("sample/new/", cls.as_view(role=Role.CREATE), name="sample-create"),
#             path(
#                 "sample/<int:pk>/", cls.as_view(role=Role.DETAIL), name="sample-detail"
#             ),
#             path(
#                 "sample/<int:pk>/edit/",
#                 cls.as_view(role=Role.UPDATE),
#                 name="sample-update",
#             ),
#             path(
#                 "sample/<int:pk>/delete/",
#                 cls.as_view(role=Role.DELETE),
#                 name="sample-delete",
#             ),
#             # Custom action URLs
#             path(
#                 "sample/<int:pk>/add-note/",
#                 login_required(lambda request, pk: cls().add_note(request, pk)),
#                 name="sample-add-note",
#             ),
#             path(
#                 "sample/<int:pk>/update-status/",
#                 login_required(lambda request, pk: cls().update_status(request, pk)),
#                 name="sample-update-status",
#             ),
#         ]
