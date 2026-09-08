from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from lab.models import TestType


class PopulateTestTypeReportDefaultsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="report-defaults-test")

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.reference = Path(directory.name) / "defaults.md"

    def create_type(self, name="WES", **fields):
        return TestType.objects.create(name=name, created_by=self.user, **fields)

    def run_command(self, *args, **options):
        output = StringIO()
        call_command("populate_test_type_report_defaults", *args, stdout=output, **options)
        return output.getvalue()

    def write_reference(self, content):
        self.reference.write_text(content, encoding="utf-8")

    def test_repository_reference_populates_matching_types(self):
        types = [self.create_type(name) for name in [" wes ", "WGS", "RNA Seq", "Sanger"]]
        unrelated = self.create_type("Panel", default_method_text="Keep panel method")
        output = self.run_command()
        templates = ["WESReanalysis", "WGS", "RNASeq", "Sanger"]
        for test_type, template in zip(types, templates):
            test_type.refresh_from_db()
            self.assertEqual(test_type.positive_report_template, f"reports/{template}_Positive_Report_Template.docx")
            self.assertEqual(test_type.negative_report_template, f"reports/{template}_Negative_Report_Template.docx")
            self.assertTrue(test_type.default_positive_comment_text)
            self.assertTrue(test_type.default_negative_result_text)
            self.assertTrue(test_type.default_method_text)
            self.assertTrue(test_type.default_limitations_text)
            self.assertEqual(test_type.default_total_reads_text, "")
            self.assertEqual(test_type.history.count(), 2)
        self.assertIn("on 4 test type(s)", output)
        unrelated.refresh_from_db()
        self.assertEqual(unrelated.default_method_text, "Keep panel method")
        self.assertEqual(unrelated.history.count(), 1)
        self.assertIn("Updated 0 field(s)", self.run_command())
        self.assertEqual(types[0].history.count(), 2)

    def test_default_preserves_existing_text_and_fills_whitespace(self):
        test_type = self.create_type(default_method_text="Custom method", default_negative_result_text=" \n ")
        self.run_command("--test-type", "wes")
        test_type.refresh_from_db()
        self.assertEqual(test_type.default_method_text, "Custom method")
        self.assertIn("varyant saptanmamıştır", test_type.default_negative_result_text)

    def test_overwrite_preserves_unicode_newlines_and_placeholders(self):
        test_type = self.create_type(default_positive_comment_text="Old comment")
        self.write_reference('''## WES
`default_positive_comment_text`
```text
Örnek: {{HPO_TERMS}}
İkinci satır.
```
''')
        self.run_command("--reference", str(self.reference), "--overwrite")
        test_type.refresh_from_db()
        self.assertEqual(test_type.default_positive_comment_text, "Örnek: {{HPO_TERMS}}\nİkinci satır.")
        self.assertIn("defaults.md", test_type.history.first().history_change_reason)

    def test_dry_run_does_not_save_or_create_history(self):
        test_type = self.create_type(default_method_text="Existing")
        output = self.run_command("--dry-run", "--overwrite", "--test-type", "WES")
        test_type.refresh_from_db()
        self.assertEqual(test_type.default_method_text, "Existing")
        self.assertEqual(test_type.positive_report_template, "")
        self.assertEqual(test_type.history.count(), 1)
        self.assertIn("Would update WES", output)

    def test_repeatable_type_selection_and_missing_records(self):
        wes = self.create_type()
        wgs = self.create_type("WGS")
        rna = self.create_type("RNA Seq")
        output = self.run_command("--test-type", "wes", "--test-type", "RNA Seq", "--test-type", "Sanger")
        wes.refresh_from_db()
        wgs.refresh_from_db()
        rna.refresh_from_db()
        self.assertTrue(wes.default_method_text)
        self.assertTrue(rna.default_method_text)
        self.assertEqual(wgs.default_method_text, "")
        self.assertIn("Test type not found: Sanger", output)
        self.assertFalse(TestType.objects.filter(name="Sanger").exists())
        with self.assertRaisesMessage(CommandError, "No reference section for: typo"):
            self.run_command("--test-type", "typo")

    def test_shared_field_precedence_and_legacy_fallback(self):
        test_type = self.create_type(default_method_text="Old method", default_filtering_text="Old filtering")
        self.write_reference('''## WES
`default_method_text`
```

```
`positive_method_text`
`Positive method`
`positive_filtering_text`
```

```
`negative_filtering_text`
```

```
`positive_limitations_text`
`Positive limitations`
`negative_limitations_text`
`Negative limitations`
''')
        self.run_command("--reference", str(self.reference), "--overwrite")
        test_type.refresh_from_db()
        self.assertEqual(test_type.default_method_text, "")
        self.assertEqual(test_type.default_filtering_text, "")
        self.assertEqual(test_type.default_limitations_text, "Positive limitations")

    def test_invalid_file_and_non_report_fields_fail_before_writes(self):
        test_type = self.create_type()
        with self.assertRaisesMessage(CommandError, "Cannot load report defaults"):
            self.run_command("--reference", str(self.reference))
        for content, error in [
            ("# Empty document", "No test type sections"),
            ("## WES\n`default_method_text`\n```text\nUnclosed", "Missing closing fence"),
            ("## WES\n`default_method_text`\n`Valid`\n`name`\n`Renamed`", "Unknown report fields"),
        ]:
            with self.subTest(error=error):
                self.write_reference(content)
                with self.assertRaisesMessage(CommandError, error):
                    self.run_command("--reference", str(self.reference))
        test_type.refresh_from_db()
        self.assertEqual(test_type.name, "WES")
        self.assertEqual(test_type.default_method_text, "")
        self.assertEqual(test_type.history.count(), 1)

    def test_validation_failure_does_not_partially_update_types(self):
        wes = self.create_type()
        self.create_type("WGS")
        self.write_reference("## WES\n`default_method_text`\n`Valid`\n## WGS\n`positive_report_template`\n`" + "x" * 256 + "`\n")
        with self.assertRaisesMessage(CommandError, "Invalid WGS.positive_report_template"):
            self.run_command("--reference", str(self.reference))
        wes.refresh_from_db()
        self.assertEqual(wes.default_method_text, "")
        self.assertEqual(wes.history.count(), 1)
