from django.core.management.base import BaseCommand

from variant.models import Variant
from variant.services import AnnotationService


class Command(BaseCommand):
    help = "Link genes to all existing variants based on their annotations"

    def handle(self, *args, **options):
        service = AnnotationService()
        variants = Variant.objects.all()
        total = variants.count()

        self.stdout.write(f"Linking genes for {total} variant(s)...")

        for i, variant in enumerate(variants, start=1):
            service.link_genes(variant)
            if i % 100 == 0:
                self.stdout.write(f"  Processed {i}/{total}...")

        self.stdout.write(self.style.SUCCESS(f"Done. Processed {total} variant(s)."))
