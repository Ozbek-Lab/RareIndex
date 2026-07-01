from django.dispatch import receiver
from simple_history.signals import post_create_historical_record
from notifications.signals import notify
from django.contrib.auth import get_user_model
from lab.models import Task, Individual, Sample, Test, Analysis, Pipeline, Project

User = get_user_model()

# Helper to get all related users for a model instance
def get_related_users(instance):
    users = set()
    for field in ["assigned_to", "created_by", "performed_by", "isolation_by"]:
        if hasattr(instance, field):
            user = getattr(instance, field, None)
            if user and isinstance(user, User):
                users.add(user)
    if hasattr(instance, "tasks"):
        for task in getattr(instance, "tasks", []).all():
            if hasattr(task, "assigned_to") and task.assigned_to:
                users.add(task.assigned_to)
    return users

# Helper to get a field diff between two historical records
def get_field_diff(new_hist, old_hist):
    if not old_hist:
        return "(First change, no previous record)"
    changes = []
    # Exclude these fields from diff
    ignore_fields = {"history_id", "history_date", "history_type", "history_user", "history_change_reason"}
    for field in new_hist._meta.fields:
        name = field.name
        if name in ignore_fields:
            continue
        new_val = getattr(new_hist, name, None)
        old_val = getattr(old_hist, name, None)
        if new_val != old_val:
            changes.append(f"- {name}: '{old_val}' → '{new_val}'")
    if not changes:
        return "No field values changed."
    return "\n".join(changes)

@receiver(post_create_historical_record)
def notify_on_history(sender, history_instance, **kwargs):
    tracked_models = (Task, Individual, Sample, Test, Analysis, Pipeline, Project)
    instance = history_instance.instance
    if not isinstance(instance, tracked_models):
        return
    users = get_related_users(instance)
    if not users:
        return
    model_name = instance._meta.verbose_name.title()
    action = history_instance.get_history_type_display() if hasattr(history_instance, 'get_history_type_display') else history_instance.history_type
    # Get previous historical record for this object
    history_model = type(history_instance)
    prev_hist = history_model.objects.filter(
        **{instance._meta.pk.name: getattr(history_instance, instance._meta.pk.name)},
        history_date__lt=history_instance.history_date
    ).order_by('-history_date').first()
    field_diff = get_field_diff(history_instance, prev_hist)
    message = f"{model_name} was changed (action: {action})"
    for user in users:
        notify.send(
            sender=instance,
            recipient=user,
            verb=message,
            target=instance,
            description=f"A change was made to {model_name} (ID: {instance.pk})\nChanged fields:\n{field_diff}"
        ) 