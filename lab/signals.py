from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.core.cache import cache
from .models import Individual

@receiver(m2m_changed, sender=Individual.hpo_terms.through)
def invalidate_hpo_tree_cache(sender, instance, action, **kwargs):
    """
    Invalidate the HPO tree cache whenever HPO terms are added/removed from an Individual.
    """
    if action in ["post_add", "post_remove", "post_clear"]:
        cache.delete("hpo_tree_structure")

# Preview Generation Signals
import os
import pypandoc
from django.db.models.signals import post_save
from django.core.files.base import ContentFile
from weasyprint import HTML, CSS
from .models import AnalysisRequestForm, AnalysisReport

def convert_docx_to_pdf_preview(instance, file_field_name, preview_field_name):
    """
    Helper to convert DOCX -> HTML -> PDF and save as preview.
    """
    file_field = getattr(instance, file_field_name)
    preview_field = getattr(instance, preview_field_name)

    # If no file or already has preview (and file hasn't changed?), skip.
    # For simplicity, we regenerate if preview is missing.
    if not file_field or preview_field:
        return

    filename = file_field.name
    if not filename.lower().endswith('.docx'):
        return

    try:
        # 1. Convert DOCX to HTML using Pandoc
        # We need the absolute path to the file.
        input_path = file_field.path

        # Convert to HTML string
        html_content = pypandoc.convert_file(
            input_path, 
            'html', 
            format='docx',
            extra_args=['--mathml'] # mathml for better formula support if needed
        )

        # 2. Convert HTML to PDF using WeasyPrint
        # We wrap HTML in a basic template to ensure styling
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: sans-serif; font-size: 12px; margin: 20px; }}
                table {{ border-collapse: collapse; width: 100%; }}
                td, th {{ border: 1px solid #ddd; padding: 8px; }}
                img {{ max-width: 100%; height: auto; }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """

        pdf_bytes = HTML(string=full_html).write_pdf()

        # 3. Save as preview file
        # Create a new filename for the preview
        preview_filename = os.path.splitext(os.path.basename(filename))[0] + '_preview.pdf'

        # We save directly to the field without triggering save() on the instance recursively
        # by using save(save=False) on the field and then update_fields on the instance if needed,
        # but here we just want to save the file content to the field storage.
        # However, to persist the filename in the DB we need to save the model.
        # Using update_fields avoids infinite recursion if we are careful,
        # but since we check `if preview_field: return` at the top, it acts as a guard.
        
        getattr(instance, preview_field_name).save(preview_filename, ContentFile(pdf_bytes), save=False)
        instance.save(update_fields=[preview_field_name])

        print(f"Generated preview for {filename}")

    except Exception as e:
        print(f"Error generating preview for {filename}: {e}")


@receiver(post_save, sender=AnalysisRequestForm)
def generate_request_form_preview(sender, instance, created, **kwargs):
    convert_docx_to_pdf_preview(instance, 'file', 'preview_file')

@receiver(post_save, sender=AnalysisReport)
def generate_analysis_report_preview(sender, instance, created, **kwargs):
    convert_docx_to_pdf_preview(instance, 'file', 'preview_file')

