from django.urls import path
from . import views

app_name = "lab"

urlpatterns = [
    # Main SPA routes
    path("", views.app, name="app"),
    path("individuals/", views.individual_index, name="individual_index"),
    path("samples/", views.sample_list, name="sample_list"),
    path("tests/", views.test_list, name="test_list"),
    path("sample-types/", views.sample_type_list, name="sample_type_list"),
    # HTMX endpoints
    path("individuals/create/", views.individual_create, name="individual_create"),
    path("individuals/<int:pk>/", views.individual_detail, name="individual_detail"),
    path("individuals/<int:pk>/edit/", views.individual_edit, name="individual_edit"),
    path(
        "individuals/<int:pk>/delete/",
        views.individual_delete,
        name="individual_delete",
    ),
    path("individuals/search/", views.individual_search, name="individual_search"),
    # Sample routes
    path("samples/create/", views.sample_create, name="sample_create"),
    path("samples/<int:pk>/edit/", views.sample_edit, name="sample_edit"),
    path("samples/<int:pk>/delete/", views.sample_delete, name="sample_delete"),
    path("samples/search/", views.sample_search, name="sample_search"),
    # Test routes
    path("tests/create/", views.test_create, name="test_create"),
    path("tests/<int:pk>/edit/", views.test_edit, name="test_edit"),
    path("tests/<int:pk>/delete/", views.test_delete, name="test_delete"),
    path("tests/search/", views.test_search, name="test_search"),
    # Sample type routes
    path("sample-types/create/", views.sample_type_create, name="sample_type_create"),
    path(
        "sample-types/<int:pk>/edit/", views.sample_type_edit, name="sample_type_edit"
    ),
    path(
        "sample-types/<int:pk>/delete/",
        views.sample_type_delete,
        name="sample_type_delete",
    ),
    path("sample-types/search/", views.sample_type_search, name="sample_type_search"),
    # Add to lab/urls.py
    path("tasks/", views.my_tasks, name="my_tasks"),
    path("tasks/create/<str:model>/<int:pk>/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/complete/", views.task_complete, name="task_complete"),
    path("tasks/search/", views.task_search, name="task_search"),
    # Notes
    path("notes/", views.note_list, name="note_list"),
    path("note_count/", views.note_count, name="note_count"),
    path("note/create/", views.note_create, name="note_create"),
    path("note/<int:pk>/delete/", views.note_delete, name="note_delete"),
]
