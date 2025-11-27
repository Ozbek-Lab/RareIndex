from __future__ import annotations

import re
from typing import Callable, Optional

from django.contrib.contenttypes.models import ContentType

from lab.models import Note


def _normalized(content: str) -> str:
    return re.sub(r"[\W_]+", "", (content or "").lower())


def find_similar_note(target_obj, content: str) -> Optional[Note]:
    """Return an existing note with nearly identical text."""

    cleaned = _normalized(content)
    if not cleaned:
        return None

    ct = ContentType.objects.get_for_model(target_obj, for_concrete_model=False)
    for note in Note.objects.filter(content_type=ct, object_id=target_obj.pk):
        if _normalized(note.content) == cleaned:
            return note
    return None


def ensure_note(
    *,
    target_obj,
    content: str,
    user,
    log_warning: Callable[[str], None],
) -> Optional[Note]:
    """Create a note unless a similar one already exists."""

    if not content or not content.strip():
        return None

    similar = find_similar_note(target_obj, content)
    if similar:
        log_warning(
            f"Skipped note on {target_obj} because similar content already exists: {content[:80]}"
        )
        return None

    return Note.objects.create(
        content=content.strip(),
        user=user,
        content_object=target_obj,
    )






