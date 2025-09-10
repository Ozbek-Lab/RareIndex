from django.apps import apps
from django.db.models import Q
import operator
from functools import reduce
from django.contrib.contenttypes.models import ContentType

# FILTER_CONFIG defines the search and filter behavior for each model.
FILTER_CONFIG = {
    "Term": {
        "app_label": "ontologies",
        "search_fields": ["identifier", "label"],
        "filters": {
            "Individual": "individuals__pk",
        },
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
        "status_filter": {
            "field_path": "status__pk",
            "label": "Status",
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
        "status_filter": {
            "field_path": "status__pk",
            "label": "Status",
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
        "status_filter": {
            "field_path": "status__pk",
            "label": "Status",
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
            "test_type": {
                "field_path": "test_type__name",
                "label": "Test Type",
                "select_filter_path": "test_type__name",
            },
        },
        "status_filter": {
            "field_path": "status__pk",
            "label": "Status",
        },
    },
    "Institution": {
        "app_label": "lab",
        "search_fields": ["name", "city", "center_name", "speciality", "official_name", "contact", "staff__first_name", "staff__last_name"],
        "filters": {
            "Individual": "individuals__pk",
            "Sample": "individuals__samples__pk",
            "SampleType": "individuals__samples__sample_type__pk",
            "Test": "individuals__samples__tests__pk",
            "TestType": "individuals__samples__tests__test_type__pk",
            "Analysis": "individuals__samples__tests__analyses__pk",
            "AnalysisType": "individuals__samples__tests__analyses__type__pk",
        },
        "select_fields": {
            "sample_type": {
                "field_path": "individuals__samples__sample_type__name",
                "label": "Sample Type",
                "select_filter_path": "individuals__samples__sample_type__name",
            },
            "test_type": {
                "field_path": "individuals__samples__tests__test_type__name",
                "label": "Test Type",
                "select_filter_path": "individuals__samples__tests__test_type__name",
            },
            "analysis_type": {
                "field_path": "individuals__samples__tests__analyses__type__name",
                "label": "Analysis Type",
                "select_filter_path": "individuals__samples__tests__analyses__type__name",
            },
        },
    },
    "Project": {
        "app_label": "lab",
        "search_fields": ["name", "description"],
        "filters": {},
        "status_filter": {
            "field_path": "status__pk",
            "label": "Status",
        },
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


def _get_status_filter_config(target_model_name):
    """Finds the configuration for status filter."""
    config = FILTER_CONFIG.get(target_model_name, {})
    return config.get("status_filter")


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


def _apply_status_filter(queryset, status_config, filter_values):
    """Applies a status filter using OR logic for multiple statuses."""
    status_field_path = status_config.get("field_path")
    if status_field_path and filter_values:
        # Convert string values to integers for pk filtering
        try:
            status_pks = [int(pk) for pk in filter_values if pk.isdigit()]
            if status_pks:
                return queryset.filter(**{f"{status_field_path}__in": status_pks})
        except (ValueError, TypeError):
            pass
    return queryset


def _apply_cross_model_status_filter(queryset, target_model_name, filter_model_name, filter_values):
    """Applies a cross-model status filter based on relationships."""
    # Define the relationships between models for status filtering
    status_filter_relationships = {
        "Individual": {
            "Sample": "individual__pk",
            "Test": "sample__individual__pk", 
            "Analysis": "test__sample__individual__pk",
            "Term": "individuals__pk",
        },
        "Sample": {
            "Individual": "individual__pk",
            "Test": "sample__pk",
            "Analysis": "test__sample__pk",
        },
        "Test": {
            "Individual": "sample__individual__pk",
            "Sample": "sample__pk", 
            "Analysis": "test__pk",
        },
        "Analysis": {
            "Individual": "test__sample__individual__pk",
            "Sample": "test__sample__pk",
            "Test": "test__pk",
        },
        "Project": {
            "Individual": "individuals__pk",
        },
        "Term": {
            "Individual": "individuals__pk",
        },
    }
    
    # Special handling for Tasks (they use generic relationships)
    if target_model_name == "Task":
        return _apply_task_cross_model_status_filter(queryset, filter_model_name, filter_values)
    
    # Get the relationship path from the filter model to the target model
    relationships = status_filter_relationships.get(filter_model_name, {})
    relationship_path = relationships.get(target_model_name)
    
    if not relationship_path or not filter_values:
        return queryset
    
    # Get the model that has the status filter
    filter_model_config = FILTER_CONFIG.get(filter_model_name, {})
    filter_app_label = filter_model_config.get("app_label", "lab")
    filter_model = apps.get_model(app_label=filter_app_label, model_name=filter_model_name)
    
    # Get status filter config for the filter model
    filter_status_config = _get_status_filter_config(filter_model_name)
    if not filter_status_config:
        return queryset
    
    # Apply status filter to the filter model to get filtered PKs
    status_field_path = filter_status_config.get("field_path")
    try:
        status_pks = [int(pk) for pk in filter_values if pk.isdigit()]
        if status_pks:
            # Get filtered objects from the filter model
            filtered_objects = filter_model.objects.filter(**{f"{status_field_path}__in": status_pks})
            # Get their PKs
            filtered_pks = list(filtered_objects.values_list("pk", flat=True))
            if filtered_pks:
                # Apply the relationship filter
                return queryset.filter(**{f"{relationship_path}__in": filtered_pks})
    except (ValueError, TypeError):
        pass
    
    return queryset


def _apply_task_cross_model_status_filter(queryset, filter_model_name, filter_values):
    """Applies a cross-model status filter specifically for Tasks using generic relationships."""
    from django.contrib.contenttypes.models import ContentType
    
    # Get the model that has the status filter
    filter_model_config = FILTER_CONFIG.get(filter_model_name, {})
    filter_app_label = filter_model_config.get("app_label", "lab")
    filter_model = apps.get_model(app_label=filter_app_label, model_name=filter_model_name)
    
    # Get status filter config for the filter model
    filter_status_config = _get_status_filter_config(filter_model_name)
    if not filter_status_config:
        return queryset
    
    # Apply status filter to the filter model to get filtered PKs
    status_field_path = filter_status_config.get("field_path")
    try:
        status_pks = [int(pk) for pk in filter_values if pk.isdigit()]
        if status_pks:
            # Get filtered objects from the filter model
            filtered_objects = filter_model.objects.filter(**{f"{status_field_path}__in": status_pks})
            # Get their PKs
            filtered_pks = list(filtered_objects.values_list("pk", flat=True))
            if filtered_pks:
                # Get the content type for the filter model
                filter_content_type = ContentType.objects.get_for_model(filter_model)
                # Filter tasks by content_type and object_id
                return queryset.filter(
                    content_type=filter_content_type,
                    object_id__in=filtered_pks
                )
    except (ValueError, TypeError):
        pass
    
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
    Handles both generic text search, exact-match select filters, and status filters.
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
        status_config = _get_status_filter_config(target_model_name)

        # Check for model-specific status filters (e.g., individual_status, sample_status)
        expected_status_key = f"{target_model_name.lower()}_status"
        if filter_key == expected_status_key and status_config:
            # Apply direct status filter for this model
            queryset = _apply_status_filter(queryset, status_config, filter_values)
        elif filter_key.endswith('_status'):
            # This is a cross-model status filter
            filter_model_name = filter_key.replace('_status', '').title()
            queryset = _apply_cross_model_status_filter(queryset, target_model_name, filter_model_name, filter_values)
        elif select_config:
            queryset = _apply_select_filter(queryset, select_config, filter_values)
        else:
            queryset = _apply_cross_model_text_filter(queryset, target_config, filter_key, filter_values)
    queryset = queryset.order_by("-pk")
    return queryset.distinct()


def get_available_statuses(model_name, app_label="lab"):
    """Get available statuses for a specific model."""
    try:
        model = apps.get_model(app_label=app_label, model_name=model_name)
        content_type = ContentType.objects.get_for_model(model)
        
        # Get all statuses that are either global (no content_type) or specific to this model
        from lab.models import Status
        statuses = Status.objects.filter(
            Q(content_type=content_type) | Q(content_type__isnull=True)
        ).order_by('name')
        
        return statuses
    except Exception as e:
        print(f"Error getting statuses for {model_name}: {e}")
        return []
