from django.urls import path
from . import views

app_name = "lab"

urlpatterns = [
    path("select/search/", views.select_search, name="select_search"),
    # Main SPA routes
    path("", views.app, name="app"),
    path("individuals/", views.individual_index, name="individual_index"),
    path("samples/", views.sample_list, name="sample_list"),
    path("tests/", views.test_list, name="test_list"),
    path("analyses/", views.analysis_list, name="analysis_list"),
    path("sample-types/", views.sample_type_list, name="sample_type_list"),
    # HTMX endpoints
    path("individuals/create/", views.individual_create, name="individual_create"),
    path("individuals/<int:pk>/", views.individual_detail, name="individual_detail"),
    path("individuals/<int:pk>/edit/", views.individual_edit, name="individual_edit"),
    path("individuals/<int:pk>/delete/", views.individual_delete, name="individual_delete"),
    path("individuals/search/", views.individual_search, name="individual_search"),
    # Sample routes
    # Sample routes in lab/urls.py
    path("samples/", views.sample_list, name="sample_list"),
    path("samples/create/", views.sample_create, name="sample_create"),
    path("samples/<int:pk>/", views.sample_detail, name="sample_detail"),
    path("samples/<int:pk>/edit/", views.sample_edit, name="sample_edit"),
    path("samples/<int:pk>/delete/", views.sample_delete, name="sample_delete"),
    path("samples/search/", views.sample_search, name="sample_search"),
    # Test routes
    path("tests/", views.test_list, name="test_list"),
    path("tests/create/", views.test_create, name="test_create"),
    path('tests/<int:pk>/', views.test_detail, name='test_detail'),
    path("tests/<int:pk>/edit/", views.test_edit, name="test_edit"),
    path("tests/<int:pk>/delete/", views.test_delete, name="test_delete"),
    path('tests/<int:pk>/card/', views.test_card, name='test_card'),
    path("tests/search/", views.test_search, name="test_search"),
    # Analysis routes
    path("analyses/", views.analysis_list, name="analysis_list"),
    path("analyses/create/", views.analysis_create, name="analysis_create"),
    path("analyses/<int:pk>/", views.analysis_detail, name="analysis_detail"),
    path("analyses/<int:pk>/edit/", views.analysis_edit, name="analysis_edit"),
    path("analyses/<int:pk>/delete/", views.analysis_delete, name="analysis_delete"),
    path("analyses/search/", views.analysis_search, name="analysis_search"),
    # Test Type routes
    path("teststypes/create/", views.test_type_create, name="test_type_create"),
    path("teststypes/<int:pk>/edit/", views.test_type_edit, name="test_type_edit"),
    path("teststypes/<int:pk>/delete/", views.test_type_delete, name="test_type_delete"),
    # Sample type routes
    path("sample-types/create/", views.sample_type_create, name="sample_type_create"),
    path("sample-types/<int:pk>/edit/", views.sample_type_edit, name="sample_type_edit"),
    path("sample-types/<int:pk>/delete/", views.sample_type_delete, name="sample_type_delete"),
    path("sample-types/search/", views.sample_type_search, name="sample_type_search"),
    # Analysis type routes
    path("analysis-types/create/", views.analysis_type_create, name="analysis_type_create"),
    path("analysis-types/<int:pk>/edit/", views.analysis_type_edit, name="analysis_type_edit"),
    path("analysis-types/<int:pk>/delete/", views.analysis_type_delete, name="analysis_type_delete"),
    path("types/", views.types_list, name="types_list"),
    # Notes
    path("notes/", views.note_list, name="note_list"),
    path("note_count/", views.note_count, name="note_count"),
    path("note/create/", views.note_create, name="note_create"),
    path("note/<int:pk>/delete/", views.note_delete, name="note_delete"),
    # Add these to your urlpatterns
    path("projects/", views.project_list, name="project_list"),
    path("projects/create/", views.project_create, name="project_create"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("projects/<int:pk>/edit/", views.project_edit, name="project_edit"),
    path("projects/<int:pk>/delete/", views.project_delete, name="project_delete"),
    path("projects/<int:pk>/toggle-complete/",views.project_toggle_complete,name="project_toggle_complete"),
    path("projects/search/", views.project_search, name="project_search"),
    # Updated task URLs
    path("tasks/", views.task_index, name="task_list"),  # Changed from "tasks" to "task_index"
    path("tasks/create/<str:model>/<int:pk>/", views.task_create, name="task_create"),
    path("tasks/create/", views.task_create_standalone, name="task_create_standalone"),
    path("tasks/<int:pk>/complete/", views.task_complete, name="task_complete"),
    path("tasks/<int:pk>/reopen/", views.task_reopen, name="task_reopen"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("tasks/search/", views.task_search, name="task_search"),
]
