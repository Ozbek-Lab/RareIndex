from django.urls import path
from . import views
from variant import views as variant_views

app_name = "lab"

urlpatterns = [
    path("", views.index, name="home"),
    path(
        "search/",
        views.generic_search,
        name="generic_search",
    ),
    path('detail/', views.generic_detail, name='generic_detail'),
    path('search/page/', views.generic_search_page, name='generic_search_page'),
    path(
        "hpo_network_visualization/",
        views.hpo_network_visualization,
        name="hpo_network_visualization",
    ),
    path("plots/", views.plots_page, name="plots"),
    path("map/", views.map_view, name="map"),
    path("pie-chart/<str:model_name>/<str:attribute_name>/", views.pie_chart_view, name="pie_chart"),
    path("get-select-options/", views.get_select_options, name="get_select_options"),
    path("get-objects-by-content-type/", views.get_objects_by_content_type, name="get_objects_by_content_type"),
    path("individual/<int:pk>/timeline/", views.individual_timeline, name="individual_timeline"),
    path("get-status-buttons/", views.get_status_buttons, name="get_status_buttons"),
    path("get-type-buttons/", views.get_type_buttons, name="get_type_buttons"),
    path("get-stats-counts/", views.get_stats_counts, name="get_stats_counts"),
    path("history-tab/", views.history_tab, name="history_tab"),
    path("project/add-individuals/", views.project_add_individuals, name="project_add_individuals"),
    path("project/remove-individuals/", views.project_remove_individuals, name="project_remove_individuals"),
    path("individual/edit-hpo-terms/", views.edit_individual_hpo_terms, name="edit_individual_hpo_terms"),
    path("individual/view-hpo-terms/", views.view_individual_hpo_terms, name="view_individual_hpo_terms"),
    path("individual/update-hpo-terms/", views.update_individual_hpo_terms, name="update_individual_hpo_terms"),
    path("individual/update-status/", views.update_individual_status, name="update_individual_status"),
    path("update-status/", views.update_status, name="update_status"),
    
    # Natural language search routes
    path("nl-search/", views.nl_search, name="nl_search"),
    path("nl-search/page/", views.nl_search_page, name="nl_search_page"),
    
    # path("", views.dashboard, name="dashboard"),
    # path("select/search/", views.select_search, name="select_search"),
    # # Individual routes
    # path("individuals/", views.individual_index, name="individuals"),
    # path("individual/create/", views.individual_create, name="individual_create"),
    # path("individual/<int:pk>/", views.individual_detail, name="individual_detail"),
    # path("individual/<int:pk>/edit/", views.individual_edit, name="individual_edit"),
    # path(
    #     "individual/<int:pk>/delete/", views.individual_delete, name="individual_delete"
    # ),
    # path("individual/search/", views.individual_search, name="individual_search"),
    # # Sample routes
    # path("samples/", views.sample_list, name="samples"),
    # path("sample/create/", views.sample_create, name="sample_create"),
    # path("sample/<int:pk>/", views.sample_detail, name="sample_detail"),
    # path("sample/<int:pk>/edit/", views.sample_edit, name="sample_edit"),
    # path("sample/<int:pk>/delete/", views.sample_delete, name="sample_delete"),
    # path("sample/search/", views.sample_search, name="sample_search"),
    # # Test routes
    # path("tests/", views.test_list, name="tests"),
    # path("test/create/", views.test_create, name="test_create"),
    # path("test/<int:pk>/", views.test_detail, name="test_detail"),
    # path("test/<int:pk>/edit/", views.test_edit, name="test_edit"),
    # path("test/<int:pk>/delete/", views.test_delete, name="test_delete"),
    # path("test/<int:pk>/card/", views.test_card, name="test_card"),
    # path("test/search/", views.test_search, name="test_search"),
    # # Analysis routes
    # path("analyses/", views.analysis_list, name="analyses"),
    # path("analysis/create/", views.analysis_create, name="analysis_create"),
    # path("analysis/<int:pk>/", views.analysis_detail, name="analysis_detail"),
    # path("analysis/<int:pk>/edit/", views.analysis_edit, name="analysis_edit"),
    # path("analysis/<int:pk>/delete/", views.analysis_delete, name="analysis_delete"),
    # path("analysis/search/", views.analysis_search, name="analysis_search"),
    # # Type routes
    # path("types/", views.types_list, name="types"),
    # path("types/search/", views.type_search, name="type_search"),
    # path("test-type/create/", views.test_type_create, name="test_type_create"),
    # path("test-type/<int:pk>/edit/", views.test_type_edit, name="test_type_edit"),
    # path("test-type/<int:pk>/delete/", views.test_type_delete, name="test_type_delete"),
    # path("sample-type/create/", views.sample_type_create, name="sample_type_create"),
    # path("sample-type/<int:pk>/edit/", views.sample_type_edit, name="sample_type_edit"),
    # path(
    #     "sample-type/<int:pk>/delete/",
    #     views.sample_type_delete,
    #     name="sample_type_delete",
    # ),
    # path("sample-type/search/", views.sample_type_search, name="sample_type_search"),
    # path(
    #     "analysis-type/create/", views.analysis_type_create, name="analysis_type_create"
    # ),
    # path(
    #     "analysis-type/<int:pk>/edit/",
    #     views.analysis_type_edit,
    #     name="analysis_type_edit",
    # ),
    # path(
    #     "analysis-type/<int:pk>/delete/",
    #     views.analysis_type_delete,
    #     name="analysis_type_delete",
    # ),
    # # Notes
    path("notes/", views.note_list, name="notes"),
    path("note/count/", views.note_count, name="note_count"),
    path("note/create/", views.note_create, name="note_create"),
    path("note/<int:pk>/update/", views.note_update, name="note_update"),
    path("note/<int:pk>/delete/", views.note_delete, name="note_delete"),
    
    # Generic CRUD routes
    path("create/", views.generic_create, name="generic_create"),
    path("edit/", views.generic_edit, name="generic_edit"),
    path("family/create/", views.family_create_segway, name="family_create_segway"),
    path("delete/", views.generic_delete, name="generic_delete"),
    
    path("check-notifications/", views.check_notifications, name="check_notifications"),
    path("notifications/", views.notifications_page, name="notifications"),
    # # Project routes
    # path("projects/", views.project_index, name="projects"),
    # path("project/create/", views.project_create, name="project_create"),
    # path("project/<int:pk>/", views.project_detail, name="project_detail"),
    # path("project/<int:pk>/edit/", views.project_edit, name="project_edit"),
    # path("project/<int:pk>/delete/", views.project_delete, name="project_delete"),
    # path(
    #     "project/<int:pk>/toggle-complete/",
    #     views.project_toggle_complete,
    #     name="project_toggle_complete",
    # ),
    # path("project/search/", views.project_search, name="project_search"),
    # # Task routes
    # path("tasks/", views.task_index, name="tasks"),
    # path("task/create/<str:model>/<int:pk>/", views.task_create, name="task_create"),
    # path("task/create/", views.task_create_standalone, name="task_create_standalone"),
    path("task/<int:pk>/complete/", views.task_complete, name="task_complete"),
    path("task/<int:pk>/reopen/", views.task_reopen, name="task_reopen"),
    path("variant/create/", variant_views.variant_create, name="variant_create"),
    # path("task/<int:pk>/", views.task_detail, name="task_detail"),
    # path("task/search/", views.task_search, name="task_search"),
    # path("search-hpo-terms/", views.search_hpo_terms, name="search_hpo_terms"),
    # path(
    #     "visualization/hpo-network/", views.hpo_visualization, name="hpo_visualization"
    # ),
]