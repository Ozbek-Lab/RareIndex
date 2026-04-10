import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from lab.management.commands.import_all import Command


class ImportIssueLoggingTests(SimpleTestCase):
    def test_issue_writer_splits_info_rows_into_separate_file(self):
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            command = Command()
            command.issue_log_path = tmp_path / "import_all_issues.tsv"
            command.info_log_path = tmp_path / "import_all_info.tsv"
            command.error_log_path = tmp_path / "import_all_errors.tsv"
            command.issue_records = [
                {
                    "step": "step14",
                    "sheet": "Gennext Analiz Listesi",
                    "severity": "warning",
                    "reason": "No WES or WGS test found for individual.",
                    "lab_id": "RB_2025_81.2",
                    "context": '{"variant": "x"}',
                    "row_data": '{"a": 1}',
                },
                {
                    "step": "step14",
                    "sheet": "Gennext Analiz Listesi",
                    "severity": "info",
                    "reason": "No WES or WGS test found; created fallback WES test with Previous + Unsure Import.",
                    "lab_id": "RB_2025_81.2",
                    "context": '{"variant": "x"}',
                    "row_data": '{"a": 1}',
                },
                {
                    "step": "step16",
                    "sheet": "Variant List",
                    "severity": "error",
                    "reason": "Unhandled error while importing variant.",
                    "lab_id": "RB_2025_81.2",
                    "context": '{"error": "boom"}',
                    "row_data": '{"a": 2}',
                },
            ]

            command._write_issue_log()

            with command.issue_log_path.open("r", encoding="utf-8", newline="") as fh:
                issue_rows = list(csv.DictReader(fh, delimiter="\t"))
            with command.info_log_path.open("r", encoding="utf-8", newline="") as fh:
                info_rows = list(csv.DictReader(fh, delimiter="\t"))
            with command.error_log_path.open("r", encoding="utf-8", newline="") as fh:
                error_rows = list(csv.DictReader(fh, delimiter="\t"))

            self.assertEqual([row["severity"] for row in issue_rows], ["warning", "error"])
            self.assertEqual([row["severity"] for row in info_rows], ["info"])
            self.assertEqual([row["severity"] for row in error_rows], ["error"])
