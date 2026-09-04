from django.shortcuts import get_object_or_404

from .models import Family, Individual, Project, ProjectMembership


PROJECT_ROLE_RANKS = {
    ProjectMembership.Role.VIEWER: 1,
    ProjectMembership.Role.EDITOR: 2,
    ProjectMembership.Role.MANAGER: 3,
}


def project_roles_at_least(min_role):
    min_rank = PROJECT_ROLE_RANKS[min_role]
    return [
        role
        for role, rank in PROJECT_ROLE_RANKS.items()
        if rank >= min_rank
    ]


def strongest_project_role(roles):
    strongest = None
    strongest_rank = 0
    for role in roles:
        rank = PROJECT_ROLE_RANKS.get(role, 0)
        if rank > strongest_rank:
            strongest = role
            strongest_rank = rank
    return strongest


def role_allows(role, min_role):
    return PROJECT_ROLE_RANKS.get(role, 0) >= PROJECT_ROLE_RANKS[min_role]


def user_has_project_scope_bypass(user):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and (getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))
    )


def accessible_projects(user, queryset=None, min_role=ProjectMembership.Role.VIEWER):
    qs = queryset if queryset is not None else Project.objects.all()
    if user_has_project_scope_bypass(user):
        return qs
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    return qs.filter(
        memberships__user=user,
        memberships__role__in=project_roles_at_least(min_role),
    ).distinct()


def accessible_individuals(user, queryset=None, min_role=ProjectMembership.Role.VIEWER):
    qs = queryset if queryset is not None else Individual.objects.all()
    if user_has_project_scope_bypass(user):
        return qs
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    return qs.filter(
        projects__memberships__user=user,
        projects__memberships__role__in=project_roles_at_least(min_role),
    ).distinct()


def accessible_families(user, queryset=None, min_role=ProjectMembership.Role.VIEWER):
    qs = queryset if queryset is not None else Family.objects.all()
    if user_has_project_scope_bypass(user):
        return qs
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    return qs.filter(
        individuals__projects__memberships__user=user,
        individuals__projects__memberships__role__in=project_roles_at_least(min_role),
    ).distinct()


def accessible_variants(user, queryset, min_role=ProjectMembership.Role.VIEWER):
    if user_has_project_scope_bypass(user):
        return queryset
    if not user or not getattr(user, "is_authenticated", False):
        return queryset.none()
    return queryset.filter(
        individual__projects__memberships__user=user,
        individual__projects__memberships__role__in=project_roles_at_least(min_role),
    ).distinct()


def get_accessible_project_or_404(user, queryset=None, **kwargs):
    return get_object_or_404(accessible_projects(user, queryset), **kwargs)


def get_accessible_individual_or_404(user, queryset=None, **kwargs):
    return get_object_or_404(accessible_individuals(user, queryset), **kwargs)


def get_accessible_family_or_404(user, queryset=None, **kwargs):
    return get_object_or_404(accessible_families(user, queryset), **kwargs)


def project_role_for_user(user, project):
    if user_has_project_scope_bypass(user):
        return ProjectMembership.Role.MANAGER
    if not user or not getattr(user, "is_authenticated", False) or not project:
        return None
    return strongest_project_role(
        project.memberships.filter(user=user).values_list("role", flat=True)
    )


def individual_role_for_user(user, individual):
    if user_has_project_scope_bypass(user):
        return ProjectMembership.Role.MANAGER
    if not user or not getattr(user, "is_authenticated", False) or not individual:
        return None
    return strongest_project_role(
        ProjectMembership.objects.filter(
            user=user,
            project__individuals=individual,
        ).values_list("role", flat=True)
    )


def family_role_for_user(user, family):
    if user_has_project_scope_bypass(user):
        return ProjectMembership.Role.MANAGER
    if not user or not getattr(user, "is_authenticated", False) or not family:
        return None
    return strongest_project_role(
        ProjectMembership.objects.filter(
            user=user,
            project__individuals__family=family,
        ).values_list("role", flat=True)
    )


def user_has_project_role(user, project, min_role=ProjectMembership.Role.VIEWER):
    return role_allows(project_role_for_user(user, project), min_role)


def user_has_individual_role(user, individual, min_role=ProjectMembership.Role.VIEWER):
    return role_allows(individual_role_for_user(user, individual), min_role)


def user_has_family_role(user, family, min_role=ProjectMembership.Role.VIEWER):
    return role_allows(family_role_for_user(user, family), min_role)


def user_can_access_project(user, project):
    if user_has_project_scope_bypass(user):
        return True
    return user_has_project_role(user, project, ProjectMembership.Role.VIEWER)


def user_can_access_individual(user, individual):
    if user_has_project_scope_bypass(user):
        return True
    return user_has_individual_role(user, individual, ProjectMembership.Role.VIEWER)


def owning_individual(obj):
    if isinstance(obj, Individual):
        return obj

    for path in (
        ("individual",),
        ("variant", "individual"),
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


def project_role_for_object(user, obj):
    if user_has_project_scope_bypass(user):
        return ProjectMembership.Role.MANAGER
    if isinstance(obj, Project):
        return project_role_for_user(user, obj)
    if isinstance(obj, Family):
        return family_role_for_user(user, obj)
    project = getattr(obj, "project", None)
    if isinstance(project, Project):
        return project_role_for_user(user, project)
    content_object = getattr(obj, "content_object", None)
    if content_object is not None and content_object is not obj:
        return project_role_for_object(user, content_object)
    individual = owning_individual(obj)
    if individual is not None:
        return individual_role_for_user(user, individual)
    return ProjectMembership.Role.MANAGER


def user_has_object_role(user, obj, min_role=ProjectMembership.Role.VIEWER):
    return role_allows(project_role_for_object(user, obj), min_role)


def user_has_permission(user, permission):
    if not permission:
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user_has_project_scope_bypass(user):
        return True
    if isinstance(permission, (list, tuple, set)):
        return any(user.has_perm(perm) for perm in permission)
    return user.has_perm(permission)


def user_can_access_object(user, obj):
    if user_has_project_scope_bypass(user):
        return True
    if isinstance(obj, Project):
        return user_has_project_role(user, obj, ProjectMembership.Role.VIEWER)
    if isinstance(obj, Family):
        return user_has_family_role(user, obj, ProjectMembership.Role.VIEWER)
    project = getattr(obj, "project", None)
    if isinstance(project, Project):
        return user_has_project_role(user, project, ProjectMembership.Role.VIEWER)
    content_object = getattr(obj, "content_object", None)
    if content_object is not None and content_object is not obj:
        return user_can_access_object(user, content_object)
    individual = owning_individual(obj)
    if individual is not None:
        return user_has_individual_role(user, individual, ProjectMembership.Role.VIEWER)
    return True


def user_can_change_object(user, obj, permission=None):
    if not user_has_permission(user, permission):
        return False
    min_role = (
        ProjectMembership.Role.MANAGER
        if isinstance(obj, Project)
        else ProjectMembership.Role.EDITOR
    )
    return user_has_object_role(user, obj, min_role)


def user_can_delete_object(user, obj, permission=None):
    return user_can_change_object(user, obj, permission)


def user_can_create_related_object(user, parent_obj, permission=None):
    if not user_has_permission(user, permission):
        return False
    return user_has_object_role(user, parent_obj, ProjectMembership.Role.EDITOR)


def user_can_manage_project(user, project, permission=None):
    return user_has_permission(user, permission) and user_has_project_role(
        user,
        project,
        ProjectMembership.Role.MANAGER,
    )
