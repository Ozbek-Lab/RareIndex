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
    return tasks.filter(is_completed=False)


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
