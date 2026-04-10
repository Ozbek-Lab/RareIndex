from django.contrib import admin
from django import forms
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from simple_history.admin import SimpleHistoryAdmin
from . import models


class ProfileInlineForm(forms.ModelForm):
    class Meta:
        model = models.Profile
        exclude = ("contact_info",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("email_notifications", "display_preferences"):
            self.fields[field_name].required = False
            self.fields[field_name].initial = self.initial.get(field_name) or {}


class CustomUserCreationForm(AdminUserCreationForm):
    signer_block_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="Optional multiline signer block to store on the user's profile.",
        label="Signer block text",
    )

class ProjectIndividualsInline(admin.TabularInline):
    model = models.Project.individuals.through
    extra = 1
    verbose_name = "Project Individual"
    verbose_name_plural = "Project Individuals"
    autocomplete_fields = ["individual"]

class IndividualProjectsInline(admin.TabularInline):
    model = models.Project.individuals.through
    extra = 1
    verbose_name = "Individual Project"
    verbose_name_plural = "Individual Projects"
    autocomplete_fields = ["project"]


@admin.register(models.Note)
class NoteAdmin(SimpleHistoryAdmin):
    list_display = ["content_object", "user", "private_owner", "get_created_at", "get_updated_at"]
    list_filter = ["user", "private_owner", "content_type"]
    search_fields = ["content"]
    autocomplete_fields = ["user", "private_owner"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"


@admin.register(models.TestType)
class TestTypeAdmin(SimpleHistoryAdmin):
    list_display = ["name", "created_by", "get_created_at", "get_updated_at"]
    search_fields = ["name", "description"]
    list_filter = ["created_by"]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "description",
                    "created_by",
                    "positive_report_template",
                    "negative_report_template",
                )
            },
        ),
        (
            "Positive Report Text",
            {
                "fields": (
                    "default_positive_comment_text",
                )
            },
        ),
        (
            "Negative Report Text",
            {
                "fields": (
                    "default_negative_result_text",
                )
            },
        ),
        (
            "Default Report Table Text",
            {
                "fields": (
                    "default_method_text",
                    "default_total_reads_text",
                    "default_coverage_20x_text",
                    "default_mean_depth_text",
                    "default_filtering_text",
                    "default_limitations_text",
                )
            },
        ),
    )

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"


