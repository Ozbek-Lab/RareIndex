import os
import re
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core.files import File
from django.conf import settings
from django.contrib.auth import get_user_model
from lab.models import Individual, AnalysisRequestForm, Analysis
from variant.models import AnalysisReport

User = get_user_model()

class Command(BaseCommand):
    help = 'Import analysis files from provided directories'

    def handle(self, *args, **options):
        # Directories
        base_dir = settings.BASE_DIR
        forms_dir = base_dir / "Özbek Vaka Başvuru Formları-20251205T123045Z-1-001" / "Özbek Vaka Başvuru Formları"
        reports_dir = base_dir / "Teknik_Raporlar-20251205T123032Z-1-001" / "Teknik_Raporlar"

        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            self.stdout.write(self.style.ERROR("No superuser found. Please create one."))
            return

        # Regex for ID extraction: RB_YYYY_ID.SUBID
        # Matches ID at the start of filename, up to the next underscore typically, 
        # but file names are like RB_2024_73.1_AAM.docx
        # So we want RB, then Year, then dot/digits until something else.
        # Actually pattern is RB_YYYY_ID where ID can contains dots.
        # e.g. RB_2024_114.1.1 -> RB_2024_114.1.1
        # It seems it's always RB_YYYY_NUM[.NUM[.NUM]] followed by _Initials...
        
        id_regex = re.compile(r"^(RB_\d{4}_[\d\.]+)")

        # 1. Import Request Forms
        self.stdout.write("Importing Request Forms...")
        if forms_dir.exists():
            for file_path in forms_dir.glob("*"):
                if file_path.name.startswith("."): continue
                
                match = id_regex.match(file_path.name)
                if match:
                    lab_id = match.group(1)
                    # Find individual
                    # We look for CrossIdentifier with this value
                    # Note: CrossIdentifier stores ID value.
                    try:
                        individual = Individual.objects.filter(
                            cross_ids__id_type__name="RareBoost",
                            cross_ids__id_value=lab_id
                        ).first()
                        
                        if individual:
                            # Check if already exists to avoid dupes?
                            # Using filename as check
                            if not AnalysisRequestForm.objects.filter(file__contains=file_path.name).exists():
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
                                self.stdout.write(f"Skipping existing form for {lab_id}")
                        else:
                            self.stdout.write(self.style.WARNING(f"Individual not found for ID {lab_id} (file: {file_path.name})"))
                            
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Error processing {file_path.name}: {e}"))
        else:
            self.stdout.write(self.style.WARNING(f"Forms directory not found: {forms_dir}"))

        # 2. Import Reports
        self.stdout.write("\nImporting Analysis Reports...")
        if reports_dir.exists():
            for file_path in reports_dir.glob("*"):
                if file_path.name.startswith("."): continue
                
                match = id_regex.match(file_path.name)
                if match:
                    lab_id = match.group(1)
                    
                    individual = Individual.objects.filter(
                            cross_ids__id_type__name="RareBoost",
                            cross_ids__id_value=lab_id
                        ).first()
                    
                    if individual:
                        # Find Analysis
                        # Trying to match analysis type from filename
                        filename_lower = file_path.name.lower()
                        analysis_qs = Analysis.objects.filter(test__sample__individual=individual)
                        
                        target_analysis = None
                        
                        if "wgs" in filename_lower:
                             target_analysis = analysis_qs.filter(type__name__icontains="wgs").last()
                        elif "wes" in filename_lower:
                             target_analysis = analysis_qs.filter(type__name__icontains="wes").last()
                        elif "sanger" in filename_lower:
                             target_analysis = analysis_qs.filter(type__name__icontains="sanger").last()
                             
                        # Fallback to latest
                        if not target_analysis:
                             target_analysis = analysis_qs.last()
                             
                        if target_analysis:
                             if not AnalysisReport.objects.filter(file__contains=file_path.name).exists():
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
                                self.stdout.write(f"Skipping existing report for {lab_id}")
                        else:
                            self.stdout.write(self.style.WARNING(f"No analysis found for {lab_id} to link report {file_path.name}"))
                    else:
                        self.stdout.write(self.style.WARNING(f"Individual not found for ID {lab_id} (file: {file_path.name})"))

        else:
             self.stdout.write(self.style.WARNING(f"Reports directory not found: {reports_dir}"))
