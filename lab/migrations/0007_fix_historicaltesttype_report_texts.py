from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lab", "0006_testtype_report_texts"),
    ]

    operations = [
        # Ensure simple_history's HistoricalTestType table matches the TestType model
        # fields added in 0006_testtype_report_texts.py.
        migrations.AddField(
            model_name="historicaltesttype",
            name="positive_comment_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="historicaltesttype",
            name="positive_report_template",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="historicaltesttype",
            name="negative_result_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="historicaltesttype",
            name="negative_report_template",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="historicaltesttype",
            name="default_method_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="historicaltesttype",
            name="default_total_reads_text",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="historicaltesttype",
            name="default_coverage_20x_text",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="historicaltesttype",
            name="default_mean_depth_text",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="historicaltesttype",
            name="default_filtering_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="historicaltesttype",
            name="default_limitations_text",
            field=models.TextField(blank=True, default=""),
        ),
    ]
