from django.shortcuts import render
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth, ExtractYear
from .models import Individual, Sample, Test, Institution

def dashboard(request):
    # Get sample counts by type
    sample_type_counts = Sample.objects.values('sample_type__name').annotate(
        count=Count('id')
    ).order_by('-count')

    # Get test counts by status
    test_status_counts = Test.objects.values('status').annotate(
        count=Count('id')
    ).order_by('-count')

    # Get sample counts by institution
    institution_counts = Sample.objects.values(
        'individual__referring_institution__name'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:5]  # Top 5 institutions

    # Get samples over time (last 12 months)
    samples_over_time = Sample.objects.annotate(
        month=TruncMonth('received_date')
    ).values('month').annotate(
        count=Count('id')
    ).order_by('-month')[:12]

    # Recent activity
    recent_samples = Sample.objects.select_related(
        'individual', 'sample_type'
    ).order_by('-received_date')[:5]

    recent_tests = Test.objects.select_related(
        'sample', 'sample__individual'
    ).order_by('-test_date')[:5]

    # Quick stats
    total_individuals = Individual.objects.count()
    total_samples = Sample.objects.count()
    total_tests = Test.objects.count()
    pending_tests = Test.objects.filter(status='pending').count()
    completed_tests = Test.objects.filter(status='completed').count()

    context = {
        'sample_type_counts': list(sample_type_counts),
        'test_status_counts': list(test_status_counts),
        'institution_counts': list(institution_counts),
        'samples_over_time': list(reversed(list(samples_over_time))),
        'recent_samples': recent_samples,
        'recent_tests': recent_tests,
        'stats': {
            'total_individuals': total_individuals,
            'total_samples': total_samples,
            'total_tests': total_tests,
            'pending_tests': pending_tests,
            'completed_tests': completed_tests,
        }
    }
    
    return render(request, 'core/dashboard.html', context)
