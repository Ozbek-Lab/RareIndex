# Generated manually to store imported GeneBe evidence and manual overrides.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("variant", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ACMGEvidenceOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("gene_symbol", models.CharField(blank=True, db_index=True, max_length=100)),
                ("transcript", models.CharField(blank=True, max_length=100)),
                ("criterion", models.CharField(db_index=True, max_length=20)),
                (
                    "source",
                    models.CharField(
                        choices=[("genebe", "GeneBe Import"), ("manual", "Manual Override")],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("included", models.BooleanField(default=True)),
                ("strength", models.CharField(blank=True, default="", max_length=20)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "variant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="acmg_evidence_overrides",
                        to="variant.variant",
                    ),
                ),
            ],
            options={
                "ordering": ["gene_symbol", "transcript", "criterion", "source"],
                "unique_together": {("variant", "gene_symbol", "transcript", "criterion", "source")},
            },
        ),
    ]
