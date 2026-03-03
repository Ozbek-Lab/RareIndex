from django.db import migrations


def uppercase_snv_alleles(apps, schema_editor):
    """
    Ensure all existing SNV reference/alternate alleles are stored in uppercase.

    This mirrors the manual shell operation:

        for var in SNV.objects.all():
            var.alternate = var.alternate.upper()
            var.reference = var.reference.upper()
            var.save()
    """
    SNV = apps.get_model("variant", "SNV")
    HistoricalSNV = apps.get_model("variant", "HistoricalSNV")

    for snv in SNV.objects.all().only("pk", "reference", "alternate"):
        ref = (snv.reference or "").upper()
        alt = (snv.alternate or "").upper()
        if ref != snv.reference or alt != snv.alternate:
            SNV.objects.filter(pk=snv.pk).update(reference=ref, alternate=alt)

    for h in HistoricalSNV.objects.all().only("pk", "reference", "alternate"):
        ref = (h.reference or "").upper()
        alt = (h.alternate or "").upper()
        if ref != h.reference or alt != h.alternate:
            HistoricalSNV.objects.filter(pk=h.pk).update(reference=ref, alternate=alt)


def noop_reverse(apps, schema_editor):
    # No reliable way to restore original casing; keep as a no-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("variant", "0003_remove_historicalcnv_analysis_and_more"),
    ]

    operations = [
        migrations.RunPython(uppercase_snv_alleles, noop_reverse),
    ]

