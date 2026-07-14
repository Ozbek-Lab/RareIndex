import unicodedata

from django.db.models import Case, IntegerField, Q, Value, When


_TURKISH_CASE_TRANSLATION = str.maketrans({
    "I": "ı",
    "İ": "i",
})


def normalize_search_text(value):
    """
    Normalize text for human-entered search.

    Python and most database case-insensitive lookups are not Turkish-locale
    aware: "I".lower() becomes "i", while Turkish expects "ı".  Translate the
    Turkish-sensitive capitals before case folding, then remove combining marks
    so diacritic variants are still findable.
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.translate(_TURKISH_CASE_TRANSLATION).casefold()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def normalized_contains(haystack, needle):
    normalized_needle = normalize_search_text(needle).strip()
    if not normalized_needle:
        return True
    return normalized_needle in normalize_search_text(haystack)


def normalized_contains_ids(queryset, field_names, query):
    normalized_query = normalize_search_text(query).strip()
    if not normalized_query:
        return []

    matched_ids = []
    seen_ids = set()
    values = queryset.values_list("pk", *field_names)
    for row in values.iterator(chunk_size=1000):
        pk = row[0]
        if pk in seen_ids:
            continue
        if any(normalized_query in normalize_search_text(value) for value in row[1:]):
            seen_ids.add(pk)
            matched_ids.append(pk)
    return matched_ids


def normalized_contains_q(queryset, field_names, query):
    return Q(pk__in=normalized_contains_ids(queryset, field_names, query))


def filter_normalized_contains(queryset, field_names, query):
    if not str(query or "").strip():
        return queryset
    return queryset.filter(normalized_contains_q(queryset, field_names, query))


def order_by_normalized_relevance(queryset, field_names, query):
    normalized_query = normalize_search_text(query).strip()
    if not normalized_query:
        return queryset
    if isinstance(field_names, str):
        field_names = [field_names]

    ranked_ids = []
    seen_ids = set()
    candidates = []
    for row in queryset.values_list("pk", *field_names).iterator(chunk_size=1000):
        pk = row[0]
        raw_values = row[1:]
        normalized_values = [normalize_search_text(value) for value in raw_values]
        matching_values = [value for value in normalized_values if normalized_query in value]
        if not matching_values:
            continue
        if pk in seen_ids:
            continue
        seen_ids.add(pk)
        display_value = str(raw_values[0] or "")
        candidates.append(
            (
                not any(value == normalized_query for value in matching_values),
                not any(value.startswith(normalized_query) for value in matching_values),
                len(display_value),
                normalized_values[0],
                pk,
            )
        )

    for *_, pk in sorted(candidates):
        ranked_ids.append(pk)
    if not ranked_ids:
        return queryset.none()

    preserved_order = Case(
        *[When(pk=pk, then=Value(index)) for index, pk in enumerate(ranked_ids)],
        output_field=IntegerField(),
    )
    return queryset.filter(pk__in=ranked_ids).annotate(_search_rank=preserved_order).order_by("_search_rank")
