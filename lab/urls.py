from django.urls import path
from .views import (
    DashboardView, IndividualListView, ProjectListView, SampleListView, IndividualDetailView,
    ProjectDetailView,
    VariantListView, FamilyCreateView, HPOTermSearchView, RenderSelectedHPOTermView,
    CompleteTaskView, ReopenTaskView, IndividualExportView, configurations_view,
)
from .profile_views import ProfileView, UpdateThemeView
from .htmx_views import (
    RevealSensitiveFieldView, add_individual_row, IndividualHPOEditView, manage_hpo_term,
    note_create, note_update, note_delete, note_list, note_count,
    individual_identification_edit, individual_identification_save,
    individual_demographics_edit, individual_demographics_save,
    individual_identification_display, individual_demographics_display,
    family_search,
    individual_parents_edit, individual_parents_display, individual_parents_save,
    individual_clinical_summary_edit, individual_clinical_summary_save, individual_clinical_summary_display,
    update_status, sample_create_modal, test_create_modal, task_create_modal,
    pipeline_create_modal, analysis_create_modal,
    individual_projects_edit, individual_projects_save, project_search,
    project_individual_search, project_individual_add, project_individual_remove,
    document_preview,
    request_form_create_modal, report_create_modal, variant_create_modal, variant_detail_partial,
    config_form, config_delete_confirm, config_delete, config_section_partial,
)


