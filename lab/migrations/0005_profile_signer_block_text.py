from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lab", "0004_historicalplottemplate_plottemplate_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="signer_block_text",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Multiline signer block inserted into generated reports.",
            ),
        ),
    ]
