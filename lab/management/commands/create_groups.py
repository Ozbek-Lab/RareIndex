from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


ADD_CHANGE_VIEW = ("add", "change", "view")
CRUD = ("add", "change", "delete", "view")
VIEW = ("view",)


ACCOUNT_MODELS = ("emailaddress", "emailconfirmation")

CONFIG_MODELS = (
    "sampletype",
    "testtype",
    "pipelinetype",
    "analysistype",
    "identifiertype",
    "statusgroup",
    "status",
    "institution",
    "contact",
)

WORKFLOW_MODELS = (
    "individual",
    "family",
    "crossidentifier",
    "sample",
    "test",
    "pipeline",
    "analysis",
    "analysisreport",
    "analysisrequestform",
    "note",
    "task",
    "project",
)

VARIANT_MODELS = (
    "variant",
    "snv",
    "cnv",
    "sv",
    "repeat",
    "delins",
    "classification",
    "annotation",
    "acmgevidenceoverride",
    "gene",
)

ONTOLOGY_MODELS = (
    "ontology",
    "term",
    "synonym",
    "crossreference",
    "relationshiptype",
    "relationship",
)

HISTORY_MODELS = (
    "historicalanalysis",
    "historicalanalysisreport",
    "historicalanalysisrequestform",
    "historicalanalysistype",
    "historicalcontact",
    "historicalcrossidentifier",
    "historicaldashboardwidget",
    "historicalfamily",
    "historicalidentifiertype",
    "historicalindividual",
    "historicalinstitution",
    "historicalnote",
    "historicalpipeline",
    "historicalpipelinetype",
    "historicalplottemplate",
    "historicalproject",
    "historicalsample",
    "historicalsampletype",
    "historicalstatus",
    "historicalstatusgroup",
    "historicaltask",
    "historicaltest",
    "historicaltesttype",
    "historicalannotation",
    "historicalclassification",
    "historicalcnv",
    "historicaldelins",
    "historicalrepeat",
    "historicalsnv",
    "historicalsv",
    "historicalvariant",
)


def model_permissions(app_label, model_names, actions):
    codenames = [
        f"{action}_{model_name}"
        for model_name in model_names
        for action in actions
    ]
    return Permission.objects.filter(
        content_type__app_label=app_label,
        content_type__model__in=model_names,
        codename__in=codenames,
    )


def codename_permissions(app_label, codenames):
    return Permission.objects.filter(
        content_type__app_label=app_label,
        codename__in=codenames,
    )


def combine_permissions(*querysets):
    permission_ids = set()
    for queryset in querysets:
        permission_ids.update(queryset.values_list("pk", flat=True))
    return Permission.objects.filter(pk__in=permission_ids)


def build_groups_perms():
    account_basic = model_permissions("account", ACCOUNT_MODELS, ("add", "change", "view"))
    config_view = model_permissions("lab", CONFIG_MODELS, VIEW)
    config_manage = model_permissions("lab", CONFIG_MODELS, CRUD)
    workflow_view = model_permissions("lab", WORKFLOW_MODELS, VIEW)
    workflow_edit = model_permissions("lab", WORKFLOW_MODELS, ADD_CHANGE_VIEW)
    workflow_delete = model_permissions(
        "lab",
        ("sample", "test", "pipeline", "analysis", "analysisreport"),
        ("delete",),
    )
    variants_view = model_permissions("variant", VARIANT_MODELS, VIEW)
    variants_edit = model_permissions("variant", VARIANT_MODELS, ADD_CHANGE_VIEW)
    variants_delete = model_permissions("variant", ("variant",), ("delete",))
    ontologies_view = model_permissions("ontologies", ONTOLOGY_MODELS, VIEW)
    history_view = combine_permissions(
        model_permissions("lab", HISTORY_MODELS, VIEW),
        model_permissions("variant", HISTORY_MODELS, VIEW),
    )
    sensitive_view = codename_permissions("lab", ("view_sensitive_data",))

    return {
        "Admin": Permission.objects.all(),
        "Basic User": combine_permissions(
            account_basic,
            config_view,
            ontologies_view,
            history_view,
        ),
        "Sensitive Data Viewer": sensitive_view,
        "Type Manager": config_manage,
        "Collaborator": combine_permissions(
            workflow_view,
            config_view,
            variants_view,
            ontologies_view,
        ),
        "Analyst": combine_permissions(
            workflow_edit,
            config_view,
            variants_edit,
            ontologies_view,
        ),
        "Group Member": combine_permissions(
            workflow_edit,
            workflow_delete,
            config_view,
            variants_edit,
            variants_delete,
            ontologies_view,
        ),
    }


def expected_permission_codenames():
    checks = {
        "lab": (
            (CONFIG_MODELS, VIEW),
            (CONFIG_MODELS, CRUD),
            (WORKFLOW_MODELS, ADD_CHANGE_VIEW),
            (("sample", "test", "pipeline", "analysis", "analysisreport"), ("delete",)),
            (("individual",), ("view_sensitive_data",)),
        ),
        "variant": (
            (VARIANT_MODELS, ADD_CHANGE_VIEW),
            (("variant",), ("delete",)),
        ),
        "ontologies": ((ONTOLOGY_MODELS, VIEW),),
    }

    expected = {}
    for app_label, entries in checks.items():
        expected[app_label] = set()
        for model_names, actions in entries:
            for action in actions:
                if action == "view_sensitive_data":
                    expected[app_label].add(action)
                    continue
                for model_name in model_names:
                    expected[app_label].add(f"{action}_{model_name}")
    return expected


class Command(BaseCommand):
    help = "Create or update application groups and their permissions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the permissions that would be set without changing groups.",
        )

    def handle(self, *args, **options):
        groups_perms = build_groups_perms()

        missing = []
        for app_label, codenames in expected_permission_codenames().items():
            existing = set(
                Permission.objects.filter(
                    content_type__app_label=app_label,
                    codename__in=codenames,
                ).values_list("codename", flat=True)
            )
            missing.extend(
                f"{app_label}.{codename}"
                for codename in sorted(codenames - existing)
            )

        if missing:
            self.stdout.write(
                self.style.WARNING(
                    "Missing expected permissions: " + ", ".join(missing)
                )
            )

        for group_name, permissions in groups_perms.items():
            permission_list = list(
                permissions.select_related("content_type").order_by(
                    "content_type__app_label",
                    "content_type__model",
                    "codename",
                )
            )

            if options["dry_run"]:
                self.stdout.write(
                    self.style.NOTICE(
                        f"{group_name}: {len(permission_list)} permissions"
                    )
                )
                for permission in permission_list:
                    self.stdout.write(
                        f"  {permission.content_type.app_label}.{permission.codename}"
                    )
                continue

            group, created = Group.objects.get_or_create(name=group_name)
            group.permissions.set(permission_list)
            action = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{action} group {group_name}: {len(permission_list)} permissions"
                )
            )
