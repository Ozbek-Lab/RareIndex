import os
import re
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core.files import File
from django.conf import settings
from django.contrib.auth import get_user_model
from lab.models import Individual, AnalysisRequestForm, Pipeline, Analysis, AnalysisReport

User = get_user_model()

class Command(BaseCommand):
    help = 'Import analysis files from provided directories'

    def add_arguments(self, parser):
        parser.add_argument(
            '--forms-dir',
            type=str,
            help='Directory containing request forms',
            required=False
        )
        parser.add_argument(
            '--reports-dir',
            type=str,
            help='Directory containing analysis reports',
            required=False
        )

    def handle(self, *args, **options):
        forms_dir_str = options.get('forms_dir')
        reports_dir_str = options.get('reports_dir')
        
        # Regex for ID extraction: RB_YYYY_ID.SUBID
        id_regex = re.compile(r"^(RB_\d{4}_[\d\.]+)")
        
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            self.stdout.write(self.style.ERROR("No superuser found. Please create one."))
            return

        # 1. Import Request Forms
        if forms_dir_str:
            forms_dir = Path(forms_dir_str)
            self.stdout.write(f"Importing Request Forms from {forms_dir}...")
            if forms_dir.exists():
                for file_path in forms_dir.glob("*"):
                    if file_path.name.startswith("."): continue
                    
                    # Skip directories
                    if not file_path.is_file(): continue

                    match = id_regex.match(file_path.name)
                    if match:
                        lab_id = match.group(1)
                        try:
                            individual = Individual.objects.filter(
                                cross_ids__id_type__name="RareBoost",
                                cross_ids__id_value=lab_id
                            ).first()

                            if individual:
                                if not AnalysisRequestForm.objects.filter(file__endswith=file_path.name).exists():
                                    with open(file_path, "rb") as f:
                                        form_obj = AnalysisRequestForm(
                                            individual=individual,
                                            description=f"Imported from {file_path.name}",
                                            created_by=admin_user
                                        )
                                        form_obj.file.save(file_path.name, File(f))
                                        form_obj.save()
                                    self.stdout.write(self.style.SUCCESS(f"Imported form for {lab_id}: {file_path.name}"))
                                else:
                                    self.stdout.write(f"Skipping existing form for {lab_id} ({file_path.name})")
                            else:
                                self.stdout.write(self.style.WARNING(f"Individual not found for ID {lab_id} (file: {file_path.name})"))

                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"Error processing {file_path.name}: {e}"))
            else:
                self.stdout.write(self.style.WARNING(f"Forms directory not found: {forms_dir}"))
        else:
            self.stdout.write("No --forms-dir provided, skipping request forms import.")

        # 2. Import Reports
        if reports_dir_str:
            reports_dir = Path(reports_dir_str)
            self.stdout.write(f"\nImporting Analysis Reports from {reports_dir}...")
            if reports_dir.exists():
                for file_path in reports_dir.glob("*"):
                    if file_path.name.startswith("."): continue
                    
                    if not file_path.is_file(): continue

                    match = id_regex.match(file_path.name)
                    if match:
                        lab_id = match.group(1)

                        individual = Individual.objects.filter(
                                cross_ids__id_type__name="RareBoost",
                                cross_ids__id_value=lab_id
                            ).first()

                        if individual:
                            # Find Pipeline
                            filename_lower = file_path.name.lower()
                            pipeline_qs = Pipeline.objects.filter(test__sample__individual=individual)

                            target_pipeline = None
                            
                            if "wgs" in filename_lower:
                                target_pipeline = pipeline_qs.filter(type__name__icontains="wgs").last()
                            elif "wes" in filename_lower:
                                target_pipeline = pipeline_qs.filter(type__name__icontains="wes").last()
                            elif "sanger" in filename_lower:
                                target_pipeline = pipeline_qs.filter(type__name__icontains="sanger").last()

                            if not target_pipeline:
                                target_pipeline = pipeline_qs.last()

                            if target_pipeline:
                                # Find or create an Analysis on this pipeline
                                target_analysis = target_pipeline.analyses.first()
                                if not target_analysis:
                                    target_analysis = Analysis.objects.create(
                                        pipeline=target_pipeline,
                                        created_by=admin_user,
                                    )

                                if not AnalysisReport.objects.filter(file__endswith=file_path.name).exists():
                                    with open(file_path, "rb") as f:
                                        report_obj = AnalysisReport(
                                            analysis=target_analysis,
                                            description=f"Imported from {file_path.name}",
                                            created_by=admin_user
                                        )
                                        report_obj.file.save(file_path.name, File(f))
                                        report_obj.save()
                                    self.stdout.write(self.style.SUCCESS(f"Imported report for {lab_id} -> Analysis {target_analysis}"))
                                else:
                                    self.stdout.write(f"Skipping existing report for {lab_id} ({file_path.name})")
                            else:
                                self.stdout.write(self.style.WARNING(f"No pipeline found for {lab_id} to link report {file_path.name}"))
                        else:
                            self.stdout.write(self.style.WARNING(f"Individual not found for ID {lab_id} (file: {file_path.name})"))

            else:
                self.stdout.write(self.style.WARNING(f"Reports directory not found: {reports_dir}"))
        else:
            self.stdout.write("\nNo --reports-dir provided, skipping analysis reports import.")

