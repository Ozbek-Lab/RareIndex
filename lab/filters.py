from django.apps import apps
from django.db.models import Q
import operator
from functools import reduce

# FILTER_CONFIG defines the search and filter behavior for each model.
FILTER_CONFIG = {
    "Term": {
        "app_label": "ontologies",
        "search_fields": ["identifier", "label"],
        "filters": {},
    },
    "Individual": {
        "app_label": "lab",
        "search_fields": ["full_name", "cross_ids__id_value", "family__family_id"],
        "filters": {
            "Institution": "institution__pk",
            "Term": "hpo_terms__pk",
            "Sample": "samples__pk",
        },
        "select_fields": {
            "sample_type": {
                "field_path": "samples__sample_type__name",
                "label": "Sample Type",
                "select_filter_path": "samples__sample_type__name",
            },
        },
    },
    "Sample": {
        "app_label": "lab",
        "search_fields": ["sample_type__name", "id"],
        "filters": {
            "Individual": "individual__pk",
            "Institution": "individual__institution__pk",
            "Term": "individual__hpo_terms__pk",
            "Test": "tests__pk",
        },
        "select_fields": {
            "sample_type": {
                "field_path": "sample_type__name",
                "label": "Sample Type",
                "select_filter_path": "sample_type__name",
            },
        },
    },
    "Test": {
        "app_label": "lab",
        "search_fields": ["test_type__name"],
        "filters": {
            "Individual": "sample__individual__pk",
            "Sample": "sample__pk",
            "Institution": "sample__individual__institution__pk",
        },
        "select_fields": {
            "sample_type": {
                "field_path": "sample__sample_type__name",
                "label": "Sample Type",
                "select_filter_path": "sample__sample_type__name",
            },
            "analysis_type": {
                "field_path": "analyses__type__name",
                "label": "Analysis Type",
                "select_filter_path": "analyses__type__name",
            },
            "test_type": {
                "field_path": "test_type__name",
                "label": "Test Type",
                "select_filter_path": "test_type__name",
            },
        },
    },
    "Analysis": {
        "app_label": "lab",
        "search_fields": ["type__name", "test__sample__individual__full_name"],
        "filters": {
            "Test": "test__pk",
            "Sample": "test__sample__sample_type__pk",
            "Individual": "test__sample__individual__pk",
        },
        "select_fields": {
            "sample_type": {
                "field_path": "test__sample__sample_type__name",
                "label": "Sample Type",
                "select_filter_path": "test__sample__sample_type__name",
            },
            "analysis_type": {
                "field_path": "type__name",
                "label": "Analysis Type",
                "select_filter_path": "type__name",
            },
        },
    },
    "Institution": {
        "app_label": "lab",
        "search_fields": ["name", "contact"],
        "filters": {},
    },
    "Project": {
        "app_label": "lab",
        "search_fields": ["name", "description"],
        "filters": {},
    },
    "Task": {
        "app_label": "lab",
        "search_fields": ["title", "description"],
        "filters": {
            "Project": "project__pk",
            "Institution": [
                {"link_model": "Individual", "path_from_link_model": "institution__pk"},
                {"link_model": "Sample", "path_from_link_model": "individual__institution__pk"},
                {"link_model": "Test", "path_from_link_model": "sample__individual__institution__pk"},
            ],
            "Individual": [
                {"link_model": "Individual", "path_from_link_model": "pk"},
                {"link_model": "Sample", "path_from_link_model": "individual__pk"},
                {"link_model": "Test", "path_from_link_model": "sample__individual__pk"},
            ],
            "Sample": [
                {"link_model": "Sample", "path_from_link_model": "pk"},
                {"link_model": "Test", "path_from_link_model": "sample__pk"},
            ],
            "Test": [
                {"link_model": "Test", "path_from_link_model": "pk"},
            ],
        },
    },
}


def _get_select_field_config(field_name, target_model_name):
    """Finds the configuration for a select field."""
    config = FILTER_CONFIG.get(target_model_name, {})
    if field_name in config.get("select_fields", {}):
        return config["select_fields"][field_name]
    return None


def _apply_own_search(queryset, target_model_name, request):
    """Handles the component's own text search (from generic-search partial)."""
    target_config = FILTER_CONFIG.get(target_model_name, {})
    own_search_term = request.GET.get("search") or request.GET.get(f"filter_{target_model_name.lower()}")
    if own_search_term:
        own_search_fields = target_config.get("search_fields", [])
        if own_search_fields:
            q_objects = Q()
            for field in own_search_fields:
                q_objects |= Q(**{f"{field}__icontains": own_search_term})
            queryset = queryset.filter(q_objects)
    return queryset


def _apply_select_filter(queryset, select_config, filter_values):
    """Applies an exact match filter for a select field."""
    select_filter_path = select_config.get("select_filter_path")
    if select_filter_path:
        return queryset.filter(**{f"{select_filter_path}__in": filter_values})
    return queryset


def _apply_cross_model_text_filter(queryset, target_config, filter_key, filter_values):
    """Applies a text search filter from another model."""
    orm_path = target_config.get("filters", {}).get(filter_key.title())
    if not isinstance(orm_path, str):
        return queryset  # Skip complex filters for now

    filter_model_name = filter_key.title()
    filter_model_config = FILTER_CONFIG.get(filter_model_name, {})
    search_fields = filter_model_config.get("search_fields", [])
    if not search_fields:
        return queryset

    filter_app_label = filter_model_config.get("app_label", "lab")
    filter_model = apps.get_model(app_label=filter_app_label, model_name=filter_model_name)

    q_objects = Q()
    for field in search_fields:
        q_objects |= reduce(operator.or_, [Q(**{f"{field}__icontains": filter_value}) for filter_value in filter_values])

    pks_to_filter_by = list(filter_model.objects.filter(q_objects).values_list("pk", flat=True).distinct())
    if not pks_to_filter_by:
        return queryset.none()

    return queryset.filter(**{f"{orm_path}__in": pks_to_filter_by})


def apply_filters(request, target_model_name, queryset, exclude_filter=None):
    """
    Applies search and cross-model filters to a given queryset.
    Handles both generic text search and exact-match select filters.
    """
    queryset = _apply_own_search(queryset, target_model_name, request)

    active_filters = {
        k.replace("filter_", ""): v.split(",")
        for k, v in request.GET.items()
        if k.startswith("filter_") and v and k.replace("filter_", "") != exclude_filter
    }
    print(f"Active filters: {active_filters}")

    target_config = FILTER_CONFIG.get(target_model_name, {})
    for filter_key, filter_values in active_filters.items():
        print(f"Applying filter: {filter_key} with value(s): {filter_values}")
        select_config = _get_select_field_config(filter_key, target_model_name)

        if select_config:
            queryset = _apply_select_filter(queryset, select_config, filter_values)
        else:
            queryset = _apply_cross_model_text_filter(queryset, target_config, filter_key, filter_values)
    queryset = queryset.order_by("-pk")
    return queryset.distinct()
