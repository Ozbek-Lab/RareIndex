from django.core.management.base import BaseCommand
from django.db.models import Q
from lab.models import AnalysisRequestForm
from variant.models import AnalysisReport
from lab.signals import convert_docx_to_pdf_preview

class Command(BaseCommand):
    help = 'Generate PDF previews for existing DOCX files'

    def handle(self, *args, **options):
        # 1. Request Forms
        forms = AnalysisRequestForm.objects.filter(
            Q(file__icontains='.docx') & (Q(preview_file__isnull=True) | Q(preview_file=''))
        )
        self.stdout.write(f"Found {forms.count()} Request Forms needing preview...")
        for form in forms:
            try:
                self.stdout.write(f"Processing Form {form.id}: {form.file.name}")
                convert_docx_to_pdf_preview(form, 'file', 'preview_file')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to generate preview for form {form.id}: {e}"))

        # 2. Analysis Reports
        reports = AnalysisReport.objects.filter(
            Q(file__icontains='.docx') & (Q(preview_file__isnull=True) | Q(preview_file=''))
        )
        self.stdout.write(f"\nFound {reports.count()} Reports needing preview...")
        for report in reports:
            try:
                self.stdout.write(f"Processing Report {report.id}: {report.file.name}")
                convert_docx_to_pdf_preview(report, 'file', 'preview_file')
            except Exception as e:
                 self.stdout.write(self.style.ERROR(f"Failed to generate preview for report {report.id}: {e}"))

        self.stdout.write(self.style.SUCCESS('Preview generation complete.'))
