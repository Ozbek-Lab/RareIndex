from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import SNV, CNV, SV, Repeat
from .services import AnnotationService

@receiver(post_save, sender=SNV)
@receiver(post_save, sender=CNV)
@receiver(post_save, sender=SV)
@receiver(post_save, sender=Repeat)
def annotate_and_link_genes(sender, instance, created, **kwargs):
    if created:
        service = AnnotationService()
        
        # Fetch annotations
        # Note: These are synchronous calls and might slow down the request
        service.fetch_vep(instance)
        service.fetch_myvariant_info(instance)
        # Genebe is also available but maybe optional?
        # service.fetch_genebe(instance)
        
        # Link genes
        service.link_genes(instance)
