from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from lab.models import Individual
from lab.models import StatusLog
from django.contrib.contenttypes.models import ContentType
import json
from django.shortcuts import render

@login_required
def timeline(request, pk):
    """Generate timeline data for an individual and all related objects"""
    individual = get_object_or_404(Individual, pk=pk)
    
    timeline_events = []
    
    # Get individual history and important dates (excluding creation events)
    for record in individual.history.all():
        if 'created' not in record.get_history_type_display().lower():
            timeline_events.append({
                'date': record.history_date,
                'type': 'individual',
                'action': record.get_history_type_display(),
                'description': f"Individual {record.get_history_type_display().lower()}",
                'user': record.history_user.username if record.history_user else 'System',
                'object_name': 'Individual',
                'object_id': individual.individual_id,
                'details': f"Status: {record.status.name if record.status else 'N/A'}"
            })
    
    # Add individual's created_at date
    timeline_events.append({
        'date': individual.created_at,
        'type': 'individual',
        'action': 'Created',
        'description': f"Individual {individual.individual_id} created",
        'user': 'System',
        'object_name': 'Individual',
        'object_id': individual.individual_id,
        'details': f"Individual ID: {individual.individual_id}, Created: {individual.created_at.date()}"
    })
    
    # Add individual's important dates
    if individual.council_date:
        timeline_events.append({
            'date': individual.council_date,
            'type': 'individual',
            'action': 'Council Date',
            'description': 'Council Date',
            'user': 'System',
            'object_name': 'Individual',
            'object_id': individual.individual_id,
            'details': f"Council Date: {individual.council_date}"
        })
    
    if individual.diagnosis_date:
        timeline_events.append({
            'date': individual.diagnosis_date,
            'type': 'individual',
            'action': 'Diagnosis Date',
            'description': 'Diagnosis Date',
            'user': 'System',
            'object_name': 'Individual',
            'object_id': individual.individual_id,
            'details': f"Diagnosis Date: {individual.diagnosis_date}"
        })
    
    # Get sample history and important dates
    for sample in individual.samples.all():
        # Add the actual created_at date
        timeline_events.append({
            'date': sample.created_at,
            'type': 'sample',
            'action': 'Created',
            'description': f"Sample {sample.id} created",
            'user': 'System',
            'object_name': 'Sample',
            'object_id': f"Sample {sample.id}",
            'details': f"Type: {sample.sample_type.name}, Created: {sample.created_at.date()}"
        })
        
        for record in sample.history.all():
            if 'created' not in record.get_history_type_display().lower():
                timeline_events.append({
                    'date': record.history_date,
                    'type': 'sample',
                    'action': record.get_history_type_display()+"Sample",
                    'description': f"Sample {record.get_history_type_display().lower()}",
                    'user': record.history_user.username if record.history_user else 'System',
                    'object_name': 'Sample',
                    'object_id': f"Sample {sample.id}",
                    'details': f"Type: {sample.sample_type.name}, Status: {record.status.name if record.status else 'N/A'}"
                })
        
        # Add sample's important dates
        if sample.receipt_date:
            timeline_events.append({
                'date': sample.receipt_date,
                'type': 'sample',
                'action': 'Receipt Date',
                'description': 'Sample Received',
                'user': 'System',
                'object_name': 'Sample',
                'object_id': f"Sample {sample.id}",
                'details': f"Sample Type: {sample.sample_type.name}, Receipt Date: {sample.receipt_date}"
            })
        
        if sample.processing_date:
            timeline_events.append({
                'date': sample.processing_date,
                'type': 'sample',
                'action': 'Processing Date',
                'description': 'Sample Processed',
                'user': 'System',
                'object_name': 'Sample',
                'object_id': f"Sample {sample.id}",
                'details': f"Sample Type: {sample.sample_type.name}, Processing Date: {sample.processing_date}"
            })
    
    # Get test history and important dates
    for sample in individual.samples.all():
        for test in sample.tests.all():
            # Add the actual created_at date
            timeline_events.append({
                'date': test.created_at,
                'type': 'test',
                'action': 'Created',
                'description': f"Test {test.id} created",
                'user': 'System',
                'object_name': 'Test',
                'object_id': f"Test {test.id}",
                'details': f"Type: {test.test_type.name}, Created: {test.created_at.date()}"
            })
            
            for record in test.history.all():
                if 'created' not in record.get_history_type_display().lower():
                    timeline_events.append({
                        'date': record.history_date,
                        'type': 'test',
                        'action': record.get_history_type_display(),
                        'description': f"Test {record.get_history_type_display().lower()}",
                        'user': record.history_user.username if record.history_user else 'System',
                        'object_name': 'Test',
                        'object_id': f"Test {test.id}",
                        'details': f"Type: {test.test_type.name}, Status: {record.status.name if record.status else 'N/A'}"
                    })
            
            # Add test's important dates
            if test.performed_date:
                timeline_events.append({
                    'date': test.performed_date,
                    'type': 'test',
                    'action': 'Performed Date',
                    'description': 'Test Performed',
                    'user': test.performed_by.username if test.performed_by else 'System',
                    'object_name': 'Test',
                    'object_id': f"Test {test.id}",
                    'details': f"Test Type: {test.test_type.name}, Performed Date: {test.performed_date}"
                })
            
            if test.service_send_date:
                timeline_events.append({
                    'date': test.service_send_date,
                    'type': 'test',
                    'action': 'Service Send Date',
                    'description': 'Test Sent to Service',
                    'user': 'System',
                    'object_name': 'Test',
                    'object_id': f"Test {test.id}",
                    'details': f"Test Type: {test.test_type.name}, Service Send Date: {test.service_send_date}"
                })
            
            if test.data_receipt_date:
                timeline_events.append({
                    'date': test.data_receipt_date,
                    'type': 'test',
                    'action': 'Data Receipt Date',
                    'description': 'Test Data Received',
                    'user': 'System',
                    'object_name': 'Test',
                    'object_id': f"Test {test.id}",
                    'details': f"Test Type: {test.test_type.name}, Data Receipt Date: {test.data_receipt_date}"
                })
    
    # Get analysis history and important dates
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                # Add the actual created_at date
                timeline_events.append({
                    'date': analysis.created_at,
                    'type': 'analysis',
                    'action': 'Created',
                    'description': f"Analysis {analysis.id} created",
                    'user': 'System',
                    'object_name': 'Analysis',
                    'object_id': f"Analysis {analysis.id}",
                    'details': f"Type: {analysis.type.name}, Created: {analysis.created_at.date()}"
                })
                
                for record in analysis.history.all():
                    if 'created' not in record.get_history_type_display().lower():
                        timeline_events.append({
                            'date': record.history_date,
                            'type': 'analysis',
                            'action': record.get_history_type_display(),
                            'description': f"Analysis {record.get_history_type_display().lower()}",
                            'user': record.history_user.username if record.history_user else 'System',
                            'object_name': 'Analysis',
                            'object_id': f"Analysis {analysis.id}",
                            'details': f"Type: {analysis.type.name}, Status: {record.status.name if record.status else 'N/A'}"
                        })
                
                # Add analysis's important dates
                if analysis.performed_date:
                    timeline_events.append({
                        'date': analysis.performed_date,
                        'type': 'analysis',
                        'action': 'Performed Date',
                        'description': 'Analysis Performed',
                        'user': analysis.performed_by.username,
                        'object_name': 'Analysis',
                        'object_id': f"Analysis {analysis.id}",
                        'details': f"Analysis Type: {analysis.type.name}, Performed Date: {analysis.performed_date}"
                    })
    
    # Get task history and important dates
    for task in individual.tasks.all():
        # Add the actual created_at date
        timeline_events.append({
            'date': task.created_at,
            'type': 'task',
            'action': 'Created',
            'description': f"Task {task.id} created",
            'user': 'System',
            'object_name': 'Task',
            'object_id': f"Task {task.id}",
            'details': f"Title: {task.title}, Created: {task.created_at.date()}"
        })
        
        for record in task.history.all():
            if 'created' not in record.get_history_type_display().lower():
                timeline_events.append({
                    'date': record.history_date,
                    'type': 'task',
                    'action': record.get_history_type_display(),
                    'description': f"Task {record.get_history_type_display().lower()}",
                    'user': record.history_user.username if record.history_user else 'System',
                    'object_name': 'Task',
                    'object_id': f"Task {task.id}",
                    'details': f"Priority: {record.priority}, Status: {record.status.name if record.status else 'N/A'}"
                })
        
        # Add task's important dates
        if task.due_date:
            timeline_events.append({
                'date': task.due_date,
                'type': 'task',
                'action': 'Due Date',
                'description': 'Task Due Date',
                'user': 'System',
                'object_name': 'Task',
                'object_id': f"Task {task.id}",
                'details': f"Task: {task.title}, Due Date: {task.due_date}, Priority: {task.priority}"
            })
    
    # Get notes (created_at and updated_at dates)
    for note in individual.notes.all():
        timeline_events.append({
            'date': note.created_at,
            'type': 'note',
            'action': 'Created',
            'description': 'Note added',
            'user': note.user.username,
            'object_name': 'Note',
            'object_id': f"Note {note.id}",
            'details': note.content[:100] + '...' if len(note.content) > 100 else note.content
        })
        
        # Add note update if it was modified
        if note.updated_at and note.updated_at != note.created_at:
            timeline_events.append({
                'date': note.updated_at,
                'type': 'note',
                'action': 'Updated',
                'description': 'Note updated',
                'user': note.user.username,
                'object_name': 'Note',
                'object_id': f"Note {note.id}",
                'details': note.content[:100] + '...' if len(note.content) > 100 else note.content
            })
    
    # Get sample tasks and notes
    for sample in individual.samples.all():
        # Sample tasks
        for task in sample.tasks.all():
            timeline_events.append({
                'date': task.created_at,
                'type': 'task',
                'action': 'Created',
                'description': f"Task {task.id} created",
                'user': 'System',
                'object_name': 'Task',
                'object_id': f"Task {task.id}",
                'details': f"Sample: {sample.id}, Title: {task.title}, Created: {task.created_at.date()}"
            })
            
            for record in task.history.all():
                if 'created' not in record.get_history_type_display().lower():
                    timeline_events.append({
                        'date': record.history_date,
                        'type': 'task',
                        'action': record.get_history_type_display(),
                        'description': f"Task {record.get_history_type_display().lower()}",
                        'user': record.history_user.username if record.history_user else 'System',
                        'object_name': 'Task',
                        'object_id': f"Task {task.id}",
                        'details': f"Sample: {sample.id}, Priority: {record.priority}, Status: {record.status.name if record.status else 'N/A'}"
                    })
            
            # Add task's important dates
            if task.due_date:
                timeline_events.append({
                    'date': task.due_date,
                    'type': 'task',
                    'action': 'Due Date',
                    'description': 'Task Due Date',
                    'user': 'System',
                    'object_name': 'Task',
                    'object_id': f"Task {task.id}",
                    'details': f"Sample: {sample.id}, Task: {task.title}, Due Date: {task.due_date}, Priority: {task.priority}"
                })
        
        # Sample notes
        for note in sample.notes.all():
            timeline_events.append({
                'date': note.created_at,
                'type': 'note',
                'action': 'Created',
                'description': 'Note added',
                'user': note.user.username,
                'object_name': 'Note',
                'object_id': f"Note {note.id}",
                'details': f"Sample: {sample.id}, Content: {note.content[:100]}{'...' if len(note.content) > 100 else ''}"
            })
            
            # Add note update if it was modified
            if note.updated_at and note.updated_at != note.created_at:
                    timeline_events.append({
                        'date': note.updated_at,
                        'type': 'note',
                        'action': 'Updated',
                        'description': 'Note updated',
                        'user': note.user.username,
                        'object_name': 'Note',
                        'object_id': f"Note {note.id}",
                        'details': f"Sample: {sample.id}, Content: {note.content[:100]}{'...' if len(note.content) > 100 else ''}"
                    })
    
    # Get test tasks and notes
    for sample in individual.samples.all():
        for test in sample.tests.all():
            # Test tasks
            for task in test.tasks.all():
                timeline_events.append({
                    'date': task.created_at,
                    'type': 'task',
                    'action': 'Created',
                    'description': f"Task {task.id} created",
                    'user': 'System',
                    'object_name': 'Task',
                    'object_id': f"Task {task.id}",
                    'details': f"Test: {test.id}, Title: {task.title}, Created: {task.created_at.date()}"
                })
                
                for record in task.history.all():
                    if 'created' not in record.get_history_type_display().lower():
                        timeline_events.append({
                            'date': record.history_date,
                            'type': 'task',
                            'action': record.get_history_type_display(),
                            'description': f"Task {record.get_history_type_display().lower()}",
                            'user': record.history_user.username if record.history_user else 'System',
                            'object_name': 'Task',
                            'object_id': f"Task {task.id}",
                            'details': f"Test: {test.id}, Priority: {record.priority}, Status: {record.status.name if record.status else 'N/A'}"
                        })
                
                # Add task's important dates
                if task.due_date:
                    timeline_events.append({
                        'date': task.due_date,
                        'type': 'task',
                        'action': 'Due Date',
                        'description': 'Task Due Date',
                        'user': 'System',
                        'object_name': 'Task',
                        'object_id': f"Task {task.id}",
                        'details': f"Test: {test.id}, Task: {task.title}, Due Date: {task.due_date}, Priority: {task.priority}"
                    })
            
            # Test notes
            for note in test.notes.all():
                timeline_events.append({
                    'date': note.created_at,
                    'type': 'note',
                    'action': 'Created',
                    'description': 'Note added',
                    'user': note.user.username,
                    'object_name': 'Note',
                    'object_id': f"Note {note.id}",
                    'details': f"Test: {test.id}, Content: {note.content[:100]}{'...' if len(note.content) > 100 else ''}"
                })
                
                # Add note update if it was modified
                if note.updated_at and note.updated_at != note.created_at:
                    timeline_events.append({
                        'date': note.updated_at,
                        'type': 'note',
                        'action': 'Updated',
                        'description': 'Note updated',
                        'user': note.user.username,
                        'object_name': 'Note',
                        'object_id': f"Note {note.id}",
                        'details': f"Test: {test.id}, Content: {note.content[:100]}{'...' if len(note.content) > 100 else ''}"
                    })
    
    # Get analysis tasks and notes
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                # Analysis tasks
                for task in analysis.tasks.all():
                    timeline_events.append({
                        'date': task.created_at,
                        'type': 'task',
                        'action': 'Created',
                        'description': f"Task {task.id} created",
                        'user': 'System',
                        'object_name': 'Task',
                        'object_id': f"Task {task.id}",
                        'details': f"Analysis: {analysis.id}, Title: {task.title}, Created: {task.created_at.date()}"
                    })
                    
                    for record in task.history.all():
                        if 'created' not in record.get_history_type_display().lower():
                            timeline_events.append({
                                'date': record.history_date,
                                'type': 'task',
                                'action': record.get_history_type_display(),
                                'description': f"Task {record.get_history_type_display().lower()}",
                                'user': record.history_user.username if record.history_user else 'System',
                                'object_name': 'Task',
                                'object_id': f"Task {task.id}",
                                'details': f"Analysis: {analysis.id}, Priority: {record.priority}, Status: {record.status.name if record.status else 'N/A'}"
                            })
                    
                    # Add task's important dates
                    if task.due_date:
                        timeline_events.append({
                            'date': task.due_date,
                            'type': 'task',
                            'action': 'Due Date',
                            'description': 'Task Due Date',
                            'user': 'System',
                            'object_name': 'Task',
                            'object_id': f"Task {task.id}",
                            'details': f"Analysis: {analysis.id}, Task: {task.title}, Due Date: {task.due_date}, Priority: {task.priority}"
                        })
                
                # Analysis notes
                for note in analysis.notes.all():
                    timeline_events.append({
                        'date': note.created_at,
                        'type': 'note',
                        'action': 'Created',
                        'description': 'Note added',
                        'user': note.user.username,
                        'object_name': 'Note',
                        'object_id': f"Note {note.id}",
                        'details': f"Analysis: {analysis.id}, Content: {note.content[:100]}{'...' if len(note.content) > 100 else ''}"
                    })
                    
                    # Add note update if it was modified
                    if note.updated_at and note.updated_at != note.created_at:
                        timeline_events.append({
                            'date': note.updated_at,
                            'type': 'note',
                            'action': 'Updated',
                            'description': 'Note updated',
                            'user': note.user.username,
                            'object_name': 'Note',
                            'object_id': f"Note {note.id}",
                            'details': f"Analysis: {analysis.id}, Content: {note.content[:100]}{'...' if len(note.content) > 100 else ''}"
                        })
    

    
    # Get status log entries
    for status_log in StatusLog.objects.filter(
        content_type=ContentType.objects.get_for_model(Individual),
        object_id=individual.id
    ):
        timeline_events.append({
            'date': status_log.changed_at,
            'type': 'individual',
            'action': 'Status Changed',
            'description': f"Status changed from {status_log.previous_status.name} to {status_log.new_status.name}",
            'user': status_log.changed_by.username,
            'object_name': 'Individual',
            'object_id': individual.individual_id,
            'details': f"Previous: {status_log.previous_status.name}, New: {status_log.new_status.name}, Notes: {status_log.notes}"
        })
    
    # Convert all dates to timezone-aware datetime.datetime objects and sort timeline events by date
    from datetime import datetime, time, date
    from django.utils import timezone
    
    for event in timeline_events:
        if isinstance(event['date'], date) and not isinstance(event['date'], datetime):
            # Convert date to timezone-aware datetime at midnight
            event['date'] = timezone.make_aware(datetime.combine(event['date'], time.min))
        elif isinstance(event['date'], datetime) and timezone.is_naive(event['date']):
            # Convert naive datetime to timezone-aware
            event['date'] = timezone.make_aware(event['date'])
    
    for event in timeline_events:
        if isinstance(event['date'], datetime):
            # Convert datetime to date
            event['date'] = event['date'].date()
    # If it's already a date (but not a datetime), leave as is

    timeline_events.sort(key=lambda x: x['date'], reverse=True)

    # Prepare data for Plotly timeline - use only date objects and assign hierarchical positions
    from django.utils import timezone
    
    # Pre-calculate y-positions using depth-first search
    sample_positions = {}
    test_positions = {}
    analysis_positions = {}
    task_positions = {}
    note_positions = {}
    
    # Configuration
    sample_offset = 1
    test_offset = 0.5
    analysis_offset = 0.25
    
    # Assign y-positions using depth-first search with chronological ordering within each level
    current_y = 0  # Individual is at 0
    
    # Process samples and their children in chronological order
    all_samples = list(individual.samples.all())
    all_samples.sort(key=lambda s: s.created_at.date() if s.created_at else date(2025, 1, 1))
    
    for sample in all_samples:
        # Assign sample position
        sample_positions[sample.id] = current_y + sample_offset
        current_y = sample_positions[sample.id]
        
        # Process tests for this sample in chronological order
        all_tests = list(sample.tests.all())
        all_tests.sort(key=lambda t: t.created_at.date() if t.created_at else date(2025, 1, 1))
        
        for test in all_tests:
            # Assign test position
            test_positions[test.id] = current_y + test_offset
            current_y = test_positions[test.id]
            
            # Process analyses for this test in chronological order
            all_analyses = list(test.analyses.all())
            all_analyses.sort(key=lambda a: a.created_at.date() if a.created_at else date(2025, 1, 1))
            
            for analysis in all_analyses:
                # Assign analysis position
                analysis_positions[analysis.id] = current_y + analysis_offset
                current_y = analysis_positions[analysis.id]
    
    # Process individual tasks and notes in chronological order (mixed together)
    current_y = -0.25  # Start at -0.25 for individual tasks and notes
    
    all_tasks = list(individual.tasks.all())
    all_notes = list(individual.notes.all())
    
    # Combine and sort by creation date
    tasks_and_notes = [(task, 'task') for task in all_tasks] + [(note, 'note') for note in all_notes]
    tasks_and_notes.sort(key=lambda x: x[0].created_at.date() if x[0].created_at else date(2025, 1, 1))
    
    for obj, obj_type in tasks_and_notes:
        if obj_type == 'task':
            task_positions[obj.id] = current_y
            current_y -= 0.25
        elif obj_type == 'note':
            note_positions[obj.id] = current_y
            current_y -= 0.25
    
    # Now process timeline events with pre-assigned positions
    y_positions = []
    dates = []
    descriptions = []
    types = []
    users = []
    details = []
    
    for event in timeline_events:
        # Convert dates to ISO format strings for Plotly (YYYY-MM-DD)
        dates.append(event['date'].isoformat())
        descriptions.append(event['description'])
        types.append(event['type'])
        users.append(event['user'])
        details.append(event['details'])
        
        # Assign y-position based on pre-calculated positions
        if event['type'] == 'individual':
            y_positions.append(0)  # Main timeline
        elif event['type'] == 'sample':
            sample_id = int(event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id'])
            y_positions.append(sample_positions.get(sample_id, 0))
        elif event['type'] == 'test':
            test_id = int(event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id'])
            y_positions.append(test_positions.get(test_id, 0))
        elif event['type'] == 'analysis':
            analysis_id = int(event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id'])
            y_positions.append(analysis_positions.get(analysis_id, 0))
        elif event['type'] == 'task':
            task_id = int(event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id'])
            y_positions.append(task_positions.get(task_id, 0))
        elif event['type'] == 'note':
            note_id = int(event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id'])
            y_positions.append(note_positions.get(note_id, 0))
        else:
            y_positions.append(0)  # Default to main timeline
    
    
    # Color mapping for different types
    color_map = {
        'individual': '#1f77b4',
        'sample': '#ff7f0e', 
        'test': '#2ca02c',
        'analysis': '#d62728',
        'task': '#9467bd',
        'note': '#8c564b'
    }
    
    # Width mapping for different types
    width_map = {
        'individual': 3,
        'sample': 2, 
        'test': 2,
        'analysis': 2,
        'task': 2,
        'note': 2
    }
    
    colors = [color_map.get(event_type, '#7f7f7f') for event_type in types]
    
    # Create Plotly figure
    import plotly.graph_objects as go
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=dates,
        y=y_positions,  # Use hierarchical y-positions
        mode='markers',
        marker=dict(    
            size=12,
            color=colors,
            symbol='circle'
        ),
        text=descriptions,
        textposition='top center',
        hovertemplate='<b>%{text}</b><br>' +
                     'Date: %{x}<br>' +
                     'Action: %{customdata[2]}<br>' +
                     'User: %{customdata[0]}<br>' +
                     'Details: %{customdata[1]}<br>' +
                     '<extra></extra>',
        customdata=list(zip(users, details, [event['action'] for event in timeline_events])),
        name='Timeline Events'
    ))

    # Add lines connecting events for the same object
    from collections import defaultdict
    object_event_lines = defaultdict(list)
    for i, event in enumerate(timeline_events):
        object_event_lines[event['object_id']].append((dates[i], y_positions[i]))

    for object_id, points in object_event_lines.items():
        if len(points) > 1:
            points.sort()
            x_vals, y_vals = zip(*points)
            # Determine the color based on the object type
            object_type = None
            for event in timeline_events:
                if event['object_id'] == object_id:
                    object_type = event['type']
                    break
            line_color = color_map.get(object_type, '#7f7f7f')
            fig.add_trace(go.Scatter(
                x=x_vals,
                y=y_vals,
                mode='lines',
                line=dict(width=2, color=line_color),
                showlegend=False,
                hoverinfo='skip',
            ))
    
    # Add horizontal lines for each level of the hierarchy with proper branching
    max_y = max(y_positions) if y_positions else 0
    min_y = min(y_positions) if y_positions else 0
    
    # Individual line - from created_at to now
    from datetime import date
    individual_created = individual.created_at.date().isoformat() if individual.created_at else '2025-01-01'
    fig.add_shape(
        type='line',
        x0=individual_created,
        x1=date.today().isoformat(),
        y0=0,
        y1=0,
        line=dict(color=color_map['individual'], width=width_map['individual'])
    )
    
    # Get actual creation dates from models
    sample_creation_dates = {}
    test_creation_dates = {}
    analysis_creation_dates = {}
    
    # Get sample creation dates
    for sample in individual.samples.all():
        sample_creation_dates[sample.id] = sample.created_at.date().isoformat()
    
    # Get test creation dates
    for sample in individual.samples.all():
        for test in sample.tests.all():
            test_creation_dates[test.id] = test.created_at.date().isoformat()
    
    # Get analysis creation dates
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                analysis_creation_dates[analysis.id] = analysis.created_at.date().isoformat()
    

    
    # Sample lines - from created_at to now
    for sample in individual.samples.all():
        if sample.id in sample_positions:
            sample_created = sample.created_at.date().isoformat() if sample.created_at else '2025-01-01'
            fig.add_shape(
                type='line',
                x0=sample_created,
                x1=date.today().isoformat(),
                y0=sample_positions[sample.id],
                y1=sample_positions[sample.id],
                line=dict(color=color_map['sample'], width=width_map['sample'])
            )
    
    # Test lines - from created_at to now
    for sample in individual.samples.all():
        for test in sample.tests.all():
            if test.id in test_positions:
                test_created = test.created_at.date().isoformat() if test.created_at else '2025-01-01'
                fig.add_shape(
                    type='line',
                    x0=test_created,
                    x1=date.today().isoformat(),
                    y0=test_positions[test.id],
                    y1=test_positions[test.id],
                    line=dict(color=color_map['test'], width=width_map['test'])
                )
    
    # Analysis lines - from created_at to now
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                if analysis.id in analysis_positions:
                    analysis_created = analysis.created_at.date().isoformat() if analysis.created_at else '2025-01-01'
                    fig.add_shape(
                        type='line',
                        x0=analysis_created,
                        x1=date.today().isoformat(),
                        y0=analysis_positions[analysis.id],
                        y1=analysis_positions[analysis.id],
                        line=dict(color=color_map['analysis'], width=width_map['analysis'])
                    )
    
    # Task lines - from created_at to due_date (or now if no due_date)
    for task in individual.tasks.all():
        if task.id in task_positions:
            task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
            task_end = task.due_date.isoformat() if task.due_date else date.today().isoformat()
            fig.add_shape(
                type='line',
                x0=task_created,
                x1=task_end,
                y0=task_positions[task.id],
                y1=task_positions[task.id],
                line=dict(color=color_map['task'], width=width_map['task'])
            )
    
    # Note lines - from created_at to now
    for note in individual.notes.all():
        if note.id in note_positions:
            note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
            fig.add_shape(
                type='line',
                x0=note_created,
                x1=date.today().isoformat(),
                y0=note_positions[note.id],
                y1=note_positions[note.id],
                line=dict(color=color_map['note'], width=width_map['note'])
            )
    
    # Sample task lines - from created_at to due_date (or now if no due_date)
    for sample in individual.samples.all():
        for task in sample.tasks.all():
            if task.id in task_positions:
                task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
                task_end = task.due_date.isoformat() if task.due_date else date.today().isoformat()
                fig.add_shape(
                    type='line',
                    x0=task_created,
                    x1=task_end,
                    y0=task_positions[task.id],
                    y1=task_positions[task.id],
                    line=dict(color=color_map['task'], width=width_map['task'])
                )
    
    # Sample note lines - from created_at to now
    for sample in individual.samples.all():
        for note in sample.notes.all():
            if note.id in note_positions:
                note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
                fig.add_shape(
                    type='line',
                    x0=note_created,
                    x1=date.today().isoformat(),
                    y0=note_positions[note.id],
                    y1=note_positions[note.id],
                    line=dict(color=color_map['note'], width=width_map['note'])
                )
    
    # Test task lines - from created_at to due_date (or now if no due_date)
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for task in test.tasks.all():
                if task.id in task_positions:
                    task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
                    task_end = task.due_date.isoformat() if task.due_date else date.today().isoformat()
                    fig.add_shape(
                        type='line',
                        x0=task_created,
                        x1=task_end,
                        y0=task_positions[task.id],
                        y1=task_positions[task.id],
                        line=dict(color=color_map['task'], width=width_map['task'])
                    )
    
    # Test note lines - from created_at to now
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for note in test.notes.all():
                if note.id in note_positions:
                    note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
                    fig.add_shape(
                        type='line',
                        x0=note_created,
                        x1=date.today().isoformat(),
                        y0=note_positions[note.id],
                        y1=note_positions[note.id],
                        line=dict(color=color_map['note'], width=width_map['note'])
                    )
    
    # Analysis task lines - from created_at to due_date (or now if no due_date)
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                for task in analysis.tasks.all():
                    if task.id in task_positions:
                        task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
                        task_end = task.due_date.isoformat() if task.due_date else date.today().isoformat()
                        fig.add_shape(
                            type='line',
                            x0=task_created,
                            x1=task_end,
                            y0=task_positions[task.id],
                            y1=task_positions[task.id],
                            line=dict(color=color_map['task'], width=width_map['task'])
                        )
    
    # Analysis note lines - from created_at to now
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                for note in analysis.notes.all():
                    if note.id in note_positions:
                        note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
                        fig.add_shape(
                            type='line',
                            x0=note_created,
                            x1=date.today().isoformat(),
                            y0=note_positions[note.id],
                            y1=note_positions[note.id],
                            line=dict(color=color_map['note'], width=width_map['note'])
                        )
    

    
    # Add vertical lines connecting object creation points hierarchically
    # Sample creation vertical lines - connect to individual
    for sample in individual.samples.all():
        if sample.id in sample_positions:
            sample_created = sample.created_at.date().isoformat() if sample.created_at else '2025-01-01'
            fig.add_shape(
                type='line',
                x0=sample_created,
                x1=sample_created,
                y0=0,  # Individual timeline
                y1=sample_positions[sample.id],  # Sample position
                line=dict(color=color_map['sample'], width=width_map['sample'], dash='dot')
            )
    
    # Test creation vertical lines - connect to their sample
    for sample in individual.samples.all():
        for test in sample.tests.all():
            if test.id in test_positions and sample.id in sample_positions:
                test_created = test.created_at.date().isoformat() if test.created_at else '2025-01-01'
                fig.add_shape(
                    type='line',
                    x0=test_created,
                    x1=test_created,
                    y0=sample_positions[sample.id],  # Sample position
                    y1=test_positions[test.id],  # Test position
                    line=dict(color=color_map['test'], width=width_map['test'], dash='dot')
                )
    
    # Analysis creation vertical lines - connect to their test
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                if analysis.id in analysis_positions and test.id in test_positions:
                    analysis_created = analysis.created_at.date().isoformat() if analysis.created_at else '2025-01-01'
                    fig.add_shape(
                        type='line',
                        x0=analysis_created,
                        x1=analysis_created,
                        y0=test_positions[test.id],  # Test position
                        y1=analysis_positions[analysis.id],  # Analysis position
                        line=dict(color=color_map['analysis'], width=width_map['analysis'], dash='dot')
                    )
    
    # Task creation vertical lines - connect to individual
    for task in individual.tasks.all():
        if task.id in task_positions:
            task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
            fig.add_shape(
                type='line',
                x0=task_created,
                x1=task_created,
                y0=0,  # Individual timeline
                y1=task_positions[task.id],  # Task position
                line=dict(color=color_map['task'], width=width_map['task'], dash='dot')
            )
    
    # Note creation vertical lines - connect to individual
    for note in individual.notes.all():
        if note.id in note_positions:
            note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
            fig.add_shape(
                type='line',
                x0=note_created,
                x1=note_created,
                y0=0,  # Individual timeline
                y1=note_positions[note.id],  # Note position
                line=dict(color=color_map['note'], width=width_map['note'], dash='dot')
            )
    
    # Sample task creation vertical lines - connect to sample
    for sample in individual.samples.all():
        for task in sample.tasks.all():
            if task.id in task_positions and sample.id in sample_positions:
                task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
                fig.add_shape(
                    type='line',
                    x0=task_created,
                    x1=task_created,
                    y0=sample_positions[sample.id],  # Sample position
                    y1=task_positions[task.id],  # Task position
                    line=dict(color=color_map['task'], width=width_map['task'], dash='dot')
                )
    
    # Sample note creation vertical lines - connect to sample
    for sample in individual.samples.all():
        for note in sample.notes.all():
            if note.id in note_positions and sample.id in sample_positions:
                note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
                fig.add_shape(
                    type='line',
                    x0=note_created,
                    x1=note_created,
                    y0=sample_positions[sample.id],  # Sample position
                    y1=note_positions[note.id],  # Note position
                    line=dict(color=color_map['note'], width=width_map['note'], dash='dot')
                )
    
    # Test task creation vertical lines - connect to test
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for task in test.tasks.all():
                if task.id in task_positions and test.id in test_positions:
                    task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
                    fig.add_shape(
                        type='line',
                        x0=task_created,
                        x1=task_created,
                        y0=test_positions[test.id],  # Test position
                        y1=task_positions[task.id],  # Task position
                        line=dict(color=color_map['task'], width=width_map['task'], dash='dot')
                    )
    
    # Test note creation vertical lines - connect to test
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for note in test.notes.all():
                if note.id in note_positions and test.id in test_positions:
                    note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
                    fig.add_shape(
                        type='line',
                        x0=note_created,
                        x1=note_created,
                        y0=test_positions[test.id],  # Test position
                        y1=note_positions[note.id],  # Note position
                        line=dict(color=color_map['note'], width=width_map['note'], dash='dot')
                    )
    
    # Analysis task creation vertical lines - connect to analysis
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                for task in analysis.tasks.all():
                    if task.id in task_positions and analysis.id in analysis_positions:
                        task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
                        fig.add_shape(
                            type='line',
                            x0=task_created,
                            x1=task_created,
                            y0=analysis_positions[analysis.id],  # Analysis position
                            y1=task_positions[task.id],  # Task position
                            line=dict(color=color_map['task'], width=width_map['task'], dash='dot')
                        )
    
    # Analysis note creation vertical lines - connect to analysis
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                for note in analysis.notes.all():
                    if note.id in note_positions and analysis.id in analysis_positions:
                        note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
                        fig.add_shape(
                            type='line',
                            x0=note_created,
                            x1=note_created,
                            y0=analysis_positions[analysis.id],  # Analysis position
                            y1=note_positions[note.id],  # Note position
                            line=dict(color=color_map['note'], width=width_map['note'], dash='dot')
                        )
    

    
    # Update layout
    fig.update_layout(
        title=f'Timeline for Individual {individual.individual_id}',
        xaxis_title='Date',
        yaxis_title='',
        showlegend=False,
        height=600,
        yaxis=dict(
            showticklabels=False,
            range=[min_y - 0.5, max_y + 0.5]
        ),
        xaxis=dict(
            tickangle=20,
            tickformat='%d %b %Y',
            type='date',
        ),
        # Add text angle for better readability
        annotations=[
            dict(
                x=date,
                y=y_pos + 0.1,  # Position just above each event's line
                text='',
                showarrow=False,
                textangle=0,
                font=dict(size=10),
                xanchor='left',
                yanchor='bottom'
            ) for date, desc, y_pos in zip(dates, descriptions, y_positions)
        ],
        hovermode='closest'
    )
    
    plot_json = json.dumps(fig.to_dict())
    
    context = {
        'individual': individual,
        'plot_json': plot_json,
        'timeline_events': timeline_events,
        'event_count': len(timeline_events)
    }
    
    if request.htmx:
        return render(request, 'lab/individual.html#timeline', context)
    else:
        return render(request, 'lab/individual.html', context)
