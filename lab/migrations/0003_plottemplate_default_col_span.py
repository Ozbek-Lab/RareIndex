# Generated manually to add dashboard width/download defaults for plot templates.

from django.db import migrations, models


def forwards(apps, schema_editor):
    PlotTemplate = apps.get_model("lab", "PlotTemplate")

    PlotTemplate.objects.filter(slug="sample-distribution-sunburst").update(
        default_col_span=1,
        show_download_menu=False,
    )
    PlotTemplate.objects.filter(slug="analysis-status-bar").update(
        default_col_span=1,
        show_download_menu=False,
    )
    PlotTemplate.objects.filter(slug="hpo-term-network").update(
        default_col_span=2,
        show_download_menu=True,
    )


def backwards(apps, schema_editor):
    PlotTemplate = apps.get_model("lab", "PlotTemplate")
    PlotTemplate.objects.update(default_col_span=1, show_download_menu=True)


class Migration(migrations.Migration):

    dependencies = [
        ("lab", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="plottemplate",
            name="default_col_span",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="plottemplate",
            name="show_download_menu",
            field=models.BooleanField(
                default=True,
                help_text="Show Marimo's notebook actions/download menu on notebook pages.",
            ),
        ),
        migrations.AddField(
            model_name="historicalplottemplate",
            name="default_col_span",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="historicalplottemplate",
            name="show_download_menu",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(forwards, backwards),
    ]
