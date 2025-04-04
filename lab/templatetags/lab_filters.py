from django import template

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
    unique_tests = set()
    for sample in individual.samples.all():
        for test in sample.tests.all():
            unique_tests.add(test)
    return unique_tests


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
