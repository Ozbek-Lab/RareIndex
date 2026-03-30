from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("lab", "0007_fix_historicaltesttype_report_texts"),
    ]

    operations = [
        migrations.RenameField(
            model_name="testtype",
            old_name="positive_comment_text",
            new_name="default_positive_comment_text",
        ),
        migrations.RenameField(
            model_name="testtype",
            old_name="negative_result_text",
            new_name="default_negative_result_text",
        ),
        migrations.RenameField(
            model_name="historicaltesttype",
            old_name="positive_comment_text",
            new_name="default_positive_comment_text",
        ),
        migrations.RenameField(
            model_name="historicaltesttype",
            old_name="negative_result_text",
            new_name="default_negative_result_text",
        ),
    ]
