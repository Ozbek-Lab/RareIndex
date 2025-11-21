from django import template
from django.core.exceptions import ObjectDoesNotExist
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


@register.filter
def mask_initials(full_name: str) -> str:
    """Mask a full name to initials plus stars per word.

    Examples:
    "Mark Smith" -> "M*** S***"
    "Ada" -> "A***"
    Handles multiple spaces and hyphenated names gracefully.
    """
    if not full_name:
        return ""
    try:
        parts = [p for p in str(full_name).strip().split() if p]
        masked_parts = []
        for part in parts:
            first = part[0]
            masked = f"{first}{'*' * 3}"
            masked_parts.append(masked)
        return " ".join(masked_parts)
    except Exception:
        return ""


@register.simple_tag
def has_model_perm(user, app_label: str, model_name: str, action: str) -> bool:
    """Return True if the user has the specified Django permission on a model.

    action should be one of: 'view', 'add', 'change', 'delete'.
    model_name is the Django model class name (e.g., 'Sample', 'Task').
    """
    try:
        if not getattr(user, "is_authenticated", False):
            return False
        codename = f"{action}_{str(model_name).lower()}"
        return user.has_perm(f"{app_label}.{codename}")
    except Exception:
        return False


@register.filter
def status_changes(instance):
    """Get history records where status changed, with previous status info."""
    if not hasattr(instance, 'history'):
        return []
    
    history_records = list(instance.history.all().order_by('history_date'))
    status_changes_list = []
    
    for i, record in enumerate(history_records):
        # Get previous record
        previous_record = history_records[i - 1] if i > 0 else None
        
        # Check if status changed
        current_status = getattr(record, 'status', None)
        previous_status = getattr(previous_record, 'status', None) if previous_record else None
        
        # Compare status IDs (handle None cases)
        current_status_id = getattr(current_status, 'id', None) if current_status else None
        previous_status_id = getattr(previous_status, 'id', None) if previous_status else None
        
        # Include if status changed, or if it's the first record (creation)
        if i == 0 or (current_status_id != previous_status_id and current_status_id is not None):
            status_changes_list.append({
                'record': record,
                'new_status': current_status,
                'previous_status': previous_status,
                'history_date': record.history_date,
                'history_user': record.history_user,
            })
    
    return status_changes_list


