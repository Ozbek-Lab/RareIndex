from contextlib import ExitStack
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import openpyxl
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from lab.management.commands._import_helpers import get_or_create_pipeline_type, get_or_create_test_type
from lab.management.commands.import_all import Command
from lab.models import (
    Analysis, AnalysisReport, CrossIdentifier, Family, IdentifierType, Individual,
    Note, Pipeline, PipelineType, Sample, SampleType, Status,
    Test as LabTest, TestType,
)
from ontologies.models import Ontology, Term
from variant.models import Gene, Variant


class ImportAnalysisReconciliationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="importer")
        self.individual = Individual.objects.create(created_by=self.user)
        self.id_type = IdentifierType.objects.create(
            name="RareBoost", use_priority=1, created_by=self.user,
        )
        self.lab_id = "RB_2026_301.1"
        CrossIdentifier.objects.create(
            individual=self.individual, id_type=self.id_type,
            id_value=self.lab_id, created_by=self.user,
        )
        sample_type = SampleType.objects.create(name="Blood", created_by=self.user)
        self.sample = Sample.objects.create(
            individual=self.individual, sample_type=sample_type, created_by=self.user,
        )
        self.wgs = TestType.objects.create(name="WGS", created_by=self.user)
        self.test = LabTest.objects.create(
            sample=self.sample, test_type=self.wgs, created_by=self.user,
        )
        self.command = Command(stdout=StringIO())
        self.command.admin_user = self.user
        self.command.dry_run = False
        self.command.pending_analyses = []
        self.command.issue_records = []
        self.command.import_source_name = "master.xlsx"
        self.command.id_types = {"RareBoost": self.id_type}
        self.command.statuses = {}
        for model in (Individual, Sample, LabTest, Pipeline, Analysis, AnalysisReport):
            ct = ContentType.objects.get_for_model(model)
            self.command.statuses[model._meta.model_name] = {
                "unsure_import": Status.objects.create(
                    name="Unsure Import", content_type=ct, created_by=self.user,
                ),
            }
        self.command.statuses["test"]["previous"] = Status.objects.create(
            name="Previous", content_type=ContentType.objects.get_for_model(LabTest),
            created_by=self.user,
        )
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for target in (
            "variant.signals.AnnotationService",
            "lab.signals.convert_docx_to_pdf_preview",
        ):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(self.command, "_backfill_testtype_report_fields")
        patcher.start()
        self.addCleanup(patcher.stop)

    def workbook(self, sheets):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        for name, rows in sheets.items():
            ws = wb.create_sheet(name)
            for row in rows:
                ws.append(row)
        return wb

    def master_workbook(self):
        return self.workbook({
            "Analiz Takip": [
                ["Özbek Lab. ID", "VERİ KAYNAĞI", "Test Notları"],
                [self.lab_id, "WGS", "First analysis"],
                [self.lab_id, "WGS", "Second analysis"],
            ],
            "Gennext Analiz Listesi": [
                ["Gennext ID", "Gennext Date"], [self.lab_id, date(2026, 1, 1)],
            ],
            "RarePipe Analiz Listesi": [
                ["Matched ID", "Date"], [self.lab_id, date(2026, 2, 1)],
            ],
        })

    def make_pipeline(self, name, test=None, version=None):
        pipeline_type, _ = PipelineType.objects.get_or_create(
            name=name, version=version, defaults={"created_by": self.user},
        )
        return Pipeline.objects.create(
            test=test or self.test, type=pipeline_type,
            performed_date=date(2026, 1, 1), performed_by=self.user,
            created_by=self.user,
        )

    def save_workbook(self, name, wb):
        path = Path(self.temp.name) / name
        wb.save(path)
        return str(path)

    def import_yayin_row(self, **values):
        row = {"RareBoost ID": self.lab_id, **values}
        path = self.save_workbook("yayin.xlsx", self.workbook({
            "GÜNCELyayıniciyedek": [list(row), list(row.values())],
        }))
        self.command._step_yayin_ici(path)

    def test_rows_wait_for_both_pipeline_sheets_and_reimport_reuses_them(self):
        wb = self.master_workbook()
        for _ in range(2):
            self.command.pending_analyses = []
            self.command._step5_analiz_takip(wb)
            self.command._step_gennext_analiz(wb)
            self.command._step_rarepipe_analiz(wb)
            if not Analysis.objects.exists():
                self.assertEqual(len(self.command.pending_analyses), 2)
            self.command._finalize_imported_analyses()
            self.assertEqual(Analysis.objects.count(), 2)
            self.assertFalse(Analysis.objects.filter(pipeline=None).exists())
            self.assertFalse(Analysis.objects.exclude(type__name="Initial").exists())
            self.assertEqual(Analysis.objects.filter(pipeline__type__name="RarePipe").count(), 2)
            self.assertEqual(Pipeline.objects.count(), 2)
        for analysis in Analysis.objects.all():
            source = analysis.notes.get(content__startswith="Import source:").content
            self.assertIn(self.lab_id, source)
            self.assertIn('"row_number":', source)

    def test_ozbek_tests_are_created_after_real_samples_and_reused_by_analiz_takip(self):
        individual = Individual.objects.create(created_by=self.user)
        lab_id = "RB_2026_302.1"
        CrossIdentifier.objects.create(
            individual=individual,
            id_type=self.id_type,
            id_value=lab_id,
            created_by=self.user,
        )
        self.command.statuses["sample"].update({
            "available": None,
            "not_available": None,
            "planned": None,
            "received": None,
            "isolated": None,
        })
        row = {
            "Özbek Lab. ID": lab_id,
            "Örnek Tipi": "Serum",
            "Geliş Tarihi": date(2026, 1, 12),
            "İleri tetkik / planlanan": "WES",
        }

        self.command._step4_samples([row])

        sample = Sample.objects.get(individual=individual)
        test = LabTest.objects.get(sample=sample, test_type__name="WES")
        self.assertEqual(individual.samples.count(), 1)

        workbook = self.workbook({
            "Analiz Takip": [
                ["Özbek Lab. ID", "VERİ KAYNAĞI"],
                [lab_id, "WES"],
            ],
        })
        self.command._step5_analiz_takip(workbook)

        self.assertEqual(individual.get_all_tests().count(), 1)
        self.assertEqual(self.command.pending_analyses[-1]["test"].pk, test.pk)

    def test_provider_priority_does_not_cross_individual_or_test_modality(self):
        wes = TestType.objects.create(name="WES", created_by=self.user)
        wes_test = LabTest.objects.create(sample=self.sample, test_type=wes, created_by=self.user)
        self.make_pipeline("RarePipe", test=wes_test)
        other = Individual.objects.create(created_by=self.user)
        other_sample = Sample.objects.create(
            individual=other, sample_type=self.sample.sample_type, created_by=self.user,
        )
        other_test = LabTest.objects.create(
            sample=other_sample, test_type=self.wgs, created_by=self.user,
        )
        self.make_pipeline("RarePipe", test=other_test)
        gennext = self.make_pipeline("Gennext")
        self.assertEqual(self.command._pipeline_for_import_test(self.test), gennext)
        rarepipe = self.make_pipeline("RarePipe", version="1")
        self.make_pipeline("RarePipe", version="2")
        self.assertEqual(self.command._pipeline_for_import_test(self.test), rarepipe)

    def test_missing_pipeline_creates_and_reuses_labeled_franklin(self):
        self.command._step5_analiz_takip(self.master_workbook())
        self.command._finalize_imported_analyses()
        self.assertEqual(Analysis.objects.count(), 2)
        pipeline = Pipeline.objects.get()
        self.assertEqual(pipeline.type.name, "Franklin")
        self.assertEqual(pipeline.test_id, self.test.pk)
        self.assertTrue(pipeline.statuses.filter(name="Unsure Import").exists())
        self.assertIn("not a known run date", pipeline.notes.get().content)
        self.assertEqual(self.command._pipeline_for_import_test(self.test), pipeline)
        self.assertFalse(Analysis.objects.filter(pipeline=None).exists())
        self.assertFalse(Analysis.objects.exclude(performed_date=None).exists())

    def test_analiz_takip_preserves_supplied_type_and_defaults_blank_to_initial(self):
        wb = self.workbook({
            "Analiz Takip": [
                ["Özbek Lab. ID", "VERİ KAYNAĞI", "Analiz Türü"],
                [self.lab_id, "WGS", "Reanalysis"],
                [self.lab_id, "WGS", None],
            ],
        })
        self.command._step5_analiz_takip(wb)
        self.command._finalize_imported_analyses()
        self.assertCountEqual(
            Analysis.objects.values_list("type__name", flat=True),
            ["Reanalysis", "Initial"],
        )

    def test_rarepipe_without_analysis_row_creates_only_pipeline(self):
        self.command._step_rarepipe_analiz(self.master_workbook())
        self.command._finalize_imported_analyses()
        self.command._finalize_imported_analyses()
        self.assertFalse(Analysis.objects.exists())
        self.assertEqual(Pipeline.objects.get().type.name, "RarePipe")

    def test_unversioned_pipeline_type_does_not_collide_with_tsv_versions(self):
        self.make_pipeline("RarePipe", version="1")
        self.make_pipeline("RarePipe", version="2")
        result = get_or_create_pipeline_type("RarePipe", self.user)
        self.assertIsNone(result.version)
        self.assertEqual(get_or_create_pipeline_type("RarePipe", self.user), result)

    def test_yayin_summary_is_one_idempotent_note_with_original_contents(self):
        raw = "Reanalysis, WGS\nRNA Seq"
        for _ in range(2):
            self.command._process_rb_reanaliz(self.individual, raw)
        self.assertEqual(self.individual.notes.get().content, "Yayın İçi: " + raw)
        self.assertFalse(Analysis.objects.exists())
        self.assertFalse(Pipeline.objects.exists())
        self.assertEqual(LabTest.objects.count(), 1)

    def test_missing_or_unknown_zygosity_imports_with_warning_in_both_sheets(self):
        for source in ("Variant List", "Yayın İçi"):
            for index, raw in enumerate((None, "  ", "not recognized", "unknown", "n/a")):
                with self.subTest(source=source, zygosity=raw):
                    position = 500 + index + (100 if source == "Yayın İçi" else 0)
                    row = {"Chromosomal Position": f"chr1-{position} A>G", "Zygosity": raw}
                    previous_issues = len(self.command.issue_records)
                    if source == "Variant List":
                        row = {"Özbek Lab. ID": self.lab_id, **row}
                        self.command._step_variants(self.workbook({
                            "Variant List": [list(row), list(row.values())],
                        }))
                    else:
                        self.import_yayin_row(**row)
                    variant = Variant.objects.get(start=position)
                    self.assertEqual(variant.zygosity, "")
                    warnings = self.command.issue_records[previous_issues:]
                    self.assertTrue(any(
                        issue["severity"] == "warning"
                        and "continuing with empty zygosity" in issue["reason"]
                        for issue in warnings
                    ))
        self.assertIn("continuing with empty zygosity", self.command.stdout.getvalue())

    def test_yayin_dry_run_does_not_create_summary_note(self):
        self.command.dry_run = True
        self.command._process_rb_reanaliz(self.individual, "WGS")
        self.command._finalize_imported_analyses()
        self.assertFalse(Note.objects.exists())
        self.assertFalse(Analysis.objects.exists())

    def test_yayin_later_steps_work_without_summary_analyses(self):
        path = self.save_workbook("yayin.xlsx", self.workbook({
            "GÜNCELyayıniciyedek": [
                ["RareBoost ID", None, "RareBoost Reanaliz/WGS/WES/RNA seq",
                 "Previous test", "Singleton-Trio", "Chromosomal Position", "Zygosity"],
                [self.lab_id, "ignored", "Reanalysis, WGS", "CMA", "Trio", "chr1-123 A>G", "het"],
            ],
        }))
        self.command._step_yayin_ici(path)
        self.assertEqual(self.individual.notes.get().content, "Yayın İçi: Reanalysis, WGS")
        self.assertTrue(self.test.notes.filter(content="Trio").exists())
        previous = LabTest.objects.get(test_type__name="CMA")
        self.assertTrue(previous.statuses.filter(name="Previous").exists())
        self.assertFalse(previous.notes.filter(content="Trio").exists())
        variant = Variant.objects.get()
        self.assertEqual(variant.individual_id, self.individual.pk)
        self.assertIsNone(variant.analysis_id)
        self.assertFalse(Analysis.objects.exists())
        self.assertFalse(Pipeline.objects.exists())

    def test_report_uses_matching_rarepipe_instead_of_creating_franklin(self):
        self.make_pipeline("Gennext")
        rarepipe = self.make_pipeline("RarePipe")
        report_dir = Path(self.temp.name) / "reports"
        report_dir.mkdir()
        (report_dir / f"{self.lab_id}_WGS.txt").write_text("Test report")
        with self.settings(MEDIA_ROOT=self.temp.name):
            self.command._step_file_attachments(None, str(report_dir))
        self.assertEqual(AnalysisReport.objects.get().analysis.pipeline_id, rarepipe.pk)
        self.assertEqual(AnalysisReport.objects.get().analysis.type.name, "Initial")
        self.assertFalse(Pipeline.objects.filter(type__name="Franklin").exists())

    def test_reports_reuse_one_franklin_and_analysis_for_matching_test(self):
        report_dir = Path(self.temp.name) / "reports"
        report_dir.mkdir()
        for suffix in ("one", "two"):
            (report_dir / f"{self.lab_id}_WGS_{suffix}.txt").write_text("Test report")
        with self.settings(MEDIA_ROOT=self.temp.name):
            self.command._step_file_attachments(None, str(report_dir))
        self.assertEqual(AnalysisReport.objects.count(), 2)
        self.assertEqual(Analysis.objects.count(), 1)
        self.assertEqual(Analysis.objects.get().type.name, "Initial")
        self.assertEqual(Pipeline.objects.get().type.name, "Franklin")

    def test_report_fallback_does_not_attach_wgs_report_to_wes_test(self):
        self.test.test_type = TestType.objects.create(name="WES", created_by=self.user)
        self.test.save()
        self.make_pipeline("RarePipe")
        report_dir = Path(self.temp.name) / "reports"
        report_dir.mkdir()
        (report_dir / f"{self.lab_id}_WGS.txt").write_text("Test report")
        with self.settings(MEDIA_ROOT=self.temp.name):
            self.command._step_file_attachments(None, str(report_dir))
        pipeline = AnalysisReport.objects.get().analysis.pipeline
        self.assertEqual(pipeline.type.name, "Franklin")
        self.assertEqual(pipeline.test.test_type.name, "WGS")
        self.assertEqual(AnalysisReport.objects.get().analysis.type.name, "Initial")

    def test_yayin_reanalysis_creates_missing_wes_and_reuses_it(self):
        for _ in range(2):
            self.import_yayin_row(**{
                "RareBoost Reanaliz/WGS/WES/RNA seq": "Reanalysis, WGS",
                "Singleton-Trio": "Singleton, Trio",
            })
        wes = LabTest.objects.get(test_type__name="WES")
        self.assertTrue(wes.notes.filter(content="Singleton").exists())
        self.assertTrue(self.test.notes.filter(content="Trio").exists())
        self.assertEqual(LabTest.objects.count(), 2)
        self.assertFalse(TestType.objects.filter(name="Reanalysis").exists())
        self.assertFalse(Analysis.objects.exists())
        self.assertFalse(Pipeline.objects.exists())
        self.assertTrue(self.individual.notes.filter(content="Yayın İçi: Reanalysis, WGS").exists())

    def test_yayin_unmatched_individual_is_logged_without_creating_records(self):
        path = self.save_workbook("unknown.xlsx", self.workbook({
            "GÜNCELyayıniciyedek": [
                ["RareBoost ID", "RareBoost Reanaliz/WGS/WES/RNA seq"],
                ["RB_2026_999.1", "WGS"],
            ],
        }))
        self.command._step_yayin_ici(path)
        self.assertEqual(Individual.objects.count(), 1)
        self.assertFalse(Note.objects.exists())
        self.assertTrue(any("Individual not found" in issue["reason"] for issue in self.command.issue_records))

    def test_yayin_recognized_values_overwrite_but_empty_unknown_values_do_not(self):
        family = Family.objects.create(
            family_id="F-301", is_consanguineous="true", created_by=self.user,
        )
        self.individual.family = family
        self.individual.is_affected = True
        self.individual.save()
        self.import_yayin_row(**{
            "Status (ex-alive)": " Exitus ", "Consanguinity": " NO ", "HPO": " SS ",
        })
        self.individual.refresh_from_db()
        family.refresh_from_db()
        self.assertFalse(self.individual.is_alive)
        self.assertFalse(self.individual.is_affected)
        self.assertEqual(family.is_consanguineous, "false")
        for value in (None, "", "UNKNOWN"):
            self.import_yayin_row(**{
                "Status (ex-alive)": value, "Consanguinity": value, "HPO": value,
            })
            self.individual.refresh_from_db()
            family.refresh_from_db()
            self.assertFalse(self.individual.is_alive)
            self.assertFalse(self.individual.is_affected)
            self.assertEqual(family.is_consanguineous, "false")
        for column in ("Status (ex-alive)", "Consanguinity", "HPO"):
            self.assertTrue(self.individual.notes.filter(content=f"Yayın İçi: {column}: UNKNOWN").exists())
        self.import_yayin_row(**{"Status (ex-alive)": "Alive", "Consanguinity": "Yes"})
        self.individual.refresh_from_db()
        family.refresh_from_db()
        self.assertTrue(self.individual.is_alive)
        self.assertEqual(family.is_consanguineous, "true")
        self.import_yayin_row(**{"Status (ex-alive)": "ex", "Consanguinity": False})
        self.individual.refresh_from_db()
        family.refresh_from_db()
        self.assertFalse(self.individual.is_alive)
        self.assertEqual(family.is_consanguineous, "false")

    def test_yayin_hpo_overwrites_healthy_and_keeps_existing_terms(self):
        ontology = Ontology.objects.create(type=1, label="HP")
        term = Term.objects.create(ontology=ontology, identifier="0001250", label="Seizure")
        old_term = Term.objects.create(ontology=ontology, identifier="0001249", label="Intellectual disability")
        self.individual.hpo_terms.add(old_term)
        self.import_yayin_row(HPO="HP:0001250")
        self.individual.refresh_from_db()
        self.assertTrue(self.individual.is_affected)
        self.assertSetEqual(set(self.individual.hpo_terms.all()), {term, old_term})

    def test_test_type_aliases_are_shared_across_import_paths(self):
        legacy = TestType.objects.create(name="rna-seq", created_by=self.user)
        for name in ("RNA Seq", "RNA seq", "rna-seq", "rna seq", "RNA_SEQ", "RNA sequencing"):
            self.assertEqual(get_or_create_test_type(name, self.user).pk, legacy.pk)
        legacy.refresh_from_db()
        self.assertEqual(legacy.name, "RNA Seq")
        self.assertEqual(TestType.objects.count(), 2)
        self.command._import_tests_from_field(self.individual, "RNA_SEQ", None)
        self.import_yayin_row(**{
            "Previous test": "rna-seq",
            "RareBoost Reanaliz/WGS/WES/RNA seq": "RNA seq",
            "Singleton-Trio": "Trio",
        })
        self.assertEqual(LabTest.objects.filter(test_type=legacy).count(), 1)
        self.assertTrue(LabTest.objects.get(test_type=legacy).notes.filter(content="Trio").exists())
        self.assertNotEqual(
            get_or_create_test_type("Long Read WGS", self.user).pk,
            get_or_create_test_type("wgs", self.user).pk,
        )

    def test_previous_na_creates_no_test_type_test_or_sample_and_continues_row(self):
        self.test.delete()
        self.sample.delete()
        initial_type_count = TestType.objects.count()
        for value in ("n/a", "N/A", "  n/A  ", " N / A ", "n/a, N/A"):
            with self.subTest(value=value):
                self.import_yayin_row(**{"Previous test": value, "NOTE": "Review needed"})
                self.assertEqual(TestType.objects.count(), initial_type_count)
                self.assertFalse(LabTest.objects.exists())
                self.assertFalse(Sample.objects.exists())
                self.assertFalse(self.individual.notes.filter(content__startswith="Yayın İçi: Previous test:").exists())
        self.assertEqual(self.individual.notes.filter(content="Yayın İçi: NOTE: Review needed").count(), 1)

    def test_previous_na_in_mixed_list_skips_even_an_existing_na_type(self):
        invalid_type = TestType.objects.create(name="n/a", created_by=self.user)
        self.import_yayin_row(**{"Previous test": "WGS, n/a, RNA_SEQ, N/A"})
        self.assertFalse(LabTest.objects.filter(test_type=invalid_type).exists())
        self.assertEqual(LabTest.objects.count(), 2)
        self.assertTrue(LabTest.objects.filter(test_type__name="RNA Seq").exists())

    def test_singleton_matches_source_order_and_creates_missing_tests(self):
        # WGS has the lowest database ID, but RNA Seq is first in the source.
        row = {
            "RareBoost Reanaliz/WGS/WES/RNA seq": "rna-seq, WGS (RB)",
            "Singleton-Trio": "Singleton, Trio",
        }
        for _ in range(2):
            self.import_yayin_row(**row)
        rna = LabTest.objects.get(test_type__name="RNA Seq")
        self.assertTrue(rna.notes.filter(content="Singleton").exists())
        self.assertTrue(rna.statuses.filter(name="Unsure Import").exists())
        self.assertEqual(self.test.notes.filter(content="Trio").count(), 1)
        self.assertFalse(self.test.notes.filter(content="Singleton").exists())
        self.assertEqual(LabTest.objects.count(), 2)
        self.assertEqual(self.individual.notes.filter(content="Yayın İçi: rna-seq, WGS (RB)").count(), 1)
        self.assertFalse(Analysis.objects.exists())
        self.assertFalse(Pipeline.objects.exists())

    def test_singleton_without_test_modality_creates_unspecified_test(self):
        self.test.delete()
        for _ in range(2):
            self.import_yayin_row(**{"Singleton-Trio": "Trio"})
        test = LabTest.objects.get()
        self.assertEqual(test.test_type.name, "Unspecified")
        self.assertTrue(test.statuses.filter(name="Unsure Import").exists())
        self.assertEqual(test.notes.filter(content="Trio").count(), 1)

    def test_singleton_mismatched_counts_preserve_values_without_guessing(self):
        self.import_yayin_row(**{
            "RareBoost Reanaliz/WGS/WES/RNA seq": "WGS, WES, RNA Seq",
            "Singleton-Trio": "Singleton, Trio",
        })
        self.assertEqual(LabTest.objects.count(), 3)
        self.assertTrue(self.individual.notes.filter(content="Yayın İçi: Singleton-Trio: Singleton, Trio").exists())
        for test in LabTest.objects.all():
            self.assertFalse(test.notes.filter(content__in=["Singleton", "Trio"]).exists())

    def test_unused_text_and_failed_variants_are_preserved_once_as_notes(self):
        row = {
            "NOTE": "Review with clinician\nRepeat sample",
            "Chromosomal Position": "not genomic coordinates",
            "Variant": "NM_000001:c.123A>G",
            "Gene": "SOURCE_ONLY_GENE",
            "Diagnostic Journey": "Long diagnostic journey",
            "Extra numeric column": 0,
            "Extra boolean column": False,
            "Empty column": None,
            "Klinisyen & İletişim Bilgileri": "Dr Example",  # No institution.
        }
        for _ in range(2):
            self.import_yayin_row(**row)
        for column, value in row.items():
            if value is not None:
                self.assertEqual(self.individual.notes.filter(content=f"Yayın İçi: {column}: {value}").count(), 1)
        self.assertFalse(self.individual.notes.filter(content__contains="Empty column").exists())
        self.assertFalse(Variant.objects.exists())
        self.assertFalse(Gene.objects.exists())

    def test_valid_variants_keep_unused_hgvs_and_gene_text_without_creating_genes(self):
        for _ in range(2):
            self.import_yayin_row(**{
                "Chromosomal Position": "chr1-123 A>G", "Variant": "NM_000001:c.123A>G",
                "Gene": "SOURCE_ONLY_GENE", "Zygosity": "het",
            })
        self.assertEqual(Variant.objects.count(), 1)
        self.assertFalse(Gene.objects.exists())
        self.assertTrue(self.individual.notes.filter(content="Yayın İçi: Gene: SOURCE_ONLY_GENE").exists())
        self.assertTrue(self.individual.notes.filter(content="Yayın İçi: Variant: NM_000001:c.123A>G").exists())
        self.assertFalse(self.individual.notes.filter(content__startswith="Yayın İçi: Chromosomal Position:").exists())
        self.assertFalse(self.individual.notes.filter(content__startswith="Yayın İçi: Zygosity:").exists())

    def test_recognized_note_status_is_attached_instead_of_becoming_unused_text(self):
        status = Status.objects.create(
            name="Review", content_type=ContentType.objects.get_for_model(Individual), created_by=self.user,
        )
        self.import_yayin_row(NOTE="review")
        self.assertTrue(self.individual.statuses.filter(pk=status.pk).exists())
        self.assertFalse(self.individual.notes.filter(content="Yayın İçi: NOTE: review").exists())

    def test_handle_imports_ozbek_demographics_before_yayin_supplements(self):
        master = self.save_workbook("master.xlsx", self.master_workbook())
        yayin = self.save_workbook("yayin.xlsx", self.workbook({
            "GÜNCELyayıniciyedek": [
                ["RareBoost ID", "Sex", "RareBoost Reanaliz/WGS/WES/RNA seq"],
                [self.lab_id, "male", "WGS"],
            ],
        }))

        def import_ozbek_individuals(*args):
            self.individual.sex = "female"
            self.individual.save()

        with ExitStack() as stack:
            stack.enter_context(patch("lab.management.commands.import_all.call_command"))
            stack.enter_context(patch.object(self.command, "_resolve_admin_user", return_value=self.user))
            stack.enter_context(patch.object(self.command, "_step1_setup", return_value=(
                self.command.statuses, self.command.id_types,
            )))
            stack.enter_context(patch.object(self.command, "_step2_families_institutions", return_value=({}, {}, None)))
            stack.enter_context(patch.object(self.command, "_step3_individuals", side_effect=import_ozbek_individuals))
            for name in (
                "_step0a_ensure_ontologies", "_step0b_ensure_hgnc", "_load_kurumlar_map",
                "_load_ozbek_lab_rows", "_step4_samples", "_step7_parent_links",
                "_step_sanger", "_step_wgs_tuseb", "_step_external", "_step_long_read",
                "_step_rna_seq", "_step_variants", "_step18_ensure_plot_templates",
                "_write_issue_log",
            ):
                stack.enter_context(patch.object(self.command, name))
            self.command.handle(
                xlsx_file=master, admin_username=self.user.username,
                dry_run=False, skip_hgnc=True, yayin_ici=yayin,
            )
        self.individual.refresh_from_db()
        self.assertEqual(self.individual.sex, "female")
        self.assertTrue(self.individual.notes.filter(content="Yayın İçi: WGS").exists())
        self.assertEqual(Analysis.objects.count(), 2)
        self.assertFalse(Analysis.objects.filter(pipeline=None).exists())
