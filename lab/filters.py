from django.apps import apps
from django.db.models import Q, OuterRef, Subquery, Value, CharField, Count, Case, When
from django.db.models.functions import Coalesce
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
                "field_path": "test__test_type__name",
                "label": "Test Type",
                "select_filter_path": "test__test_type__name",
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


def _is_encrypted_field(model, field_name):
    """Check if a field is an encrypted field."""
    try:
        field = model._meta.get_field(field_name.split('__')[0])
        # Try using EncryptedFieldMixin first
        try:
            from encrypted_model_fields.fields import EncryptedFieldMixin
            if isinstance(field, EncryptedFieldMixin):
                return True
        except ImportError:
            pass
        
        # Fallback: check if 'Encrypted' is in the class name
        field_class_name = field.__class__.__name__
        if 'Encrypted' in field_class_name:
            return True
        
        return False
    except (AttributeError, Exception):
        return False


def _separate_encrypted_fields(model, search_fields):
    """Separate encrypted fields from regular fields."""
    encrypted_fields = []
    regular_fields = []
    
    for field in search_fields:
        if _is_encrypted_field(model, field):
            encrypted_fields.append(field)
        else:
            regular_fields.append(field)
    
    return encrypted_fields, regular_fields


def _filter_encrypted_fields(queryset, encrypted_fields, terms, exact_match=False, exclude=False):
    """Filter queryset by encrypted fields in Python.
    
    Uses OR logic: matches if ANY term matches ANY encrypted field.
    """
    if not encrypted_fields or not terms:
        return queryset
    
    matching_pks = []
    search_terms_lower = [term.lower() for term in terms]
    
    # Load all records to decrypt and filter
    # Evaluate queryset to list to ensure we get all records
    try:
        all_objects = list(queryset)
    except Exception:
        # If that fails, try iterating
        all_objects = [obj for obj in queryset]
    
    for obj in all_objects:
        match_found = False
        for field_name in encrypted_fields:
            field_path_parts = field_name.split('__')
            field_name_only = field_path_parts[0]
            
            try:
                field_value = getattr(obj, field_name_only)
                if field_value:
                    field_value_str = str(field_value).lower()
                    
                    # Check if any term matches this field (OR logic)
                    for search_term_lower in search_terms_lower:
                        if exact_match:
                            if field_value_str == search_term_lower:
                                match_found = True
                                break
                        else:
                            if search_term_lower in field_value_str:
                                match_found = True
                                break
                    
                    if match_found:
                        break
            except (AttributeError, Exception):
                continue
        
        if match_found:
            matching_pks.append(obj.pk)
    
    if exclude:
        if matching_pks:
            return queryset.exclude(pk__in=matching_pks)
        return queryset
    else:
        if matching_pks:
            return queryset.filter(pk__in=matching_pks)
        return queryset.none()