@admin.register(models.SampleType)
class SampleTypeAdmin(SimpleHistoryAdmin):
    list_display = ["name", "created_by", "get_created_at", "get_updated_at"]
    search_fields = ["name", "description"]
    list_filter = ["created_by"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"


@admin.register(models.Institution)
class InstitutionAdmin(SimpleHistoryAdmin):
    list_display = ["name", "latitude", "longitude", "created_by", "get_created_at", "get_updated_at"]
    search_fields = ["name", "staff__full_name"]
    list_filter = ["created_by"]
    autocomplete_fields = ["staff", "created_by"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"


@admin.register(models.Individual)
class IndividualAdmin(SimpleHistoryAdmin):
    list_display = [
        "full_name",
        "id",
        "get_statuses",
        "family",
        "mother",
        "father",
        "get_institutions",
        "created_by",
        "get_created_at",
        "get_updated_at",
        "get_hpo_terms",
    ]
    list_filter = ["family", "mother", "father"]
    search_fields = [
        "id",
        "full_name",
        "tc_identity",
        "cross_ids__id_value",
        "institution__name",
        "physicians__full_name",
    ]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    autocomplete_fields = ["hpo_terms", "mother", "father", "family", "institution", "physicians"]
    inlines = [IndividualProjectsInline]

    def get_hpo_terms(self, obj):
        return ", ".join([term.label for term in obj.hpo_terms.all()])
    get_hpo_terms.short_description = "HPO Terms"

    def get_institutions(self, obj):
        return ", ".join(obj.institution.values_list("name", flat=True))
    get_institutions.short_description = "Institutions"

    def get_statuses(self, obj):
        return ", ".join(obj.statuses.values_list("name", flat=True)) or "—"
    get_statuses.short_description = "Statuses"


@admin.register(models.Sample)
class SampleAdmin(SimpleHistoryAdmin):
    list_display = ["individual", "sample_type", "get_statuses", "receipt_date", "created_by", "get_created_at", "get_updated_at"]
    list_filter = ["sample_type", "receipt_date"]
    search_fields = [
        "individual__full_name",  # Only direct or forward fields!
        "isolation_by__full_name",
    ]
    date_hierarchy = "receipt_date"
    autocomplete_fields = ["individual", "sample_type", "isolation_by"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    def get_statuses(self, obj):
        return ", ".join(obj.statuses.values_list("name", flat=True)) or "—"
    get_statuses.short_description = "Statuses"

    def get_search_results(self, request, queryset, search_term):
        # Get the default search results
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        # Add custom search for individual's cross_id values
        cross_id_matches = models.Sample.objects.filter(
            individual__cross_ids__id_value__icontains=search_term
        )
        queryset |= cross_id_matches

        return queryset, use_distinct


@admin.register(models.Test)
class TestAdmin(SimpleHistoryAdmin):
    list_display = ["sample", "pk", "test_type", "get_statuses", "performed_date", "performed_by", "get_created_at", "get_updated_at"]
    list_filter = ["performed_date", "test_type"]
    search_fields = ["sample__individual__lab_id", "test_type__name"]
    date_hierarchy = "performed_date"
    autocomplete_fields = ["sample", "test_type", "performed_by"]
    raw_id_fields = []

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    def get_statuses(self, obj):
        return ", ".join(obj.statuses.values_list("name", flat=True)) or "—"
    get_statuses.short_description = "Statuses"


@admin.register(models.Status)
class StatusAdmin(SimpleHistoryAdmin):
    list_display = ["name", "short_name", "group", "content_type", "color", "created_by", "get_created_at", "get_updated_at"]
    list_editable = ["short_name"]
    search_fields = ["name", "short_name", "description"]
    list_filter = ["content_type", "group"]
    autocomplete_fields = ["group"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"


@admin.register(models.StatusGroup)
class StatusGroupAdmin(SimpleHistoryAdmin):
    list_display = ["name", "content_type", "status_count", "get_created_at", "get_updated_at"]
    search_fields = ["name", "content_type__app_label", "content_type__model"]
    list_filter = ["content_type"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.prefetch_related("statuses")

    def status_count(self, obj):
        return obj.statuses.count()
    status_count.short_description = "Statuses"

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"


@admin.register(models.Family)
class FamilyAdmin(SimpleHistoryAdmin):
    list_display = ["family_id", "created_by", "get_created_at", "get_updated_at"]
    search_fields = ["family_id", "description"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"


@admin.register(models.PipelineType)
class PipelineTypeAdmin(SimpleHistoryAdmin):
    list_display = ("name", "version", "created_by", "get_created_at", "get_updated_at")
    search_fields = ("name", "description", "version")
    filter_horizontal = ("parent_types",)
    readonly_fields = ("created_by",)

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    def save_model(self, request, obj, form, change):
        if not change:  # Only set created_by on creation
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(models.AnalysisType)
class AnalysisTypeAdmin(SimpleHistoryAdmin):
    list_display = ("name", "created_by", "get_created_at", "get_updated_at")
    search_fields = ("name", "description")
    readonly_fields = ("created_by",)

    def get_created_at(self, obj):
        return obj.get_created_at()

    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()

    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(models.Pipeline)
class PipelineAdmin(SimpleHistoryAdmin):
    list_display = ["test", "type", "get_statuses", "performed_date", "performed_by", "get_created_at", "get_updated_at"]
    list_filter = ["type", "performed_date"]
    search_fields = ["test__sample__individual__lab_id", "type__name"]
    date_hierarchy = "performed_date"
    autocomplete_fields = ["test", "type", "performed_by"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    def get_statuses(self, obj):
        return ", ".join(obj.statuses.values_list("name", flat=True)) or "—"
    get_statuses.short_description = "Statuses"


@admin.register(models.Analysis)
class AnalysisAdmin(SimpleHistoryAdmin):
    list_display = [
        "pipeline",
        "type",
        "get_statuses",
        "performed_date",
        "get_performed_by",
        "get_created_at",
        "get_updated_at",
    ]
    list_filter = ["type", "performed_date"]
    search_fields = ["pipeline__test__sample__individual__lab_id", "performed_by__username"]
    date_hierarchy = "performed_date"
    filter_horizontal = ["performed_by"]
    autocomplete_fields = ["pipeline", "type"]

    def get_performed_by(self, obj):
        return ", ".join(
            getattr(getattr(user, "contact", None), "full_name", None)
            or user.get_full_name()
            or user.username
            for user in obj.performed_by.all()
        )
    get_performed_by.short_description = "Performed By"

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    def get_statuses(self, obj):
        return ", ".join(obj.statuses.values_list("name", flat=True)) or "—"
    get_statuses.short_description = "Statuses"


@admin.register(models.Task)
class TaskAdmin(SimpleHistoryAdmin):
    list_display = [
        "id",
        "title",
        "project",
        "assigned_to",
        "created_by",
        "priority",
        "get_statuses",
        "due_date",
        "get_created_at",
        "get_updated_at",
    ]
    list_filter = [
        "priority",
        "due_date",
        "assigned_to",
        "created_by",
    ]
    search_fields = ["title", "description", "project__name"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    autocomplete_fields = ["project", "assigned_to", "created_by"]

    def get_statuses(self, obj):
        return ", ".join(obj.statuses.values_list("name", flat=True)) or "—"
    get_statuses.short_description = "Statuses"


@admin.register(models.Project)
class ProjectAdmin(SimpleHistoryAdmin):
    list_display = [
        "name",
        "created_by",
        "priority",
        "get_statuses",
        "due_date",
        "get_created_at",
        "get_updated_at",
        "get_completion_percentage",
    ]
    list_filter = ["priority", "due_date", "created_by"]
    search_fields = ["name", "description"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    autocomplete_fields = ["created_by"]
    inlines = [ProjectIndividualsInline]
    exclude = ("individuals",)

    def get_statuses(self, obj):
        return ", ".join(obj.statuses.values_list("name", flat=True)) or "—"
    get_statuses.short_description = "Statuses"

    def get_completion_percentage(self, obj):
        return f"{obj.get_completion_percentage()}%"
    get_completion_percentage.short_description = "Completion %"


@admin.register(models.IdentifierType)
class IdentifierTypeAdmin(SimpleHistoryAdmin):
    list_display = ["name", "description", "get_created_at", "get_updated_at", "created_by"]
    list_filter = ["name", "description", "created_by"]
    search_fields = ["name", "description"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"


@admin.register(models.CrossIdentifier)
class CrossIdentifierAdmin(SimpleHistoryAdmin):
    list_display = [
        "individual",
        "id_type",
        "id_value",
        "id_description",
        "get_institutions",
        "get_created_at",
        "get_updated_at",
        "created_by",
    ]
    list_filter = ["individual", "id_type", "id_value", "institution", "created_by"]
    search_fields = ["individual__id", "id_type__name", "id_value"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    autocomplete_fields = [
        "individual",
        "id_type",
        "institution",
        "created_by",
    ]

    def get_institutions(self, obj):
        return ", ".join(obj.institution.values_list("name", flat=True))

    get_institutions.short_description = "Institutions"


@admin.register(models.Contact)
class ContactAdmin(SimpleHistoryAdmin):
    list_display = ["full_name", "user", "get_emails", "get_phones", "created_by", "get_created_at", "get_updated_at"]
    list_filter = ["created_by", "user"]
    search_fields = ["full_name", "notes", "user__username", "user__first_name", "user__last_name"]
    autocomplete_fields = ["user", "created_by"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    def get_emails(self, obj):
        return ", ".join(obj.emails or [])
    get_emails.short_description = "Emails"

    def get_phones(self, obj):
        return ", ".join(obj.phones or [])
    get_phones.short_description = "Phones"


@admin.register(models.AnalysisReport)
class AnalysisReportAdmin(SimpleHistoryAdmin):
    list_display = ["id", "analysis", "file", "description", "created_by", "created_at"]
    list_filter = ["created_at", "created_by"]
    search_fields = ["file", "description"]
    autocomplete_fields = ["analysis", "created_by"]
    readonly_fields = ["created_at"]


@admin.register(models.AnalysisRequestForm)
class AnalysisRequestFormAdmin(SimpleHistoryAdmin):
    list_display = ["id", "individual", "file", "description", "created_by", "created_at"]
    list_filter = ["created_at", "created_by"]
    search_fields = ["file", "description"]
    autocomplete_fields = ["individual", "created_by"]
    readonly_fields = ["created_at"]


class ProfileInline(admin.StackedInline):
    model = models.Profile
    form = ProfileInlineForm
    can_delete = False
    fk_name = "user"
    verbose_name_plural = "Profile"
    fields = (
        "signer_block_text",
        "email_notifications",
        "display_preferences",
    )


class CustomUserAdmin(BaseUserAdmin):
    add_form = CustomUserCreationForm
    inlines = (ProfileInline,)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            "Report Signer",
            {
                "fields": ("signer_block_text",),
            },
        ),
    )
    list_display = BaseUserAdmin.list_display + (
        "get_filter_popup_on_hover",
        "get_default_list_view",
        "get_task_assigned_notifications",
        "get_status_change_notifications",
        "get_group_message_notifications",
    )

    def get_inline_instances(self, request, obj=None):
        # The profile is created by signal on initial user creation, so showing
        # the inline on the add form causes the admin to try creating it twice.
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        signer_block_text = form.cleaned_data.get("signer_block_text")
        if signer_block_text is not None:
            profile, _ = models.Profile.objects.get_or_create(user=obj)
            profile.signer_block_text = signer_block_text
            profile.save(update_fields=["signer_block_text"])

    def _get_profile(self, obj):
        return getattr(obj, "profile", None)

    def get_filter_popup_on_hover(self, obj):
        profile = self._get_profile(obj)
        if not profile or not profile.display_preferences:
            return True
        return profile.display_preferences.get("filter_popup_on_hover", True)

    get_filter_popup_on_hover.short_description = "Filter popup on hover"
    get_filter_popup_on_hover.boolean = True

    def get_default_list_view(self, obj):
        profile = self._get_profile(obj)
        if not profile or not profile.display_preferences:
            return "cards"
        return profile.display_preferences.get("default_list_view", "cards")

    get_default_list_view.short_description = "Default list view"

    def _get_email_setting(self, obj, key):
        profile = self._get_profile(obj)
        if not profile or not profile.email_notifications:
            return True
        return profile.email_notifications.get(key, True)

    def get_task_assigned_notifications(self, obj):
        return self._get_email_setting(obj, "task_assigned")

    get_task_assigned_notifications.short_description = "Task assigned email"
    get_task_assigned_notifications.boolean = True

    def get_status_change_notifications(self, obj):
        return self._get_email_setting(obj, "status_change")

    get_status_change_notifications.short_description = "Status change email"
    get_status_change_notifications.boolean = True

    def get_group_message_notifications(self, obj):
        return self._get_email_setting(obj, "group_message")

    get_group_message_notifications.short_description = "Group message email"
    get_group_message_notifications.boolean = True


# Ensure default User admin is replaced with our customized version
try:
    admin.site.unregister(User)
except NotRegistered:
    pass

admin.site.register(User, CustomUserAdmin)


@admin.register(models.PlotTemplate)
class PlotTemplateAdmin(SimpleHistoryAdmin):
    list_display = ["name", "target_model", "is_published", "created_by", "get_created_at", "get_updated_at"]
    search_fields = ["name", "description", "target_model"]
    list_filter = ["target_model", "is_published"]
    prepopulated_fields = {"slug": ("name",)}

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_staff:
            return qs
        return qs.none()

    def has_module_permission(self, request):
        return request.user.is_staff

    def has_add_permission(self, request):
        return request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return request.user.is_staff


@admin.register(models.DashboardWidget)
class DashboardWidgetAdmin(SimpleHistoryAdmin):
    list_display = ["user", "template", "order", "col_span", "row_span", "get_created_at", "get_updated_at"]
    list_filter = ["user", "template"]
    search_fields = ["user__username", "template__name"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        if obj and obj.user == request.user:
            return True
        return False

    def has_delete_permission(self, request, obj=None):
        if obj and obj.user == request.user:
            return True
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)