app_name = "lab"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("individuals/", IndividualListView.as_view(), name="individual_list"),
    path("projects/", ProjectListView.as_view(), name="project_list"),
    path("projects/<int:pk>/detail/", ProjectDetailView.as_view(), name="project_detail"),
    path("variants/", VariantListView.as_view(), name="variant_list"),
    path("individuals/export/", IndividualExportView.as_view(), name="individual_export"),
    path("individuals/create-family/", FamilyCreateView.as_view(), name="create_family"),
    path("samples/", SampleListView.as_view(), name="sample_list"),
    path("individuals/<int:pk>/detail/", IndividualDetailView.as_view(), name="individual_detail"),
    path("reveal/<str:model_name>/<int:pk>/<str:field_name>/", RevealSensitiveFieldView.as_view(), name="reveal_sensitive_field"),
    path("htmx/add-individual-row/", add_individual_row, name="add_individual_row"),
    path("htmx/individual/<int:pk>/hpo-edit/", IndividualHPOEditView.as_view(), name="hpo_edit"),
    path("htmx/individual/<int:pk>/hpo-manage/", manage_hpo_term, name="hpo_manage"),
    
    # Inline Edit
    path("htmx/individual/<int:pk>/identification/", individual_identification_display, name="individual_identification_display"),
    path("htmx/individual/<int:pk>/identification/edit/", individual_identification_edit, name="individual_identification_edit"),
    path("htmx/individual/<int:pk>/identification/save/", individual_identification_save, name="individual_identification_save"),
    path("htmx/individual/<int:pk>/demographics/", individual_demographics_display, name="individual_demographics_display"),
    path("htmx/individual/<int:pk>/demographics/edit/", individual_demographics_edit, name="individual_demographics_edit"),
    path("htmx/individual/<int:pk>/demographics/save/", individual_demographics_save, name="individual_demographics_save"),
    path("htmx/family/search/", family_search, name="family_search"),
    path("htmx/individual/<int:pk>/parents/edit/", individual_parents_edit, name="individual_parents_edit"),
    path("htmx/individual/<int:pk>/parents/display/", individual_parents_display, name="individual_parents_display"),
    path("htmx/individual/<int:pk>/parents/save/", individual_parents_save, name="individual_parents_save"),
    path("htmx/individual/<int:pk>/clinical-summary/", individual_clinical_summary_display, name="individual_clinical_summary_display"),
    path("htmx/individual/<int:pk>/clinical-summary/edit/", individual_clinical_summary_edit, name="individual_clinical_summary_edit"),
    path("htmx/individual/<int:pk>/clinical-summary/save/", individual_clinical_summary_save, name="individual_clinical_summary_save"),

    # HPO Search
    path("htmx/hpo/search/", HPOTermSearchView.as_view(), name="hpo_search"),
    path("htmx/hpo/picker/", HPOTermSearchView.as_view(template_name="lab/partials/hpo_picker_results.html"), name="hpo_picker"),
    path("htmx/hpo/render/<int:pk>/", RenderSelectedHPOTermView.as_view(), name="render_selected_hpo"),
    
    # Notes
    path("htmx/notes/create/", note_create, name="note_create"),
    path("htmx/notes/update/<int:pk>/", note_update, name="note_update"),
    path("htmx/notes/delete/<int:pk>/", note_delete, name="note_delete"),
    path("htmx/notes/list/", note_list, name="note_list"),
    path("htmx/notes/count/", note_count, name="note_count"),
    
    # Profile & Theme
    path("profile/", ProfileView.as_view(), name="profile"),
    path("profile/update-theme/", UpdateThemeView.as_view(), name="update_theme"),
    
    # Status Updates
    path(
        "status/update/<int:content_type_id>/<int:object_id>/<int:status_id>/",
        update_status,
        name="update_status",
    ),
    path("htmx/sample/create/<int:individual_id>/", sample_create_modal, name="sample_create_modal"),
    path("htmx/test/create/<int:sample_id>/", test_create_modal, name="test_create_modal"),
    path("htmx/pipeline/create/<int:test_id>/", pipeline_create_modal, name="pipeline_create_modal"),
    path("htmx/analysis/create/<int:pipeline_id>/", analysis_create_modal, name="analysis_create_modal"),
    path("htmx/task/create/<int:content_type_id>/<int:object_id>/", task_create_modal, name="task_create_modal"),
    path("htmx/request_form/create/<int:individual_id>/", request_form_create_modal, name="request_form_create_modal"),
    path("htmx/report/create/<int:pipeline_id>/", report_create_modal, name="report_create_modal"),
    path("htmx/variant/create/<int:pipeline_id>/", variant_create_modal, name="variant_create_modal"),
    
    # Project Management
    path("htmx/individual/<int:pk>/projects/edit/", individual_projects_edit, name="individual_projects_edit"),
    path("htmx/individual/<int:pk>/projects/save/", individual_projects_save, name="individual_projects_save"),
    path("htmx/project/search/", project_search, name="project_search"),
    path("htmx/project/<int:pk>/individuals/search/", project_individual_search, name="project_individual_search"),
    path("htmx/project/<int:project_pk>/individuals/<int:individual_pk>/add/", project_individual_add, name="project_individual_add"),
    path("htmx/project/<int:project_pk>/individuals/<int:individual_pk>/remove/", project_individual_remove, name="project_individual_remove"),
    path("htmx/task/complete/<int:pk>/", CompleteTaskView.as_view(), name="complete_task"),
    path("htmx/task/reopen/<int:pk>/", ReopenTaskView.as_view(), name="reopen_task"),
    path("htmx/preview/<str:model_name>/<int:pk>/", document_preview, name="document_preview"),
    path("htmx/variant/<int:pk>/detail/", variant_detail_partial, name="variant_detail_partial"),

    # Configurations
    path("configurations/", configurations_view, name="configurations"),
    path("htmx/config/<str:model_name>/section/", config_section_partial, name="config_section"),
    path("htmx/config/<str:model_name>/form/", config_form, name="config_form_add"),
    path("htmx/config/<str:model_name>/<int:pk>/form/", config_form, name="config_form_edit"),
    path("htmx/config/<str:model_name>/<int:pk>/delete-confirm/", config_delete_confirm, name="config_delete_confirm"),
    path("htmx/config/<str:model_name>/<int:pk>/delete/", config_delete, name="config_delete"),
]
