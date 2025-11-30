from django.core.management.base import BaseCommand
import csv
import requests
import io
from variant.models import Gene

class Command(BaseCommand):
    help = 'Import genes from HGNC TSV file'

    def add_arguments(self, parser):
        parser.add_argument('--url', type=str, help='URL to HGNC TSV file')
        parser.add_argument('--file', type=str, help='Path to local HGNC TSV file')

    def handle(self, *args, **options):
        url = options['url']
        file_path = options['file']

        if not url and not file_path:
            self.stdout.write(self.style.ERROR('Please provide either --url or --file'))
            return

        if url:
            self.stdout.write(f'Downloading from {url}...')
            response = requests.get(url)
            response.raise_for_status()
            content = response.content.decode('utf-8')
            f = io.StringIO(content)
        else:
            self.stdout.write(f'Reading from {file_path}...')
            f = open(file_path, 'r', encoding='utf-8')

        reader = csv.DictReader(f, delimiter='\t')
        
        genes_to_create = []
        genes_to_update = []
        
        count = 0
        for row in reader:
            if row['status'] == 'Entry Withdrawn':
                continue
                
            hgnc_id = row['hgnc_id']
            symbol = row['symbol']
            name = row['name']
            alias_symbol = row.get('alias_symbol', '')
            alias_name = row.get('alias_name', '')
            ensembl_gene_id = row.get('ensembl_gene_id', '')
            entrez_id = row.get('entrez_id', '')
            omim_id = row.get('omim_id', '')
            location = row.get('location', '')
            
            defaults = {
                'symbol': symbol,
                'name': name,
                'alias_symbol': alias_symbol,
                'alias_name': alias_name,
                'ensembl_gene_id': ensembl_gene_id,
                'entrez_id': entrez_id,
                'omim_id': omim_id,
                'location': location,
            }
            
            obj, created = Gene.objects.update_or_create(
                hgnc_id=hgnc_id,
                defaults=defaults
            )
            
            if created:
                count += 1
                if count % 1000 == 0:
                    self.stdout.write(f'Processed {count} genes...')

        self.stdout.write(self.style.SUCCESS(f'Successfully imported/updated genes'))
        
        if not url:
            f.close()