def _apply_own_search(queryset, target_model_name, request):
    """Handles the component's own text search (from generic-search partial).
    
    Search syntax:
    - Space-separated terms: OR logic with fuzzy match (icontains)
    - "quoted term": exact match (iexact)
    - -term: exclude fuzzy match
    - -"quoted term": exclude exact match
    
    Examples:
    - "02 03" → contains "02" OR contains "03"
    - '"RB_2025"' → exactly "RB_2025"
    - "02 -04" → contains "02", excluding contains "04"
    - '-"RB_2025"' → exclude exactly "RB_2025"
    """
    import re
    target_config = FILTER_CONFIG.get(target_model_name, {})
    own_search_term = request.GET.get("search") or request.GET.get(f"filter_{target_model_name.lower()}")
    
    if own_search_term:
        # Check if the search term is a list of IDs (from autocomplete/combobox)
        # Only JSON array format is treated as ID selection
        ids_to_filter = []
        if own_search_term.startswith("[") and own_search_term.endswith("]"):
            try:
                import json
                ids_to_filter = json.loads(own_search_term)
            except Exception:
                pass
        
        # If we found IDs from JSON array, filter by PK
        if ids_to_filter:
            return queryset.filter(pk__in=ids_to_filter)

        own_search_fields = target_config.get("search_fields", [])
        if own_search_fields:
            # Get the model to check for encrypted fields
            target_app_label = target_config.get("app_label", "lab")
            target_model = apps.get_model(app_label=target_app_label, model_name=target_model_name)
            
            # Separate encrypted and regular fields
            encrypted_fields, regular_fields = _separate_encrypted_fields(target_model, own_search_fields)
            
            # Parse all tokens: -"quoted", "quoted", -term, term
            # Pattern matches: -"...", "...", or non-whitespace sequences
            tokens = re.findall(r'-"[^"]+"|"[^"]+"|[^\s]+', own_search_term)
            
            include_exact = []
            include_fuzzy = []
            exclude_exact = []
            exclude_fuzzy = []
            
            for token in tokens:
                if token.startswith('-"') and token.endswith('"'):
                    # Exclude exact: -"term"
                    exclude_exact.append(token[2:-1])
                elif token.startswith('"') and token.endswith('"'):
                    # Include exact: "term"
                    include_exact.append(token[1:-1])
                elif token.startswith('-'):
                    # Exclude fuzzy: -term
                    term = token[1:]
                    if term:
                        exclude_fuzzy.append(term)
                else:
                    # Include fuzzy: term
                    if token:
                        include_fuzzy.append(token)
            
            # Special handling for ontology Terms (e.g. HPO codes like "HP:0025696")
            # If a token looks like PREFIX:CODE, also search by the CODE part alone
            if target_model_name == "Term":
                def _augment_with_code(tokens_list):
                    augmented = list(tokens_list)
                    for t in list(tokens_list):
                        if ":" in t:
                            _, _, after = t.partition(":")
                            code = after.strip()
                            if code and code not in augmented:
                                augmented.append(code)
                    return augmented
                
                include_exact = _augment_with_code(include_exact)
                include_fuzzy = _augment_with_code(include_fuzzy)
                exclude_exact = _augment_with_code(exclude_exact)
                exclude_fuzzy = _augment_with_code(exclude_fuzzy)
            
            # Build include Q for regular fields (OR logic)
            include_q = Q()
            for term in include_exact:
                term_q = Q()
                for field in regular_fields:
                    term_q |= Q(**{f"{field}__iexact": term})
                include_q |= term_q
            
            for term in include_fuzzy:
                term_q = Q()
                for field in regular_fields:
                    term_q |= Q(**{f"{field}__icontains": term})
                include_q |= term_q
            
            # Build exclude Q for regular fields (OR logic - exclude if matches any)
            exclude_q = Q()
            for term in exclude_exact:
                term_q = Q()
                for field in regular_fields:
                    term_q |= Q(**{f"{field}__iexact": term})
                exclude_q |= term_q
            
            for term in exclude_fuzzy:
                term_q = Q()
                for field in regular_fields:
                    term_q |= Q(**{f"{field}__icontains": term})
                exclude_q |= term_q
            
            # Collect matching PKs from regular fields
            include_regular_pks = set()
            if include_q:
                include_regular_pks.update(queryset.filter(include_q).values_list("pk", flat=True))
            
            # Collect matching PKs from encrypted fields (OR logic with regular fields)
            include_encrypted_pks = set()
            if encrypted_fields:
                if include_exact:
                    exact_queryset = _filter_encrypted_fields(queryset, encrypted_fields, include_exact, exact_match=True, exclude=False)
                    exact_pks = list(exact_queryset.values_list("pk", flat=True))
                    include_encrypted_pks.update(exact_pks)
                if include_fuzzy:
                    fuzzy_queryset = _filter_encrypted_fields(queryset, encrypted_fields, include_fuzzy, exact_match=False, exclude=False)
                    fuzzy_pks = list(fuzzy_queryset.values_list("pk", flat=True))
                    include_encrypted_pks.update(fuzzy_pks)
            
            # Combine regular and encrypted PKs with OR logic
            all_include_pks = include_regular_pks | include_encrypted_pks
            
            # Apply include filter
            if all_include_pks:
                queryset = queryset.filter(pk__in=list(all_include_pks))
            elif (include_exact or include_fuzzy or include_q):
                # If we had search terms but no matches, return empty
                queryset = queryset.none()
            
            # Handle exclude filters
            exclude_regular_pks = set()
            if exclude_q:
                exclude_regular_pks.update(queryset.filter(exclude_q).values_list("pk", flat=True))
            
            exclude_encrypted_pks = set()
            if encrypted_fields:
                if exclude_exact:
                    exact_exclude_queryset = _filter_encrypted_fields(queryset, encrypted_fields, exclude_exact, exact_match=True, exclude=False)
                    exact_exclude_pks = list(exact_exclude_queryset.values_list("pk", flat=True))
                    exclude_encrypted_pks.update(exact_exclude_pks)
                if exclude_fuzzy:
                    fuzzy_exclude_queryset = _filter_encrypted_fields(queryset, encrypted_fields, exclude_fuzzy, exact_match=False, exclude=False)
                    fuzzy_exclude_pks = list(fuzzy_exclude_queryset.values_list("pk", flat=True))
                    exclude_encrypted_pks.update(fuzzy_exclude_pks)
            
            # Combine exclude PKs with OR logic
            all_exclude_pks = exclude_regular_pks | exclude_encrypted_pks
            
            # Apply exclude filter
            if all_exclude_pks:
                queryset = queryset.exclude(pk__in=list(all_exclude_pks))
    
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

    # Separate encrypted and regular fields
    encrypted_fields, regular_fields = _separate_encrypted_fields(filter_model, search_fields)

    # Build Q objects for regular fields
    q_objects = Q()
    for filter_value in filter_values:
        # If the value is a digit, it might be a PK (from a combobox selection)
        if filter_value.isdigit():
            q_objects |= Q(pk=filter_value)
        
        # Also search by regular text fields
        for field in regular_fields:
            q_objects |= Q(**{f"{field}__icontains": filter_value})

    # Get PKs from regular field search
    pks_to_filter_by = set()
    if q_objects:
        pks_from_regular = list(filter_model.objects.filter(q_objects).values_list("pk", flat=True).distinct())
        pks_to_filter_by.update(pks_from_regular)
    
    # Handle encrypted fields separately
    if encrypted_fields:
        # Get all objects to search encrypted fields
        base_queryset = filter_model.objects.all()
        if q_objects:
            # If we already have results from regular fields, use those
            base_queryset = base_queryset.filter(q_objects)
        
        for filter_value in filter_values:
            if not filter_value.isdigit():  # Skip numeric values (already handled)
                # Filter by encrypted fields
                encrypted_pks = []
                for obj in base_queryset:
                    match_found = False
                    for field_name in encrypted_fields:
                        field_path_parts = field_name.split('__')
                        field_name_only = field_path_parts[0]
                        
                        try:
                            field_value = getattr(obj, field_name_only)
                            if field_value:
                                field_value_str = str(field_value).lower()
                                if filter_value.lower() in field_value_str:
                                    match_found = True
                                    break
                        except (AttributeError, Exception):
                            continue
                    
                    if match_found:
                        encrypted_pks.append(obj.pk)
                
                if encrypted_pks:
                    pks_to_filter_by.update(encrypted_pks)
                elif not q_objects:
                    # If no regular fields matched and no encrypted fields matched, return empty
                    return queryset.none()

    if not pks_to_filter_by:
        return queryset.none()

    lookup = {f"{orm_path}__in": list(pks_to_filter_by)}
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


