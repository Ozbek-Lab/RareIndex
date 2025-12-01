from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from simple_history.admin import SimpleHistoryAdmin
from . import models

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
    search_fields = ["name"]
    list_filter = ["created_by"]

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
        "status",
        "family",
        "mother",
        "father",
        "get_institutions",
        "created_by",
        "get_created_at",
        "get_updated_at",
        "get_hpo_terms",
    ]
    list_filter = ["status", "family", "mother", "father"]
    search_fields = [
        "id",
        "full_name",
        "tc_identity",
        "cross_ids__id_value",
        "institution__name",
    ]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    autocomplete_fields = ["hpo_terms", "mother", "father", "family", "institution"]
    inlines = [IndividualProjectsInline]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "status":
            ct = ContentType.objects.get_for_model(self.model)
            kwargs["queryset"] = models.Status.objects.filter(
                content_type=ct
            ) | models.Status.objects.filter(content_type__isnull=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_hpo_terms(self, obj):
        return ", ".join([term.label for term in obj.hpo_terms.all()])

    get_hpo_terms.short_description = "HPO Terms"

    def get_institutions(self, obj):
        return ", ".join(obj.institution.values_list("name", flat=True))

    get_institutions.short_description = "Institutions"


@admin.register(models.Sample)
class SampleAdmin(SimpleHistoryAdmin):
    list_display = ["individual", "sample_type", "status", "receipt_date", "created_by", "get_created_at", "get_updated_at"]
    list_filter = ["status", "sample_type", "receipt_date"]
    search_fields = [
        "individual__full_name",  # Only direct or forward fields!
    ]
    date_hierarchy = "receipt_date"
    autocomplete_fields = ["individual", "sample_type"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "status":
            ct = ContentType.objects.get_for_model(self.model)
            kwargs["queryset"] = models.Status.objects.filter(
                content_type=ct
            ) | models.Status.objects.filter(content_type__isnull=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

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
    list_display = ["sample", "pk", "test_type", "status", "performed_date", "performed_by", "get_created_at", "get_updated_at"]
    list_filter = ["status", "performed_date", "test_type"]
    search_fields = ["sample__individual__lab_id", "test_type__name"]
    date_hierarchy = "performed_date"
    autocomplete_fields = ["sample", "test_type", "performed_by"]

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "status":
            ct = ContentType.objects.get_for_model(self.model)
            kwargs["queryset"] = models.Status.objects.filter(
                content_type=ct
            ) | models.Status.objects.filter(content_type__isnull=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(models.Status)
class StatusAdmin(SimpleHistoryAdmin):
    list_display = ["name", "content_type", "color", "created_by", "get_created_at", "get_updated_at"]
    search_fields = ["name", "description"]
    list_filter = ["content_type"]

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


@admin.register(models.AnalysisType)
class AnalysisTypeAdmin(SimpleHistoryAdmin):
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


@admin.register(models.Analysis)
class AnalysisAdmin(SimpleHistoryAdmin):
    list_display = ["test", "type", "status", "performed_date", "performed_by", "get_created_at", "get_updated_at"]
    list_filter = ["type", "status", "performed_date"]
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

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "status":
            ct = ContentType.objects.get_for_model(self.model)
            kwargs["queryset"] = models.Status.objects.filter(
                content_type=ct
            ) | models.Status.objects.filter(content_type__isnull=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(models.Task)
class TaskAdmin(SimpleHistoryAdmin):
    list_display = [
        "id",
        "title",
        "project",
        "assigned_to",
        "created_by",
        "priority",
        "status",
        "due_date",
        "get_created_at",
        "get_updated_at",
    ]
    list_filter = [
        "status",
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

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "status":
            ct = ContentType.objects.get_for_model(self.model)
            kwargs["queryset"] = models.Status.objects.filter(
                content_type=ct
            ) | models.Status.objects.filter(content_type__isnull=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(models.Project)
class ProjectAdmin(SimpleHistoryAdmin):
    list_display = [
        "name",
        "created_by",
        "priority",
        "status",
        "due_date",
        "get_created_at",
        "get_updated_at",
        "get_completion_percentage",
    ]
    list_filter = ["status", "priority", "due_date", "created_by"]
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

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "status":
            ct = ContentType.objects.get_for_model(self.model)
            kwargs["queryset"] = models.Status.objects.filter(
                content_type=ct
            ) | models.Status.objects.filter(content_type__isnull=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

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

