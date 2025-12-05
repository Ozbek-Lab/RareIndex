import os
import pypandoc
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.files.base import ContentFile
from weasyprint import HTML, CSS
from .models import AnalysisRequestForm
from variant.models import AnalysisReport

def convert_docx_to_pdf_preview(instance, file_field_name, preview_field_name):
    """
    Helper to convert DOCX -> HTML -> PDF and save as preview.
    """
    file_field = getattr(instance, file_field_name)
    preview_field = getattr(instance, preview_field_name)
    
    # If no file or already has preview (and file hasn't changed?), skip.
    # For simplicity, we regenerate if preview is missing.
    # Ideally logic should check if file changed.
    if not file_field or preview_field:
        return

    filename = file_field.name
    if not filename.lower().endswith('.docx'):
        return

    try:
        # 1. Convert DOCX to HTML using Pandoc
        # We need the absolute path to the file.
        # If using storage backends like S3 this might need download.
        # Assuming local filesystem for now as per "works on container"
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
        
        # We save directly to the field. 
        # Note: calling save() on the field might trigger post_save again?
        # No, post_save is on the model instance. Calling instance.save() would trigger it.
        # But saving the file field saves the file to storage. We update the instance WITHOUT calling save() 
        # on the instance to avoid recursion loop, OR we disconnect signal.
        # Better: use update_fields in save() if supported, or just be careful.
        
        # Actually, since we check `if preview_field: return`, it should be safe from infinite recursion 
        # IF we populate the field before saving.
        
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
