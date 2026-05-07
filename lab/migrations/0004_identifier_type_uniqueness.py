import taggit.managers
from django.db import migrations, models
from django.db.models import Count, Q
from django.db.models.functions import Lower


def merge_duplicate_identifier_types(apps, schema_editor):
    IdentifierType = apps.get_model("lab", "IdentifierType")
    CrossIdentifier = apps.get_model("lab", "CrossIdentifier")
    db_alias = schema_editor.connection.alias

    duplicate_names = (
        IdentifierType.objects.using(db_alias)
        .annotate(normalized_name=Lower("name"))
        .values("normalized_name")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .order_by("normalized_name")
    )

    for row in duplicate_names:
        records = list(
            IdentifierType.objects.using(db_alias)
            .annotate(normalized_name=Lower("name"))
            .filter(normalized_name=row["normalized_name"])
            .order_by("id")
        )
        if len(records) < 2:
            continue

        canonical = records[0]
        for extra in records[1:]:
            if not canonical.description and extra.description:
                canonical.description = extra.description
            if not canonical.use_priority and extra.use_priority:
                canonical.use_priority = extra.use_priority
            if not canonical.is_shown_in_table and extra.is_shown_in_table:
                canonical.is_shown_in_table = True
        canonical.save(using=db_alias)

        canonical_individual_ids = set(
            CrossIdentifier.objects.using(db_alias)
            .filter(id_type=canonical)
            .values_list("individual_id", flat=True)
        )

        for extra in records[1:]:
            for xid in CrossIdentifier.objects.using(db_alias).filter(id_type=extra).order_by("id"):
                if xid.individual_id in canonical_individual_ids:
                    xid.delete()
                    continue

                xid.id_type = canonical
                xid.save(using=db_alias)
                canonical_individual_ids.add(xid.individual_id)

            extra.delete()


def populate_identifier_type_examples(apps, schema_editor):
    IdentifierType = apps.get_model("lab", "IdentifierType")
    db_alias = schema_editor.connection.alias

    examples = {
        "RareBoost": "RB_2025_01.1",
        "Biobank": "RD3.F12.1",
    }

    for name, example in examples.items():
        IdentifierType.objects.using(db_alias).filter(name__iexact=name, example="").update(example=example)


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("lab", "0003_plottemplate_default_col_span"),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_identifier_types, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="identifiertype",
            constraint=models.UniqueConstraint(
                Lower("name"),
                name="unique_identifiertype_name_ci",
            ),
        ),
        migrations.AddConstraint(
            model_name="identifiertype",
            constraint=models.UniqueConstraint(
                fields=["use_priority"],
                condition=Q(use_priority__gt=0),
                name="unique_identifiertype_use_priority_nonzero",
            ),
        ),
        migrations.AddField(
            model_name="identifiertype",
            name="example",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Example of a valid identifier value for this type.",
                max_length=255,
            ),
        ),
        migrations.RunPython(populate_identifier_type_examples, migrations.RunPython.noop),
        migrations.AddField(
            model_name="historicalidentifiertype",
            name="example",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Example of a valid identifier value for this type.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="analysisreport",
            name="statuses",
            field=taggit.managers.TaggableManager(
                blank=True,
                help_text="A comma-separated list of tags.",
                through="lab.TaggedStatus",
                to="lab.Status",
                verbose_name="Statuses",
            ),
        ),
        migrations.AddField(
            model_name="status",
            name="connected_classes",
            field=models.ManyToManyField(
                blank=True,
                help_text="Connected object types whose statuses should also be surfaced on the individual row.",
                related_name="connected_statuses",
                to="contenttypes.contenttype",
            ),
        ),
        migrations.AlterField(
            model_name="historicalplottemplate",
            name="show_download_menu",
            field=models.BooleanField(
                default=True,
                help_text="Show Marimo's notebook actions/download menu on notebook pages.",
            ),
        ),
    ]
