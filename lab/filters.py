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
            "Project": "individuals__projects__pk",
        },
    },
    "Gene": {
        "app_label": "variant",
        "search_fields": ["symbol", "name", "alias_symbol", "hgnc_id"],
        "filters": {
            "Variant": "variants__pk",
            "Individual": "variants__individual__pk",
            "Sample": "variants__individual__samples__pk",
            "Test": "variants__individual__samples__tests__pk",
            "Analysis": "variants__individual__samples__tests__analyses__pk",
            "Project": "variants__individual__projects__pk",
        },
    },
    "Individual": {
        "app_label": "lab",
        "search_fields": ["full_name", "cross_ids__id_value", "family__family_id"],
        "filters": {
            "Institution": "institution__pk",
            "Term": "hpo_terms__pk",
            "Sample": "samples__pk",
            "Test": "samples__tests__pk",
            "Analysis": "samples__tests__analyses__pk",
            "Project": "projects__pk",
            "Variant": "variants__pk",
            "Gene": "variants__genes__pk",
        },
        "select_fields": {
            "sample_type": {
                "field_path": "samples__sample_type__name",
                "label": "Sample Type",
                "select_filter_path": "samples__sample_type__name",
            },
            "test_type": {
                "field_path": "samples__tests__test_type__name",
                "label": "Test Type",
                "select_filter_path": "samples__tests__test_type__name",
            },
            "analysis_type": {
                "field_path": "samples__tests__analyses__type__name",
                "label": "Analysis Type",
                "select_filter_path": "samples__tests__analyses__type__name",
            },
        },
        "status_filter": {
            "field_path": "status__pk",
            "label": "Status",
        },
    },
    "Sample": {
        "app_label": "lab",
        "search_fields": ["sample_type__name", "id", "individual__cross_ids__id_value"],
        "type_info": {
            "model": "SampleType",
            "filter_field": "sample_type",
            "pk_field": "pk",
        },
        "filters": {
            "Individual": "individual__pk",
            "Institution": "individual__institution__pk",
            "Term": "individual__hpo_terms__pk",
            "Test": "tests__pk",
            "Analysis": "tests__analyses__pk",
            "Variant": "individual__variants__pk",
            "Gene": "individual__variants__genes__pk",
            "Project": "individual__projects__pk",
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
        "search_fields": ["test_type__name", "sample__individual__cross_ids__id_value"],
        "type_info": {
            "model": "TestType",
            "filter_field": "test_type",
            "pk_field": "pk",
        },
        "filters": {
            "Individual": "sample__individual__pk",
            "Sample": "sample__pk",
            "Institution": "sample__individual__institution__pk",
            "Analysis": "analyses__pk",
            "Variant": "analyses__found_variants__pk",
            "Gene": "analyses__found_variants__genes__pk",
            "Project": "sample__individual__projects__pk",
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
        "search_fields": ["type__name", "test__sample__individual__full_name", "test__sample__individual__cross_ids__id_value"],
        "type_info": {
            "model": "AnalysisType",
            "filter_field": "analysis_type",
            "pk_field": "pk",
        },
        "filters": {
            "Test": "test__pk",
            "Sample": "test__sample__pk",
            "Individual": "test__sample__individual__pk",
            "Variant": "found_variants__pk",
            "Gene": "found_variants__genes__pk",
            "Project": "test__sample__individual__projects__pk",
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
            "Project": "individuals__projects__pk",
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
    "Variant": {
        "app_label": "variant",
        "search_fields": ["chromosome", "snv__reference", "snv__alternate", "id", "individual__cross_ids__id_value"],
        "variant_types": {
            "snv": {"name": "SNV", "query_lookup": "snv__isnull"},
            "cnv": {"name": "CNV", "query_lookup": "cnv__isnull"},
            "sv": {"name": "SV", "query_lookup": "sv__isnull"},
            "repeat": {"name": "Repeat", "query_lookup": "repeat__isnull"},
        },
        "filters": {
            "Individual": "individual__pk",
            "Analysis": "analysis__pk",
            "Test": "analysis__test__pk",
            "Gene": "genes__pk",
            "Project": "individual__projects__pk",
        },
        "select_fields": {
            "classification": {
                "field_path": "classifications__classification",
                "label": "Classification",
                "select_filter_path": "classifications__classification",
            },
            "inheritance": {
                "field_path": "classifications__inheritance",
                "label": "Inheritance",
                "select_filter_path": "classifications__inheritance",
            },
            "test_type": {
                "field_path": "analysis__test__test_type__name",
                "label": "Test Type",
                "select_filter_path": "analysis__test__test_type__name",
            },
            "analysis_type": {
                "field_path": "analysis__type__name",
                "label": "Analysis Type",
                "select_filter_path": "analysis__type__name",
            },
        },
        "status_filter": {
            "field_path": "status__pk",
            "label": "Status",
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
        # Check if the search term is a list of IDs (from autocomplete/combobox)
        ids_to_filter = []
        if own_search_term.startswith("[") and own_search_term.endswith("]"):
            try:
                import json
                ids_to_filter = json.loads(own_search_term)
            except Exception:
                pass
        elif "," in own_search_term:
             # Try to parse as comma separated list of ints
            try:
                ids_to_filter = [int(x) for x in own_search_term.split(",") if x.strip().isdigit()]
            except Exception:
                pass
        elif own_search_term.isdigit():
            # Single ID
            ids_to_filter = [int(own_search_term)]
        
        # If we found IDs, filter by PK
        if ids_to_filter:
            return queryset.filter(pk__in=ids_to_filter)

        # Otherwise, perform text search
        own_search_fields = target_config.get("search_fields", [])
        if own_search_fields:
            q_objects = Q()
            for field in own_search_fields:
                q_objects |= Q(**{f"{field}__icontains": own_search_term})
            queryset = queryset.filter(q_objects)
    return queryset


def _apply_select_filter(queryset, select_config, filter_values, exclude=False):
    """Applies an exact match filter for a select field."""
    select_filter_path = select_config.get("select_filter_path")
    if select_filter_path:
        lookup = {f"{select_filter_path}__in": filter_values}
        return queryset.exclude(**lookup) if exclude else queryset.filter(**lookup)
    return queryset


def _apply_status_filter(queryset, status_config, filter_values, exclude=False):
    """Applies a status filter using OR logic for multiple statuses."""
    status_field_path = status_config.get("field_path")
    if status_field_path and filter_values:
        # Convert string values to integers for pk filtering
        try:
            status_pks = [int(pk) for pk in filter_values if pk.strip().isdigit()]
            if status_pks:
                lookup = {f"{status_field_path}__in": status_pks}
                return queryset.exclude(**lookup) if exclude else queryset.filter(**lookup)
        except (ValueError, TypeError):
            pass
    return queryset


def _apply_cross_model_status_filter(queryset, target_model_name, filter_model_name, filter_values, exclude=False):
    """Applies a cross-model status filter based on relationships."""
    # Define the relationships between models for status filtering
    # Define the relationships between models for status filtering
    # Refactored to use FILTER_CONFIG directly
    
    # Special handling for Tasks (they use generic relationships)
    if target_model_name == "Task":
        return _apply_task_cross_model_status_filter(queryset, filter_model_name, filter_values, exclude=exclude)
    
    # Get the relationship path from the filter model to the target model
    target_config = FILTER_CONFIG.get(target_model_name, {})
    relationship_path = target_config.get("filters", {}).get(filter_model_name)
    
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
                lookup = {f"{relationship_path}__in": filtered_pks}
                return queryset.exclude(**lookup) if exclude else queryset.filter(**lookup)
    except (ValueError, TypeError):
        pass
    
    return queryset


def _apply_task_cross_model_status_filter(queryset, filter_model_name, filter_values, exclude=False):
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
                lookup = {
                    "content_type": filter_content_type,
                    "object_id__in": filtered_pks,
                }
                return queryset.exclude(**lookup) if exclude else queryset.filter(**lookup)
    except (ValueError, TypeError):
        pass
    
    return queryset


def _apply_cross_model_text_filter(queryset, target_config, filter_key, filter_values, exclude=False):
    """Applies a text search filter from another model."""
    orm_path = target_config.get("filters", {}).get(filter_key.title())
    if not isinstance(orm_path, str):
        return queryset  # Skip complex filters for now

    # Check if we have a list of IDs (digits)
    # If all values are digits, we assume it's a PK filter and apply it directly
    all_digits = all(v.isdigit() for v in filter_values)
    if all_digits:
        lookup = {f"{orm_path}__in": filter_values}
        return queryset.exclude(**lookup) if exclude else queryset.filter(**lookup)

    filter_model_name = filter_key.title()
    filter_model_config = FILTER_CONFIG.get(filter_model_name, {})
    search_fields = filter_model_config.get("search_fields", [])
    if not search_fields:
        return queryset

    filter_app_label = filter_model_config.get("app_label", "lab")
    filter_model = apps.get_model(app_label=filter_app_label, model_name=filter_model_name)

    q_objects = Q()
    for filter_value in filter_values:
        # If the value is a digit, it might be a PK (from a combobox selection)
        if filter_value.isdigit():
            q_objects |= Q(pk=filter_value)
        
        # Also search by text fields
        for field in search_fields:
            q_objects |= Q(**{f"{field}__icontains": filter_value})

    pks_to_filter_by = list(filter_model.objects.filter(q_objects).values_list("pk", flat=True).distinct())
    if not pks_to_filter_by:
        return queryset.none()

    lookup = {f"{orm_path}__in": pks_to_filter_by}
    return queryset.exclude(**lookup) if exclude else queryset.filter(**lookup)


def _partition_active_filters(request, exclude_filter=None):
    include_filters = {}
    exclude_filters = {}
    for k, v in request.GET.items():
        if not k.startswith("filter_") or not v:
            continue
        raw_key = k.replace("filter_", "").strip()
        if not raw_key:
            continue
        target_dict = include_filters
        normalized_key = raw_key
        if raw_key.endswith("_exclude"):
            normalized_key = raw_key[: -len("_exclude")]
            target_dict = exclude_filters
        if normalized_key == exclude_filter or not normalized_key:
            continue
            
        # Handle JSON array or comma-separated list
        values = []
        if v.startswith("[") and v.endswith("]"):
            try:
                import json
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    values = [str(x) for x in parsed]
            except Exception:
                pass
        
        if not values:
            values = [part.strip() for part in v.split(",") if part.strip()]
            
        if not values:
            continue
        target_dict[normalized_key] = values
    return include_filters, exclude_filters


def _apply_filter_group(queryset, target_model_name, filter_key, filter_values, target_config, exclude=False):
    select_config = _get_select_field_config(filter_key, target_model_name)
    status_config = _get_status_filter_config(target_model_name)

    expected_status_key = f"{target_model_name.lower()}_status"
    if filter_key == expected_status_key and status_config:
        return _apply_status_filter(queryset, status_config, filter_values, exclude=exclude)
    if filter_key.endswith("_status"):
        filter_model_name = filter_key.replace("_status", "").title()
        return _apply_cross_model_status_filter(
            queryset,
            target_model_name,
            filter_model_name,
            filter_values,
            exclude=exclude,
        )
    if filter_key == "variant_type":
        return _apply_variant_type_filter(queryset, filter_values, target_model_name, exclude=exclude)
    if select_config:
        return _apply_select_filter(queryset, select_config, filter_values, exclude=exclude)
    return _apply_cross_model_text_filter(
        queryset,
        target_config,
        filter_key,
        filter_values,
        exclude=exclude,
    )

def _apply_variant_type_filter(queryset, filter_values, target_model_name, exclude=False):
    """Applies a filter for variant types (SNV, CNV, SV, Repeat)."""
    # Determine the path to the variant model based on the target model
    prefix = ""
    if target_model_name != "Variant":
        target_config = FILTER_CONFIG.get(target_model_name, {})
        variant_path = target_config.get("filters", {}).get("Variant")
        if not variant_path:
            return queryset
        # Remove 'pk' from the end to get the relationship prefix
        # e.g. "variants__pk" -> "variants__"
        prefix = variant_path.rsplit("pk", 1)[0]

    variant_config = FILTER_CONFIG.get("Variant", {}).get("variant_types", {})
    q_objects = Q()
    
    for val in filter_values:
        val = val.lower()
        type_data = variant_config.get(val)
        if type_data:
            lookup = type_data["query_lookup"]
            q_objects |= Q(**{f"{prefix}{lookup}": False})
    
    if exclude:
        return queryset.exclude(q_objects)
    return queryset.filter(q_objects)


def apply_filters(request, target_model_name, queryset, exclude_filter=None):
    """
    Applies search and cross-model filters to a given queryset.
    Handles both generic text search, exact-match select filters, and status filters.
    """
    queryset = _apply_own_search(queryset, target_model_name, request)

    include_filters, exclude_filters = _partition_active_filters(request, exclude_filter)

    target_config = FILTER_CONFIG.get(target_model_name, {})

    for filter_key, filter_values in include_filters.items():
        queryset = _apply_filter_group(
            queryset,
            target_model_name,
            filter_key,
            filter_values,
            target_config,
            exclude=False,
        )
    for filter_key, filter_values in exclude_filters.items():
        queryset = _apply_filter_group(
            queryset,
            target_model_name,
            filter_key,
            filter_values,
            target_config,
            exclude=True,
        )
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


def get_available_types(model_name, app_label="lab"):
    """Get available types for a specific model."""
    try:
        # Normalize model name to Title case for config lookup
        config_key = model_name
        if config_key not in FILTER_CONFIG:
            config_key = model_name.title()
            
        config = FILTER_CONFIG.get(config_key, {})
        
        # Handle Variant special case (types defined in config)
        if "variant_types" in config:
            types = []
            for key, data in config["variant_types"].items():
                types.append({
                    "pk": key,
                    "name": data["name"],
                    "filter_field": "variant_type"
                })
            return types

        # Handle standard model-based types
        type_info = config.get("type_info")
        if not type_info:
            return []
        
        # Get the type model
        # Use app_label from config if available, else default to passed app_label
        type_app_label = config.get("app_label", app_label)
        type_model = apps.get_model(app_label=type_app_label, model_name=type_info['model'])
        
        # Get all types ordered by name
        types = type_model.objects.all().order_by('name')
        
        # Add the filter field name to each type object
        for type_obj in types:
            type_obj.filter_field = type_info['filter_field']
            type_obj.pk_field = type_info['pk_field']
        
        return types
    except Exception as e:
        print(f"Error getting types for {model_name}: {e}")
        return []
