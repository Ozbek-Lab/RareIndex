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
    path("profile/settings/", views.profile_settings, name="profile_settings"),
    path("profile/send-group-message/", views.send_group_message, name="send_group_message"),
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
    path("variant/<int:pk>/update/", variant_views.variant_update, name="variant_update"),
    # path("task/<int:pk>/", views.task_detail, name="task_detail"),
    # path("task/search/", views.task_search, name="task_search"),
    # path("search-hpo-terms/", views.search_hpo_terms, name="search_hpo_terms"),
    # path(
    #     "visualization/hpo-network/", views.hpo_visualization, name="hpo_visualization"
    # ),
]