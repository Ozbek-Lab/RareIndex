from django.db import migrations, models


CHOICES = [
    ("false", "Non-Consanguineous"),
    (None, "Unknown"),
    ("true", "Consanguineous"),
    ("same_village", "Same Village"),
    ("nearby_villages", "Nearby Villages"),
]


def copy_boolean_values(apps, schema_editor):
    for name in ("Family", "HistoricalFamily"):
        rows = apps.get_model("lab", name).objects.using(schema_editor.connection.alias)
        rows.filter(is_consanguineous=True).update(consanguinity_choice="true")
        rows.filter(is_consanguineous=False).update(consanguinity_choice="false")
        rows.filter(is_consanguineous__isnull=True).update(consanguinity_choice=None)


def restore_boolean_values(apps, schema_editor):
    # Village choices have no boolean equivalent; preserve them as Unknown
    # when rolling back to the old schema.
    for name in ("Family", "HistoricalFamily"):
        rows = apps.get_model("lab", name).objects.using(schema_editor.connection.alias)
        rows.update(is_consanguineous=None)
        rows.filter(consanguinity_choice="true").update(is_consanguineous=True)
        rows.filter(consanguinity_choice="false").update(is_consanguineous=False)


class Migration(migrations.Migration):
    dependencies = [("lab", "0003_historicalprojectmembership_projectmembership")]

    operations = [
        migrations.AddField(
            model_name=name,
            name="consanguinity_choice",
            field=models.CharField(
                max_length=20, choices=CHOICES, blank=True, null=True,
                default=None, verbose_name="Consanguinity",
            ),
        )
        for name in ("family", "historicalfamily")
    ] + [
        migrations.RunPython(copy_boolean_values, restore_boolean_values),
        migrations.RemoveField(model_name="family", name="is_consanguineous"),
        migrations.RemoveField(model_name="historicalfamily", name="is_consanguineous"),
        migrations.RenameField(model_name="family", old_name="consanguinity_choice", new_name="is_consanguineous"),
        migrations.RenameField(model_name="historicalfamily", old_name="consanguinity_choice", new_name="is_consanguineous"),
    ]