def _extract_sort_params(request, target_model_name):
    """Return list of (key, direction) tuples scoped to the target model."""
    model_prefix = target_model_name.lower() + "_"
    params = []
    for key, value in request.GET.items():
        if not key.startswith("sort_"):
            continue
        sort_key = key.replace("sort_", "", 1)
        # Enforce model scoping: expect sort_<model>_<field>
        if not sort_key.startswith(model_prefix):
            continue
        unprefixed = sort_key[len(model_prefix) :]
        direction = (value or "").lower()
        if direction not in ("asc", "desc"):
            continue
        params.append((unprefixed, direction))
    return params


def _annotate_individual_identifier(queryset):
    """Annotate Individuals with a sortable identifier preference: RareBoost, then Biobank, then any."""
    CrossIdentifier = apps.get_model("lab", "CrossIdentifier")
    rare = (
        CrossIdentifier.objects.filter(individual=OuterRef("pk"), id_type__name="RareBoost")
        .order_by("id_value")
        .values("id_value")[:1]
    )
    biobank = (
        CrossIdentifier.objects.filter(individual=OuterRef("pk"), id_type__name="Biobank")
        .order_by("id_value")
        .values("id_value")[:1]
    )
    any_id = (
        CrossIdentifier.objects.filter(individual=OuterRef("pk"))
        .order_by("id_value")
        .values("id_value")[:1]
    )
    return queryset.annotate(
        individual_identifier=Coalesce(
            Subquery(rare, output_field=CharField()),
            Subquery(biobank, output_field=CharField()),
            Subquery(any_id, output_field=CharField()),
            Value(""),
        )
    )


