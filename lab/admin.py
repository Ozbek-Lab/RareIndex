from django.contrib import admin
from . import models

@admin.register(models.Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ['content_object', 'user', 'created_at', 'updated_at']
    list_filter = ['created_at', 'user', 'content_type']
    search_fields = ['content']
    date_hierarchy = 'created_at'

@admin.register(models.TestType)
class TestTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'created_at']
    search_fields = ['name', 'description']
    list_filter = ['created_at', 'created_by']

@admin.register(models.SampleType)
class SampleTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'created_at']
    search_fields = ['name', 'description']
    list_filter = ['created_at', 'created_by']

@admin.register(models.Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'created_at']
    search_fields = ['name']
    list_filter = ['created_at', 'created_by']

@admin.register(models.Individual)
class IndividualAdmin(admin.ModelAdmin):
    list_display = ['lab_id', 'biobank_id', 'full_name', 'status', 'family', 'created_by', 'created_at']
    list_filter = ['status', 'created_at', 'family']
    search_fields = ['lab_id', 'biobank_id', 'full_name', 'tc_identity']
    date_hierarchy = 'created_at'

@admin.register(models.Sample)
class SampleAdmin(admin.ModelAdmin):
    list_display = ['individual', 'sample_type', 'status', 'receipt_date', 'created_by']
    list_filter = ['status', 'sample_type', 'receipt_date', 'created_at']
    search_fields = ['individual__lab_id', 'individual__full_name']
    date_hierarchy = 'receipt_date'

@admin.register(models.Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ['sample', 'test_type', 'status', 'performed_date', 'performed_by']
    list_filter = ['status', 'performed_date', 'test_type']
    search_fields = ['sample__individual__lab_id', 'test_type__name']
    date_hierarchy = 'performed_date'

@admin.register(models.Status)
class StatusAdmin(admin.ModelAdmin):
    list_display = ['name', 'color', 'created_by', 'created_at']
    search_fields = ['name', 'description']
    list_filter = ['created_at']

@admin.register(models.StatusLog)
class StatusLogAdmin(admin.ModelAdmin):
    list_display = ['content_object', 'previous_status', 'new_status', 'changed_by', 'changed_at']
    list_filter = ['changed_at', 'content_type', 'changed_by']
    search_fields = ['notes']
    date_hierarchy = 'changed_at'

@admin.register(models.Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ['family_id', 'created_by', 'created_at', 'updated_at']
    search_fields = ['family_id', 'description']
    date_hierarchy = 'created_at'

@admin.register(models.AnalysisType)
class AnalysisTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'created_by', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'description', 'version')
    filter_horizontal = ('parent_types',)
    readonly_fields = ('created_at', 'created_by')

    def save_model(self, request, obj, form, change):
        if not change:  # Only set created_by on creation
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(models.Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ['test', 'type', 'status', 'performed_date', 'performed_by']
    list_filter = ['type', 'status', 'performed_date']
    search_fields = ['test__sample__individual__lab_id', 'type__name']
    date_hierarchy = 'performed_date'
