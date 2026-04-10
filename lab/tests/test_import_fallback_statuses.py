from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile

import openpyxl
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from lab.management.commands.import_all import Command
from lab.models import (
    AnalysisReport,
    CrossIdentifier,
    Contact,
    Family,
    IdentifierType,
    Individual,
    Pipeline,
    PipelineType,
    Status,
    Sample,
    SampleType,
    Test,
    TestType,
)
from variant.models import SNV

User = get_user_model()


class ImportFallbackStatusTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="testpass")
        self.contact = Contact.objects.create(full_name="tester", user=self.user, created_by=self.user)
        self.family = Family.objects.create(family_id="FAM-1", created_by=self.user)
        self.individual = Individual.objects.create(
            full_name="Person One",
            family=self.family,
            created_by=self.user,
        )
        self.command = Command()
        self.command.admin_user = self.user
        self.command.dry_run = False
        self.command.issue_records = []
        self.command._report_text_reference_cache = None
        self.command.id_types = {"Biobank": None}

        sample_not_available = Status.objects.create(
            name="Not Available",
            description="Placeholder",
            color="gray",
            created_by=self.user,
        )
        sample_unsure_import = Status.objects.create(
            name="Unsure Import",
            description="Import fallback",
            color="orange",
            created_by=self.user,
        )
        test_previous = Status.objects.create(
            name="Previous",
            description="Historical",
            color="orange",
            created_by=self.user,
        )
        test_unsure_import = Status.objects.create(
            name="Unsure Import",
            description="Import fallback",
            color="orange",
            created_by=self.user,
        )
        pipeline_unsure_import = Status.objects.create(
            name="Unsure Import",
            description="Import fallback",
            color="orange",
            created_by=self.user,
        )
        analysis_unsure_import = Status.objects.create(
            name="Unsure Import",
            description="Import fallback",
            color="orange",
            created_by=self.user,
        )

        self.command.statuses = {
            "sample": {
                "not_available": sample_not_available,
                "unsure_import": sample_unsure_import,
            },
            "test": {
                "previous": test_previous,
                "unsure_import": test_unsure_import,
            },
            "pipeline": {
                "unsure_import": pipeline_unsure_import,
            },
            "analysis": {
                "unsure_import": analysis_unsure_import,
            },
        }
        self.sample_type = SampleType.objects.create(name="Blood", created_by=self.user)
        self.wes_type = TestType.objects.create(name="WES", created_by=self.user)
        self.rb_type = IdentifierType.objects.create(
            name="RareBoost",
            description="RareBoost identifier",
            created_by=self.user,
            use_priority=1,
        )

    def test_reanalysis_fallback_test_and_placeholder_sample_are_marked_unsure_import(self):
        self.command._process_rb_reanaliz(self.individual, "WGS reanalysis")

        sample = self.individual.samples.first()
        self.assertIsNotNone(sample)
        self.assertEqual(
            set(sample.statuses.values_list("name", flat=True)),
            {"Not Available", "Unsure Import"},
        )

        test = Test.objects.filter(sample=sample, test_type__name="WES").first()
        self.assertIsNotNone(test)
        self.assertEqual(
            set(test.statuses.values_list("name", flat=True)),
            {"Previous", "Unsure Import"},
        )

    def test_gennext_fallback_creates_wes_test_for_renumbered_id(self):
        renumbered_individual = Individual.objects.create(
            full_name="Renumbered Person",
            family=self.family,
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=renumbered_individual,
            id_type=self.rb_type,
            id_value="RB_2026_9.1.1",
            created_by=self.user,
        )

        self.command.analysis_map = {}
        row = {"Gennext ID": "RB_2026_9.1", "Gennext Date": date(2025, 1, 1)}

        with patch.object(self.command, "_ws_rows", return_value=[row]):
            self.command._step_gennext_analiz(None)

        sample = renumbered_individual.samples.first()
        self.assertIsNotNone(sample)
        self.assertEqual(
            set(sample.statuses.values_list("name", flat=True)),
            {"Not Available", "Unsure Import"},
        )

        test = Test.objects.filter(sample=sample, test_type__name="WES").first()
        self.assertIsNotNone(test)
        self.assertEqual(
            set(test.statuses.values_list("name", flat=True)),
            {"Previous", "Unsure Import"},
        )

        pipeline = Pipeline.objects.filter(test=test, type__name="Gennext").first()
        self.assertIsNotNone(pipeline)

    def test_report_fallback_creates_franklin_pipeline_on_first_test(self):
        report_sample = Sample.objects.create(
            individual=self.individual,
            sample_type=self.sample_type,
            isolation_by=self.contact,
            created_by=self.user,
        )
        report_test = Test.objects.create(
            sample=report_sample,
            test_type=self.wes_type,
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.individual,
            id_type=self.rb_type,
            id_value="RB_2024_27.1",
            created_by=self.user,
        )

        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                report_path = Path(tmpdir) / "RB_2024_27.1_TNS_WGS.docx"
                with zipfile.ZipFile(report_path, "w") as zf:
                    zf.writestr(
                        "[Content_Types].xml",
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
                    )
                    zf.writestr(
                        "word/document.xml",
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                        "<w:body><w:p><w:r><w:t>Report</w:t></w:r></w:p></w:body></w:document>",
                    )

                self.command._step_file_attachments(None, tmpdir)

        pipeline = Pipeline.objects.filter(test=report_test, type__name="Franklin").first()
        self.assertIsNotNone(pipeline)
        self.assertEqual(
            set(pipeline.statuses.values_list("name", flat=True)),
            {"Unsure Import"},
        )

        analysis = pipeline.analyses.first()
        self.assertIsNotNone(analysis)
        self.assertEqual(
            set(analysis.statuses.values_list("name", flat=True)),
            {"Unsure Import"},
        )

        self.assertTrue(
            AnalysisReport.objects.filter(
                analysis=analysis,
                file__endswith="RB_2024_27.1_TNS_WGS.docx",
            ).exists()
        )

    def test_report_filename_resolves_biobank_cross_identifier(self):
        biobank_individual = Individual.objects.create(
            full_name="Biobank Person",
            family=self.family,
            created_by=self.user,
        )
        biobank_type = IdentifierType.objects.create(
            name="Biobank",
            description="Biobank identifier",
            created_by=self.user,
            use_priority=2,
        )
        CrossIdentifier.objects.create(
            individual=biobank_individual,
            id_type=biobank_type,
            id_value="RD3.F149.4",
            created_by=self.user,
        )
        bio_sample = Sample.objects.create(
            individual=biobank_individual,
            sample_type=self.sample_type,
            isolation_by=self.contact,
            created_by=self.user,
        )
        bio_test_type = TestType.objects.create(name="Sanger", created_by=self.user)
        bio_test = Test.objects.create(
            sample=bio_sample,
            test_type=bio_test_type,
            created_by=self.user,
        )
        bio_pipeline_type = PipelineType.objects.create(name="Sanger", created_by=self.user)
        Pipeline.objects.create(
            test=bio_test,
            performed_date=date(2025, 1, 3),
            performed_by=self.user,
            type=bio_pipeline_type,
            created_by=self.user,
        )

        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                report_path = Path(tmpdir) / "RD3.F149.4_RAC_CHKA_SANGER_RAPOR.docx"
                with zipfile.ZipFile(report_path, "w") as zf:
                    zf.writestr(
                        "[Content_Types].xml",
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
                    )
                    zf.writestr(
                        "word/document.xml",
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                        "<w:body><w:p><w:r><w:t>Report</w:t></w:r></w:p></w:body></w:document>",
                    )

                self.command._step_file_attachments(None, tmpdir)

        self.assertTrue(
            AnalysisReport.objects.filter(
                file__endswith="RD3.F149.4_RAC_CHKA_SANGER_RAPOR.docx"
            ).exists()
        )
        self.assertFalse(
            any(
                rec["reason"] == "Report filename did not match an importable ID pattern."
                for rec in self.command.issue_records
            )
        )

    def test_rarepipe_fallback_creates_wes_test_with_unsure_import(self):
        rarepipe_individual = Individual.objects.create(
            full_name="RarePipe Person",
            family=self.family,
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=rarepipe_individual,
            id_type=self.rb_type,
            id_value="RB_2026_15.1",
            created_by=self.user,
        )

        row = {
            "Date": date(2025, 1, 2),
            "Matched ID": "RB_2026_15.1",
            "Samplesheet Name": "RarePipe Sheet",
            "Sample ID": "Sample-1",
        }

        with patch.object(self.command, "_ws_rows", return_value=[row]):
            self.command._step_rarepipe_analiz(None)

        sample = rarepipe_individual.samples.first()
        self.assertIsNotNone(sample)
        self.assertEqual(
            set(sample.statuses.values_list("name", flat=True)),
            {"Not Available", "Unsure Import"},
        )

        test = Test.objects.filter(sample=sample, test_type__name="WES").first()
        self.assertIsNotNone(test)
        self.assertEqual(
            set(test.statuses.values_list("name", flat=True)),
            {"Previous", "Unsure Import"},
        )

        pipeline = Pipeline.objects.filter(test=test, type__name="RarePipe").first()
        self.assertIsNotNone(pipeline)
        self.assertEqual(
            set(r["severity"] for r in self.command.issue_records if r["step"] == "step15"),
            {"info"},
        )

    def test_wgs_tuseb_separator_only_rows_are_logged_as_info(self):
        with patch.object(self.command, "_ws_rows", return_value=[{"Örnek No:": "1"}]):
            self.command._step_wgs_tuseb(None)

        step9_records = [r for r in self.command.issue_records if r["step"] == "step9"]
        self.assertEqual(len(step9_records), 1)
        self.assertEqual(step9_records[0]["severity"], "info")
        self.assertEqual(step9_records[0]["reason"], "Separator row in WGS_TÜSEB skipped.")

    def test_yayin_ici_chromosomal_position_imports_new_variants_and_skips_duplicates_as_info(self):
        report_individual = Individual.objects.create(
            full_name="Yayin Person",
            family=self.family,
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=report_individual,
            id_type=self.rb_type,
            id_value="RB_2026_30.1",
            created_by=self.user,
        )
        SNV.objects.create(
            individual=report_individual,
            chromosome="chr10",
            start=77984023,
            end=77984023,
            reference="A",
            alternate="G",
            zygosity="het",
            created_by=self.user,
        )

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "GÜNCELyayıniciyedek"
        ws.append([
            "RareBoost ID",
            "Chromosomal Position",
            "Zygosity",
        ])
        ws.append([
            "RB_2026_30.1",
            "chr10-77984023 A>G\nchr10-78009515 C>T",
            "Heterozigot",
        ])

        with TemporaryDirectory() as tmpdir:
            xlsx_path = Path(tmpdir) / "yayin.xlsx"
            wb.save(xlsx_path)
            self.command._step_yayin_ici(str(xlsx_path))

        self.assertEqual(
            SNV.objects.filter(individual=report_individual).count(),
            2,
        )
        info_reasons = [
            rec["reason"]
            for rec in self.command.issue_records
            if rec["step"] == "step20" and rec["severity"] == "info"
        ]
        self.assertIn("Variant already exists; duplicate skipped.", info_reasons)