def _annotate_related_identifier(queryset, individual_lookup, annotation_name):
    """Annotate a queryset with an individual's identifier via lookup path."""
    CrossIdentifier = apps.get_model("lab", "CrossIdentifier")
    rare = (
        CrossIdentifier.objects.filter(individual=OuterRef(individual_lookup), id_type__name="RareBoost")
        .order_by("id_value")
        .values("id_value")[:1]
    )
    biobank = (
        CrossIdentifier.objects.filter(individual=OuterRef(individual_lookup), id_type__name="Biobank")
        .order_by("id_value")
        .values("id_value")[:1]
    )
    any_id = (
        CrossIdentifier.objects.filter(individual=OuterRef(individual_lookup))
        .order_by("id_value")
        .values("id_value")[:1]
    )
    return queryset.annotate(
        **{
            annotation_name: Coalesce(
                Subquery(rare, output_field=CharField()),
                Subquery(biobank, output_field=CharField()),
                Subquery(any_id, output_field=CharField()),
                Value(""),
            )
        }
    )


def _annotate_variant_type(queryset, prefix=""):
    """Annotate queryset with a simple variant type label based on child relationships."""
    return queryset.annotate(
        variant_type_label=Coalesce(
            Case(
                When(**{f"{prefix}snv__isnull": False}, then=Value("SNV")),
                When(**{f"{prefix}cnv__isnull": False}, then=Value("CNV")),
                When(**{f"{prefix}sv__isnull": False}, then=Value("SV")),
                When(**{f"{prefix}repeat__isnull": False}, then=Value("Repeat")),
                default=Value("Variant"),
                output_field=CharField(),
            ),
            Value("Variant"),
        )
    )


def get_sort_options(model_name):
    """Expose configured sort options for templates/views."""
    return SORT_CONFIG.get(model_name, SORT_CONFIG.get(model_name.title(), []))