@register.filter
def hierarchical_history(instance):
    """Get history records from instance and all hierarchical children, with status changes and notifications."""
    from lab.models import Individual, Sample, Test, Analysis
    from django.contrib.contenttypes.models import ContentType
    
    all_history = []
    
    # Helper function to get status changes from a history record
    def get_status_change_for_record(record, previous_record):
        current_status = getattr(record, 'status', None)
        previous_status = getattr(previous_record, 'status', None) if previous_record else None
        
        current_status_id = getattr(current_status, 'id', None) if current_status else None
        previous_status_id = getattr(previous_status, 'id', None) if previous_status else None
        
        return {
            'new_status': current_status,
            'previous_status': previous_status,
            'status_changed': current_status_id != previous_status_id if current_status_id is not None else False,
        }
    
    # Process the main instance
    if hasattr(instance, 'history'):
        history_records = list(instance.history.all().order_by('history_date'))
        model_name = instance._meta.verbose_name
        object_id = str(instance)
        
        for i, record in enumerate(history_records):
            previous_record = history_records[i - 1] if i > 0 else None
            status_info = get_status_change_for_record(record, previous_record)
            
            # Include if status changed, or if it's the first record (creation)
            if i == 0 or status_info['status_changed']:
                all_history.append({
                    'type': 'status_change',
                    'record': record,
                    'history_date': record.history_date,
                    'history_user': record.history_user,
                    'model_name': model_name,
                    'object_id': object_id,
                    'object_type': type(instance).__name__,
                    **status_info,
                })
    
    # Process children based on instance type
    if isinstance(instance, Individual):
        # Individual -> Samples -> Tests -> Analyses
        for sample in instance.samples.all():
            if hasattr(sample, 'history'):
                history_records = list(sample.history.all().order_by('history_date'))
                for i, record in enumerate(history_records):
                    previous_record = history_records[i - 1] if i > 0 else None
                    status_info = get_status_change_for_record(record, previous_record)
                    if i == 0 or status_info['status_changed']:
                        all_history.append({
                            'type': 'status_change',
                            'record': record,
                            'history_date': record.history_date,
                            'history_user': record.history_user,
                            'model_name': 'Sample',
                            'object_id': str(sample),
                            'object_type': 'Sample',
                            **status_info,
                        })
                
                # Tests for this sample
                for test in sample.tests.all():
                    if hasattr(test, 'history'):
                        history_records = list(test.history.all().order_by('history_date'))
                        for i, record in enumerate(history_records):
                            previous_record = history_records[i - 1] if i > 0 else None
                            status_info = get_status_change_for_record(record, previous_record)
                            if i == 0 or status_info['status_changed']:
                                all_history.append({
                                    'type': 'status_change',
                                    'record': record,
                                    'history_date': record.history_date,
                                    'history_user': record.history_user,
                                    'model_name': 'Test',
                                    'object_id': str(test),
                                    'object_type': 'Test',
                                    **status_info,
                                })
                    
                    # Analyses for this test
                    for analysis in test.analyses.all():
                        if hasattr(analysis, 'history'):
                            history_records = list(analysis.history.all().order_by('history_date'))
                            for i, record in enumerate(history_records):
                                previous_record = history_records[i - 1] if i > 0 else None
                                status_info = get_status_change_for_record(record, previous_record)
                                if i == 0 or status_info['status_changed']:
                                    all_history.append({
                                        'type': 'status_change',
                                        'record': record,
                                        'history_date': record.history_date,
                                        'history_user': record.history_user,
                                        'model_name': 'Analysis',
                                        'object_id': str(analysis),
                                        'object_type': 'Analysis',
                                        **status_info,
                                    })
    
    elif isinstance(instance, Sample):
        # Sample -> Tests -> Analyses
        for test in instance.tests.all():
            if hasattr(test, 'history'):
                history_records = list(test.history.all().order_by('history_date'))
                for i, record in enumerate(history_records):
                    previous_record = history_records[i - 1] if i > 0 else None
                    status_info = get_status_change_for_record(record, previous_record)
                    if i == 0 or status_info['status_changed']:
                        all_history.append({
                            'type': 'status_change',
                            'record': record,
                            'history_date': record.history_date,
                            'history_user': record.history_user,
                            'model_name': 'Test',
                            'object_id': str(test),
                            'object_type': 'Test',
                            **status_info,
                        })
            
            # Analyses for this test
            for analysis in test.analyses.all():
                if hasattr(analysis, 'history'):
                    history_records = list(analysis.history.all().order_by('history_date'))
                    for i, record in enumerate(history_records):
                        previous_record = history_records[i - 1] if i > 0 else None
                        status_info = get_status_change_for_record(record, previous_record)
                        if i == 0 or status_info['status_changed']:
                            all_history.append({
                                'type': 'status_change',
                                'record': record,
                                'history_date': record.history_date,
                                'history_user': record.history_user,
                                'model_name': 'Analysis',
                                'object_id': str(analysis),
                                'object_type': 'Analysis',
                                **status_info,
                            })
    
    elif isinstance(instance, Test):
        # Test -> Analyses
        for analysis in instance.analyses.all():
            if hasattr(analysis, 'history'):
                history_records = list(analysis.history.all().order_by('history_date'))
                for i, record in enumerate(history_records):
                    previous_record = history_records[i - 1] if i > 0 else None
                    status_info = get_status_change_for_record(record, previous_record)
                    if i == 0 or status_info['status_changed']:
                        all_history.append({
                            'type': 'status_change',
                            'record': record,
                            'history_date': record.history_date,
                            'history_user': record.history_user,
                            'model_name': 'Analysis',
                            'object_id': str(analysis),
                            'object_type': 'Analysis',
                            **status_info,
                        })
    
    # Collect all related objects for notification lookup
    related_objects = [instance]
    
    if isinstance(instance, Individual):
        for sample in instance.samples.all():
            related_objects.append(sample)
            for test in sample.tests.all():
                related_objects.append(test)
                for analysis in test.analyses.all():
                    related_objects.append(analysis)
    elif isinstance(instance, Sample):
        for test in instance.tests.all():
            related_objects.append(test)
            for analysis in test.analyses.all():
                related_objects.append(analysis)
    elif isinstance(instance, Test):
        for analysis in instance.analyses.all():
            related_objects.append(analysis)
    
    # Get notifications for all related objects
    try:
        from notifications.models import Notification
        
        # Get ContentTypes for all related objects
        for obj in related_objects:
            content_type = ContentType.objects.get_for_model(obj)
            notifications = Notification.objects.filter(
                target_content_type=content_type,
                target_object_id=obj.pk
            ).order_by('timestamp')
            
            for notification in notifications:
                try:
                    # Get the target object to determine model data
                    target_obj = notification.target
                except ObjectDoesNotExist:
                    # Target was deleted; skip this orphaned notification
                    continue

                if target_obj is None:
                    model_name = 'Unknown'
                    object_id = f'ID: {notification.target_object_id}'
                    object_type = 'Unknown'
                else:
                    model_name = target_obj._meta.verbose_name
                    object_id = str(target_obj)
                    object_type = type(target_obj).__name__
                
                all_history.append({
                    'type': 'notification',
                    'notification': notification,
                    'history_date': notification.timestamp,
                    'history_user': None,  # Notifications don't have a direct user field
                    'model_name': model_name,
                    'object_id': object_id,
                    'object_type': object_type,
                    'verb': notification.verb,
                    'description': notification.description,
                    'new_status': None,
                    'previous_status': None,
                })
    except ImportError:
        # notifications app not available
        pass
    except Exception:
        # Handle any other errors gracefully
        pass
    
    # Sort all history by date
    all_history.sort(key=lambda x: x['history_date'])
    
    return all_history