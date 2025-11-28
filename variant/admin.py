from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import SNV, CNV, SV, Repeat, Annotation, Classification

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
