from django import template
from django.db.models import Q

register = template.Library()


@register.filter
def regroup_by(queryset, attr):
    """Custom filter to regroup a queryset by an attribute"""
    result = {}
    for item in queryset:
        key = getattr(item, attr)
        if key not in result:
            result[key] = []
        result[key].append(item)

    # Convert to a format similar to Django's regroup
    return [{"grouper": key, "list": items} for key, items in result.items()]


@register.simple_tag
def count_by_type(samples, type_name):
    """Count samples by type name"""
    return samples.filter(sample_type__name=type_name).count()


@register.filter
def get_all_tests(individual):
    """Get all unique tests associated with an individual's samples"""
    unique_tests = []
    seen_ids = set()
    for sample in individual.samples.all():
        for test in sample.tests.all():
            if test.id not in seen_ids:
                unique_tests.append(test)
                seen_ids.add(test.id)
    return unique_tests


@register.filter
def get_all_analyses(individual):
    """Get all unique analyses associated with an individual's tests"""
    unique_analyses = []
    seen_ids = set()
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                if analysis.id not in seen_ids:
                    unique_analyses.append(analysis)
                    seen_ids.add(analysis.id)
    return unique_analyses


@register.filter
def pending_tasks(tasks):
    """Filter tasks to only show incomplete ones"""
    if tasks is None:
        return []
    if hasattr(tasks, 'all'):
        tasks = tasks.all()
    return [task for task in tasks if not task.is_completed]


@register.filter
def slice_it(value, arg):
    """Return a slice of the list"""
    try:
        bits = []
        for x in arg.split(":"):
            if not x:
                bits.append(None)
            else:
                bits.append(int(x))
        return value[slice(*bits)]
    except (ValueError, TypeError):
        return value


@register.filter
def split(value, arg):
    """Split a string by the given separator"""
    if value:
        return value.split(arg)
    return []


@register.filter
def strip(value):
    """Strip whitespace from a string"""
    if value:
        return value.strip()
    return value


@register.filter
def filter_by_status(tasks, status):
    """Filter tasks by their completion status"""
    if status == "open":
        return [task for task in tasks if not task.is_completed]
    elif status == "completed":
        return [task for task in tasks if task.is_completed]
    return tasks  # Return all tasks for 'all' status


@register.filter
def filter_by_project(tasks, project_id):
    """Filter tasks by project ID"""
    if project_id:
        return [
            task
            for task in tasks
            if task.project and str(task.project.id) == str(project_id)
        ]
    return tasks


@register.filter
def filter_by_assigned(tasks, user_id):
    """Filter tasks by assigned user"""
    if user_id == "me":
        # This requires that 'request.user' be added to the context
        # in the view function
        return [
            task
            for task in tasks
            if hasattr(task, "assigned_to") and task.assigned_to == "request.user"
        ]
    if user_id:
        return [
            task
            for task in tasks
            if hasattr(task, "assigned_to") and str(task.assigned_to.id) == str(user_id)
        ]
    return tasks


@register.filter
def js_bool(value):
    """Convert Python boolean to JavaScript boolean"""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return value


@register.filter
def visible_to(notes_manager, user):
    """Filter notes to those visible to the given user (public or owned)."""
    if notes_manager is None:
        return []
    if hasattr(notes_manager, 'all'):
        qs = notes_manager.all()
        try:
            return qs.filter(Q(private_owner__isnull=True) | Q(private_owner=user))
        except Exception:
            pass
    result = []
    for n in notes_manager:
        try:
            if getattr(n, 'private_owner_id', None) is None or (user and getattr(n, 'private_owner_id', None) == getattr(user, 'id', None)):
                result.append(n)
        except Exception:
            continue
    return result


@register.filter
def visible_count(notes_manager, user):
    """Count of notes visible to the given user."""
    if notes_manager is None:
        return 0
    if hasattr(notes_manager, 'all'):
        qs = notes_manager.all()
        try:
            return qs.filter(Q(private_owner__isnull=True) | Q(private_owner=user)).count()
        except Exception:
            pass
    return len(visible_to(notes_manager, user))
@register.filter
def plotly_safe(value):
    """Convert Plotly figure data to JavaScript-safe format"""
    import json
    import re
    
    # Convert the dict to JSON string first
    json_str = json.dumps(value)
    
    # Replace Python booleans with JavaScript booleans
    json_str = re.sub(r'\bTrue\b', 'true', json_str)
    json_str = re.sub(r'\bFalse\b', 'false', json_str)
    
    return json_str


@register.filter
def has_analyses(sample):
    """Return True if any test on the sample has at least one analysis."""
    try:
        # Efficient existence check through reverse relation
        return sample.tests.filter(analyses__isnull=False).exists()
    except Exception:
        return False