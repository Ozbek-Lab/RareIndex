INDIVIDUAL_HISTORY_MASKS = {
    "full_name": "*****",
    "tc_identity": "***********",
    "birth_date": "**-**-****",
}


def historical_model_name(hist_record):
    name = type(hist_record).__name__
    return name.replace("Historical", "", 1) if name.startswith("Historical") else name


def can_view_sensitive_data(user):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and user.has_perm("lab.view_sensitive_data")
    )


def is_sensitive_history_field(hist_record, field_name):
    return (
        historical_model_name(hist_record) == "Individual"
        and field_name in INDIVIDUAL_HISTORY_MASKS
    )


def history_field_value(hist_record, field):
    if getattr(field, "remote_field", None) and getattr(field, "attname", None):
        return getattr(hist_record, field.attname, None)
    return getattr(hist_record, field.name, None)


def display_history_value(hist_record, field_name, value, user):
    if is_sensitive_history_field(hist_record, field_name) and not can_view_sensitive_data(user):
        if value is None:
            return "(empty)"
        return INDIVIDUAL_HISTORY_MASKS[field_name]
    return value if value is not None else "(empty)"


def format_history_diff(
    new_hist,
    old_hist,
    user,
    *,
    title_case_labels=False,
    ignore_fields=None,
):
    if not old_hist:
        return {}

    ignored = set(ignore_fields or ())
    changes = {}
    for field in new_hist._meta.fields:
        name = field.name
        if name in ignored:
            continue

        new_val = history_field_value(new_hist, field)
        old_val = history_field_value(old_hist, field)
        if new_val == old_val:
            continue

        label = name.replace("_", " ").title() if title_case_labels else name
        old_display = display_history_value(new_hist, name, old_val, user)
        new_display = display_history_value(new_hist, name, new_val, user)
        changes[label] = f"'{old_display}' -> '{new_display}'"

    return changes
