from django.test import SimpleTestCase

from lab.management.commands.import_all import _extract_variant_records, _variant_model_for_kind
from variant.models import Repeat


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

    def test_parses_compact_deletion_range_as_sv(self):
        records = _extract_variant_records("chr20:35679278-35685149del")

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["kind"], "sv")
        self.assertEqual(record["chromosome"], "chr20")
        self.assertEqual(record["start"], 35679278)
        self.assertEqual(record["end"], 35685149)
        self.assertEqual(record["sv_type"], "deletion")

    def test_parses_compact_deletion_range_with_separators(self):
        cases = [
            ("chrM:6,325-13,988 DEL", "chrM", 6325, 13988),
            ("chr12:41.021.576_41.040.185del", "chr12", 41021576, 41040185),
            (r"chr5:126,489,209\_126,759,255del", "chr5", 126489209, 126759255),
        ]

        for value, chrom, start, end in cases:
            with self.subTest(value=value):
                records = _extract_variant_records(value)

                self.assertEqual(len(records), 1)
                record = records[0]
                self.assertEqual(record["kind"], "sv")
                self.assertEqual(record["chromosome"], chrom)
                self.assertEqual(record["start"], start)
                self.assertEqual(record["end"], end)
                self.assertEqual(record["sv_type"], "deletion")

    def test_parses_repeat_range_variants(self):
        cases = [
            ("chr4:3074876-3074936 CAG[20]", "chr4", 3074876, 3074936, "CAG", 20),
            ("chr4:3,074,876_3,074,936 (cag)x42", "chr4", 3074876, 3074936, "CAG", 42),
            ("4:3074876-3074936 repeat CAG x 18", "chr4", 3074876, 3074936, "CAG", 18),
            ("chrX:1000 STR CGG[200]", "chrX", 1000, 1000, "CGG", 200),
        ]

        for value, chrom, start, end, repeat_unit, repeat_count in cases:
            with self.subTest(value=value):
                records = _extract_variant_records(value)

                self.assertEqual(len(records), 1)
                record = records[0]
                self.assertEqual(record["kind"], "repeat")
                self.assertEqual(record["chromosome"], chrom)
                self.assertEqual(record["start"], start)
                self.assertEqual(record["end"], end)
                self.assertEqual(record["repeat_unit"], repeat_unit)
                self.assertEqual(record["repeat_count"], repeat_count)

    def test_repeat_kind_maps_to_repeat_model(self):
        self.assertIs(_variant_model_for_kind("repeat"), Repeat)

    def test_parses_inversion_range_as_sv(self):
        records = _extract_variant_records("chr2:200000-250000 inversion")

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["kind"], "sv")
        self.assertEqual(record["chromosome"], "chr2")
        self.assertEqual(record["start"], 200000)
        self.assertEqual(record["end"], 250000)
        self.assertEqual(record["sv_type"], "inversion")
