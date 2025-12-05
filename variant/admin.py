from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import SNV, CNV, SV, Repeat, Annotation, Classification, Gene, AnalysisReport

@admin.register(Gene)
class GeneAdmin(admin.ModelAdmin):
    list_display = ("symbol", "hgnc_id", "name", "location")
    search_fields = ("symbol", "hgnc_id", "name", "ensembl_gene_id", "entrez_id")
    list_filter = ("location",)

@admin.register(SNV)
class SNVAdmin(SimpleHistoryAdmin):
    list_display = ("__str__", "individual", "chromosome", "start", "end", "reference", "alternate", "created_by")
    search_fields = ("chromosome", "reference", "alternate", "individual__full_name")
    list_filter = ("chromosome", "created_at")

@admin.register(CNV)
class CNVAdmin(SimpleHistoryAdmin):
    list_display = ("__str__", "individual", "chromosome", "start", "end", "cnv_type", "copy_number", "created_by")
    search_fields = ("chromosome", "cnv_type", "individual__full_name")
    list_filter = ("chromosome", "cnv_type", "created_at")

@admin.register(SV)
class SVAdmin(SimpleHistoryAdmin):
    list_display = ("__str__", "individual", "chromosome", "start", "end", "sv_type", "created_by")
    search_fields = ("chromosome", "sv_type", "individual__full_name")
    list_filter = ("chromosome", "sv_type", "created_at")

@admin.register(Repeat)
class RepeatAdmin(SimpleHistoryAdmin):
    list_display = ("__str__", "individual", "chromosome", "start", "repeat_unit", "repeat_count", "created_by")
    search_fields = ("chromosome", "repeat_unit", "individual__full_name")
    list_filter = ("chromosome", "created_at")

@admin.register(Annotation)
class AnnotationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "variant", "source", "source_version", "created_at")
    search_fields = ("source", "variant__chromosome")
    list_filter = ("source", "created_at")

@admin.register(Classification)
class ClassificationAdmin(SimpleHistoryAdmin):
    list_display = ("__str__", "variant", "user", "classification", "inheritance", "created_at")
    search_fields = ("variant__chromosome", "user__username", "classification")
    list_filter = ("classification", "inheritance", "created_at")

@admin.register(AnalysisReport)
class AnalysisReportAdmin(SimpleHistoryAdmin):
    list_display = ("__str__", "analysis", "created_by", "get_created_at", "get_updated_at")
    search_fields = ("analysis__test__sample__individual__lab_id", "description")
    list_filter = ("created_by", "created_at")
    autocomplete_fields = ["analysis", "created_by"]
    filter_horizontal = ("variants",)

    def get_created_at(self, obj):
        return obj.get_created_at()
    get_created_at.short_description = "Created At"
    get_created_at.admin_order_field = "id"

    def get_updated_at(self, obj):
        return obj.get_updated_at()
    get_updated_at.short_description = "Updated At"
    get_updated_at.admin_order_field = "id"
