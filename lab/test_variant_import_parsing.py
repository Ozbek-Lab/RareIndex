from django.test import SimpleTestCase

from lab.management.commands.import_all import _extract_variant_records


class VariantImportParsingTests(SimpleTestCase):
    def test_parses_snv_variant_list_format(self):
        records = _extract_variant_records("chr10-77984023 A>G")

        self.assertEqual(
            records,
            [
                {
                    "chromosome": "chr10",
                    "start": 77984023,
                    "reference": "A",
                    "alternate": "G",
                    "kind": "snv",
                    "end": 77984023,
                    "source_text": "chr10-77984023 A>G",
                }
            ],
        )

    def test_parses_copy_number_range_as_cnv(self):
        records = _extract_variant_records("7:100318423-100321323:1/DUP")

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["kind"], "cnv")
        self.assertEqual(record["chromosome"], "chr7")
        self.assertEqual(record["start"], 100318423)
        self.assertEqual(record["end"], 100321323)
        self.assertEqual(record["cnv_type"], "gain")
        self.assertEqual(record["copy_number"], None)

    def test_parses_cytoband_copy_number_as_cnv(self):
        records = _extract_variant_records(
            "LAMA2 seq[GRCh38] 6q22.33(129,047,209_129,083,546)x4 Duplikasyon"
        )

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["kind"], "cnv")
        self.assertEqual(record["chromosome"], "chr6")
        self.assertEqual(record["start"], 129047209)
        self.assertEqual(record["end"], 129083546)
        self.assertEqual(record["cnv_type"], "gain")
        self.assertEqual(record["copy_number"], 4)

    def test_parses_deletion_range_as_sv(self):
        records = _extract_variant_records("chr5:100000-120000 deletion")

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["kind"], "sv")
        self.assertEqual(record["chromosome"], "chr5")
        self.assertEqual(record["start"], 100000)
        self.assertEqual(record["end"], 120000)
        self.assertEqual(record["sv_type"], "deletion")

    def test_parses_inversion_range_as_sv(self):
        records = _extract_variant_records("chr2:200000-250000 inversion")

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["kind"], "sv")
        self.assertEqual(record["chromosome"], "chr2")
        self.assertEqual(record["start"], 200000)
        self.assertEqual(record["end"], 250000)
        self.assertEqual(record["sv_type"], "inversion")
