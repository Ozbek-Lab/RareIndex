from django.shortcuts import get_object_or_404

from .models import Family, Individual, Project


def user_has_project_scope_bypass(user):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and (getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))
    )


def accessible_projects(user, queryset=None):
    qs = queryset if queryset is not None else Project.objects.all()
    if user_has_project_scope_bypass(user):
        return qs
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    return qs.filter(memberships__user=user).distinct()


def accessible_individuals(user, queryset=None):
    qs = queryset if queryset is not None else Individual.objects.all()
    if user_has_project_scope_bypass(user):
        return qs
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    return qs.filter(projects__memberships__user=user).distinct()


def accessible_families(user, queryset=None):
    qs = queryset if queryset is not None else Family.objects.all()
    if user_has_project_scope_bypass(user):
        return qs
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    return qs.filter(individuals__projects__memberships__user=user).distinct()


def accessible_variants(user, queryset):
    if user_has_project_scope_bypass(user):
        return queryset
    if not user or not getattr(user, "is_authenticated", False):
        return queryset.none()
    return queryset.filter(individual__projects__memberships__user=user).distinct()


def get_accessible_project_or_404(user, queryset=None, **kwargs):
    return get_object_or_404(accessible_projects(user, queryset), **kwargs)


def get_accessible_individual_or_404(user, queryset=None, **kwargs):
    return get_object_or_404(accessible_individuals(user, queryset), **kwargs)


def get_accessible_family_or_404(user, queryset=None, **kwargs):
    return get_object_or_404(accessible_families(user, queryset), **kwargs)


def user_can_access_project(user, project):
    if user_has_project_scope_bypass(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return project.memberships.filter(user=user).exists()


def user_can_access_individual(user, individual):
    if user_has_project_scope_bypass(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return individual.projects.filter(memberships__user=user).exists()


def owning_individual(obj):
    if isinstance(obj, Individual):
        return obj

    for path in (
        ("individual",),
        ("sample", "individual"),
        ("test", "sample", "individual"),
        ("pipeline", "test", "sample", "individual"),
        ("analysis", "pipeline", "test", "sample", "individual"),
    ):
        current = obj
        for attr in path:
            current = getattr(current, attr, None)
            if current is None:
                break
        if isinstance(current, Individual):
            return current

    content_object = getattr(obj, "content_object", None)
    if content_object is not None and content_object is not obj:
        return owning_individual(content_object)

    return None


def user_can_access_object(user, obj):
    if user_has_project_scope_bypass(user):
        return True
    if isinstance(obj, Project):
        return user_can_access_project(user, obj)
    if isinstance(obj, Family):
        return accessible_families(user, Family.objects.filter(pk=obj.pk)).exists()
    project = getattr(obj, "project", None)
    if isinstance(project, Project):
        return user_can_access_project(user, project)
    content_object = getattr(obj, "content_object", None)
    if content_object is not None and content_object is not obj:
        return user_can_access_object(user, content_object)
    individual = owning_individual(obj)
    if individual is not None:
        return user_can_access_individual(user, individual)
    return True
