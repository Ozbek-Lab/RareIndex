from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Optional

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from reversion.models import Version

from lab.models import ImportFieldState


def _flatten_iterable(value: Iterable[Any]) -> list[str]:
    flattened: list[str] = []
    for item in value:
        flattened.append(normalize_import_value(item))
    return flattened


def normalize_import_value(value: Any) -> str:
    """Normalize any supported value into a deterministic string."""
    if value is None:
        return ""
    if isinstance(value, (str, bytes)):
        return str(value).strip()
    if isinstance(value, datetime):
        dt = value
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, models.Model):
        return f"{value._meta.label}:{value.pk}"
    if isinstance(value, dict):
        normalized = {str(k): normalize_import_value(v) for k, v in value.items()}
        return json.dumps(normalized, sort_keys=True)
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return json.dumps(sorted(_flatten_iterable(value)))
    return str(value).strip()


@dataclass
class FieldImportDecision:
    should_update_db: bool
    normalized_value: str
    tracker: Optional[ImportFieldState]
    should_update_tracker: bool


def evaluate_field_import(
    obj: models.Model,
    field_name: str,
    new_value: Any,
    *,
    current_value: Any | None = None,
) -> FieldImportDecision:
    """Determine whether a field should be updated based on prior imports."""

    content_type = ContentType.objects.get_for_model(obj, for_concrete_model=False)
    tracker = ImportFieldState.objects.filter(
        content_type=content_type, object_id=obj.pk, field_name=field_name
    ).first()

    normalized_new = normalize_import_value(new_value)
    if current_value is None:
        current_value = getattr(obj, field_name, None)
    normalized_current = normalize_import_value(current_value)

    if tracker is None:
        should_update = normalized_new != normalized_current
        return FieldImportDecision(
            should_update_db=should_update,
            normalized_value=normalized_new,
            tracker=None,
            should_update_tracker=True,
        )

    last_value = tracker.last_imported_value or ""
    if normalized_new == last_value:
        # Sheet still has the value we previously imported.
        if normalized_current != last_value:
            # Manual change exists; respect it.
            return FieldImportDecision(
                should_update_db=False,
                normalized_value=normalized_new,
                tracker=tracker,
                should_update_tracker=False,
            )
        return FieldImportDecision(
            should_update_db=False,
            normalized_value=normalized_new,
            tracker=tracker,
            should_update_tracker=False,
        )

    if normalized_current == normalized_new:
        # Already matches desired state (maybe updated manually). Only tracker update.
        return FieldImportDecision(
            should_update_db=False,
            normalized_value=normalized_new,
            tracker=tracker,
            should_update_tracker=True,
        )

    return FieldImportDecision(
        should_update_db=True,
        normalized_value=normalized_new,
        tracker=tracker,
        should_update_tracker=True,
    )


def record_field_import(
    obj: models.Model,
    field_name: str,
    normalized_value: str,
    *,
    import_time: datetime | None = None,
    version: Version | None = None,
) -> ImportFieldState:
    """Persist the last import metadata for a field."""

    if import_time is None:
        import_time = timezone.now()

    content_type = ContentType.objects.get_for_model(obj, for_concrete_model=False)
    tracker, _ = ImportFieldState.objects.get_or_create(
        content_type=content_type,
        object_id=obj.pk,
        field_name=field_name,
        defaults={
            "last_imported_at": import_time,
            "last_imported_value": normalized_value,
            "last_version": version,
        },
    )
    tracker.last_imported_at = import_time
    tracker.last_imported_value = normalized_value
    tracker.last_version = version
    tracker.save(update_fields=["last_imported_at", "last_imported_value", "last_version"])
    return tracker

