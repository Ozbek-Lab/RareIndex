from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from . import models

class ProjectIndividualsInline(admin.TabularInline):
    model = models.Project.individuals.through
    extra = 1
    verbose_name = "Project Individual"
    verbose_name_plural = "Project Individuals"

class IndividualProjectsInline(admin.TabularInline):
    model = models.Project.individuals.through
    extra = 1
    verbose_name = "Individual Project"
    verbose_name_plural = "Individual Projects"


@admin.register(models.Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ["content_object", "user", "created_at", "updated_at"]
    list_filter = ["created_at", "user", "content_type"]
    search_fields = ["content"]
    date_hierarchy = "created_at"


@admin.register(models.TestType)
class TestTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "created_by", "created_at"]
    search_fields = ["name", "description"]
    list_filter = ["created_at", "created_by"]


@admin.register(models.SampleType)
class SampleTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "created_by", "created_at"]
    search_fields = ["name", "description"]
    list_filter = ["created_at", "created_by"]


@admin.register(models.Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ["name", "created_by", "created_at"]
    search_fields = ["name"]
    list_filter = ["created_at", "created_by"]


@admin.register(models.Individual)
class IndividualAdmin(admin.ModelAdmin):
    list_display = [
        "full_name",
        "status",
        "family",
        "mother",
        "father",
        "created_by",
        "created_at",
        "get_hpo_terms",
    ]
    list_filter = ["status", "created_at", "family", "mother", "father"]
    search_fields = ["full_name", "tc_identity"]
    date_hierarchy = "created_at"
    autocomplete_fields = ["hpo_terms"]
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


@admin.register(models.Sample)
class SampleAdmin(admin.ModelAdmin):
    list_display = ["individual", "sample_type", "status", "receipt_date", "created_by"]
    list_filter = ["status", "sample_type", "receipt_date", "created_at"]
    search_fields = [
        "individual__full_name",  # Only direct or forward fields!
    ]
    date_hierarchy = "receipt_date"

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
class TestAdmin(admin.ModelAdmin):
    list_display = ["sample", "test_type", "status", "performed_date", "performed_by"]
    list_filter = ["status", "performed_date", "test_type"]
    search_fields = ["sample__individual__lab_id", "test_type__name"]
    date_hierarchy = "performed_date"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "status":
            ct = ContentType.objects.get_for_model(self.model)
            kwargs["queryset"] = models.Status.objects.filter(
                content_type=ct
            ) | models.Status.objects.filter(content_type__isnull=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(models.Status)
class StatusAdmin(admin.ModelAdmin):
    list_display = ["name", "content_type", "color", "created_by", "created_at"]
    search_fields = ["name", "description"]
    list_filter = ["created_at", "content_type"]


@admin.register(models.Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ["family_id", "created_by", "created_at", "updated_at"]
    search_fields = ["family_id", "description"]
    date_hierarchy = "created_at"


@admin.register(models.AnalysisType)
class AnalysisTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "created_by", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "description", "version")
    filter_horizontal = ("parent_types",)
    readonly_fields = ("created_at", "created_by")

    def save_model(self, request, obj, form, change):
        if not change:  # Only set created_by on creation
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(models.Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ["test", "type", "status", "performed_date", "performed_by"]
    list_filter = ["type", "status", "performed_date"]
    search_fields = ["test__sample__individual__lab_id", "type__name"]
    date_hierarchy = "performed_date"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "status":
            ct = ContentType.objects.get_for_model(self.model)
            kwargs["queryset"] = models.Status.objects.filter(
                content_type=ct
            ) | models.Status.objects.filter(content_type__isnull=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(models.Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "title",
        "project",
        "assigned_to",
        "created_by",
        "priority",
        "status",
        "due_date",
        "created_at",
    ]
    list_filter = [
        "status",
        "priority",
        "created_at",
        "due_date",
        "assigned_to",
        "created_by",
    ]
    search_fields = ["title", "description", "project__name"]
    date_hierarchy = "created_at"
    raw_id_fields = ["project", "assigned_to", "created_by"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "status":
            ct = ContentType.objects.get_for_model(self.model)
            kwargs["queryset"] = models.Status.objects.filter(
                content_type=ct
            ) | models.Status.objects.filter(content_type__isnull=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(models.Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "created_by",
        "priority",
        "status",
        "due_date",
        "created_at",
        "get_completion_percentage",
    ]
    list_filter = ["status", "priority", "created_at", "due_date", "created_by"]
    search_fields = ["name", "description"]
    date_hierarchy = "created_at"
    raw_id_fields = ["created_by"]
    inlines = [ProjectIndividualsInline]

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
class IdentifierTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "description", "created_at", "created_by"]
    list_filter = ["name", "description", "created_by"]
    search_fields = ["name", "description"]
    date_hierarchy = "created_at"


@admin.register(models.CrossIdentifier)
class CrossIdentifierAdmin(admin.ModelAdmin):
    list_display = [
        "individual",
        "id_type",
        "id_value",
        "id_description",
        "institution",
        "created_at",
        "created_by",
    ]
    list_filter = ["individual", "id_type", "id_value", "institution", "created_by"]
    search_fields = ["individual__id", "id_type__name"]
    date_hierarchy = "created_at"