def _apply_sorting(request, target_model_name, queryset):
    """Apply configured sorting options if provided, otherwise default ordering."""
    sort_options = {opt["key"]: opt["field"] for opt in get_sort_options(target_model_name)}
    sort_params = _extract_sort_params(request, target_model_name)

    # Special annotation for Individuals identifier sorting
    needs_identifier = target_model_name == "Individual" and any(
        sort_options.get(sort_key) == "individual_identifier" for sort_key, _ in sort_params
    )
    if needs_identifier:
        queryset = _annotate_individual_identifier(queryset)

    # Special annotation for Project size sorting
    needs_project_size = target_model_name == "Project" and any(
        sort_options.get(sort_key) == "project_size" for sort_key, _ in sort_params
    )
    if needs_project_size:
        queryset = queryset.annotate(project_size=Count("individuals", distinct=True))

    # Related identifier annotations for other models
    if target_model_name == "Sample":
        needs_related_identifier = any(
            sort_options.get(sort_key) == "individual_identifier" for sort_key, _ in sort_params
        )
        if needs_related_identifier:
            queryset = _annotate_related_identifier(queryset, "individual", "individual_identifier")
    elif target_model_name == "Test":
        needs_related_identifier = any(
            sort_options.get(sort_key) == "individual_identifier" for sort_key, _ in sort_params
        )
        if needs_related_identifier:
            queryset = _annotate_related_identifier(queryset, "sample__individual", "individual_identifier")
    elif target_model_name == "Analysis":
        needs_related_identifier = any(
            sort_options.get(sort_key) == "individual_identifier" for sort_key, _ in sort_params
        )
        if needs_related_identifier:
            queryset = _annotate_related_identifier(queryset, "test__sample__individual", "individual_identifier")
    # Variant type annotations
    if target_model_name == "Variant":
        needs_variant_type = any(
            sort_options.get(sort_key) == "variant_type_label" for sort_key, _ in sort_params
        )
        if needs_variant_type:
            queryset = _annotate_variant_type(queryset, prefix="")
    elif target_model_name == "Analysis":
        needs_variant_type = any(
            sort_options.get(sort_key) == "variant_type_label" for sort_key, _ in sort_params
        )
        if needs_variant_type:
            queryset = _annotate_variant_type(queryset, prefix="found_variants__")

    ordering = []
    for sort_key, direction in sort_params:
        field = sort_options.get(sort_key)
        if not field:
            continue
        prefix = "" if direction == "asc" else "-"
        ordering.append(f"{prefix}{field}")

    if not ordering:
        return queryset.order_by("-pk")

    # Provide a deterministic secondary ordering for stable pagination
    if "pk" not in {o.lstrip("-") for o in ordering}:
        ordering.append("-pk")
    return queryset.order_by(*ordering)


def apply_filters(request, target_model_name, queryset, exclude_filter=None):
    """
    Applies search and cross-model filters to a given queryset.
    Handles both generic text search, exact-match select filters, and status filters.
    """
    queryset = _apply_own_search(queryset, target_model_name, request)

    include_filters, exclude_filters = _partition_active_filters(request, exclude_filter)

    # Handle "Task Scope" filter for Tasks (All, Assigned to Me, Assigned by Me)
    if target_model_name == "Task" and "task_scope" in include_filters:
        scope = include_filters["task_scope"]
        # Handle list or string
        if isinstance(scope, list):
            scope = scope[0]
            
        if scope == "assigned_to_me":
            queryset = queryset.filter(assigned_to=request.user)
        elif scope == "assigned_by_me":
            queryset = queryset.filter(created_by=request.user)
            
        # Remove it from include_filters so it's not processed by generic logic
        del include_filters["task_scope"]
        
    # Cleanup old filter if present
    if "assigned_to_me" in include_filters:
        del include_filters["assigned_to_me"]

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
    queryset = _apply_sorting(request, target_model_name, queryset)
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


