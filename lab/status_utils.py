"""Shared status helpers used by views, tables, and HTMX updates."""

from django.contrib.contenttypes.models import ContentType


def build_status_metadata_by_model():
    """Return status metadata keyed by content type model name."""
    from .models import Status

    metadata = {
        "global": {},
        "individual": {},
        "sample": {},
        "test": {},
        "pipeline": {},
        "analysis": {},
        "analysisreport": {},
        "project": {},
        "task": {},
        "variant": {},
    }
    for status in Status.objects.select_related("content_type"):
        model_key = status.content_type.model if status.content_type else "global"
        metadata.setdefault(model_key, {})[status.name] = {
            "color": status.color,
            "icon": status.icon,
            "short_name": status.short_name,
        }
    return metadata


def collect_individual_row_statuses(individual):
    """Return direct and connected statuses that should appear on an individual row."""
    from .models import Individual

    if not individual or not isinstance(individual, Individual):
        return []

    individual_ct = ContentType.objects.get_for_model(Individual)
    statuses = []
    seen = set()

    def add_statuses(source_statuses):
        for status in source_statuses:
            if status.pk in seen:
                continue
            if not status.connected_classes.filter(pk=individual_ct.pk).exists():
                continue
            statuses.append(status)
            seen.add(status.pk)

    # Direct individual statuses first.
    for status in individual.statuses.all():
        if status.pk in seen:
            continue
        statuses.append(status)
        seen.add(status.pk)

    for project in individual.projects.all():
        add_statuses(project.statuses.all())
        for task in project.tasks.all():
            add_statuses(task.statuses.all())

    for task in individual.tasks.all():
        add_statuses(task.statuses.all())

    # Connected workflow objects.
    for sample in individual.samples.all():
        add_statuses(sample.tasks.all())
        add_statuses(sample.statuses.all())
        for test in sample.tests.all():
            add_statuses(test.tasks.all())
            add_statuses(test.statuses.all())
            for pipeline in test.pipelines.all():
                add_statuses(pipeline.tasks.all())
                add_statuses(pipeline.statuses.all())
                for analysis in pipeline.analyses.all():
                    add_statuses(analysis.tasks.all())
                    add_statuses(analysis.statuses.all())
                    for report in analysis.reports.all():
                        add_statuses(report.statuses.all())

    for variant in individual.variants.all():
        add_statuses(variant.statuses.all())

    return statuses
