from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lab", "0005_profile_signer_block_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="testtype",
            name="negative_report_template",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="testtype",
            name="negative_result_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="testtype",
            name="positive_comment_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="testtype",
            name="positive_report_template",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="testtype",
            name="default_method_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="testtype",
            name="default_total_reads_text",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="testtype",
            name="default_coverage_20x_text",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="testtype",
            name="default_mean_depth_text",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="testtype",
            name="default_filtering_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="testtype",
            name="default_limitations_text",
            field=models.TextField(blank=True, default=""),
        ),
    ]