# Sorting configuration per model. Each option maps a stable key to an ORM field.
SORT_CONFIG = {
    "Individual": [
        {"key": "created_at", "label": "Created", "field": "created_at"},
        {"key": "updated_at", "label": "Updated", "field": "updated_at"},
        {"key": "full_name", "label": "Full Name", "field": "full_name"},
        {"key": "identifier", "label": "Identifier", "field": "individual_identifier"},
        {"key": "status", "label": "Status", "field": "status__name"},
        {"key": "birth_date", "label": "Birth Date", "field": "birth_date"},
        {"key": "age_of_onset", "label": "Age of Onset", "field": "age_of_onset"},
        {"key": "institution", "label": "Institution", "field": "institution__name"},

    ],
    "Sample": [
        {"key": "receipt_date", "label": "Receipt Date", "field": "receipt_date"},
        {"key": "created", "label": "Created", "field": "pk"},
        {"key": "status", "label": "Status", "field": "status__name"},
        {"key": "sample_type", "label": "Sample Type", "field": "sample_type__name"},
        {"key": "individual", "label": "Individual", "field": "individual_identifier"},
        {"key": "receipt_date", "label": "Receipt Date", "field": "receipt_date"},
        {"key": "isolation_by", "label": "Isolation By", "field": "isolation_by__username"},
        {"key": "sample_measurements", "label": "Sample Measurements", "field": "sample_measurements"},
    ],
    "Test": [
        {"key": "performed_date", "label": "Performed Date", "field": "performed_date"},
        {"key": "created", "label": "Created", "field": "pk"},
        {"key": "status", "label": "Status", "field": "status__name"},
        {"key": "test_type", "label": "Test Type", "field": "test_type__name"},
        {"key": "individual", "label": "Individual", "field": "individual_identifier"},
    ],
    "Analysis": [
        {"key": "performed_date", "label": "Performed Date", "field": "performed_date"},
        {"key": "created", "label": "Created", "field": "pk"},
        {"key": "status", "label": "Status", "field": "status__name"},
        {"key": "analysis_type", "label": "Analysis Type", "field": "type__name"},
        {"key": "individual", "label": "Individual", "field": "individual_identifier"},
        {"key": "gene", "label": "Gene", "field": "found_variants__genes__symbol"},
        {"key": "variant", "label": "Variant", "field": "found_variants__pk"},
        {"key": "variant_type", "label": "Variant Type", "field": "variant_type_label"},
    ],
    "Institution": [
        {"key": "name", "label": "Name", "field": "name"},
        {"key": "created", "label": "Created", "field": "pk"},
        {"key": "city", "label": "City", "field": "city"},
        {"key": "speciality", "label": "Speciality", "field": "speciality"},
        {"key": "official_name", "label": "Official Name", "field": "official_name"},
    ],
    "Project": [
        {"key": "due_date", "label": "Due Date", "field": "due_date"},
        {"key": "priority", "label": "Priority", "field": "priority"},
        {"key": "created", "label": "Created", "field": "created_at"},
        {"key": "status", "label": "Status", "field": "status__name"},
        {"key": "size", "label": "Size", "field": "project_size"},
    ],
    "Task": [
        {"key": "due_date", "label": "Due Date", "field": "due_date"},
        {"key": "priority", "label": "Priority", "field": "priority"},
        {"key": "created", "label": "Created", "field": "pk"},
        {"key": "status", "label": "Status", "field": "status__name"},
        {"key": "assigned_to", "label": "Assigned To", "field": "assigned_to__username"},
        {"key": "created_by", "label": "Created By", "field": "created_by__username"},
        {"key": "project", "label": "Project", "field": "project__name"},
    ],
    "Variant": [
        {"key": "position", "label": "Position", "field": "start"},
        {"key": "chromosome", "label": "Chromosome", "field": "chromosome"},
        {"key": "created", "label": "Created", "field": "created_at"},
        {"key": "status", "label": "Status", "field": "status__name"},
        {"key": "start", "label": "Start", "field": "start"},
        {"key": "reference", "label": "Reference", "field": "reference"},
        {"key": "alternate", "label": "Alternate", "field": "alternate"},
        {"key": "zygosity", "label": "Zygosity", "field": "zygosity"},
        {"key": "classification", "label": "Classification", "field": "classifications__classification"},
        {"key": "inheritance", "label": "Inheritance", "field": "classifications__inheritance"},
        {"key": "gene", "label": "Gene", "field": "genes__symbol"},
        {"key": "individual", "label": "Individual", "field": "individual__individual_id"},
        {"key": "variant_type", "label": "Variant Type", "field": "variant_type_label"},
        {"key": "analysis", "label": "Analysis", "field": "analysis__type__name"},
    ]
}
