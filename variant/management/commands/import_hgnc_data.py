import csv
import requests
import io
from django.core.management.base import BaseCommand
from variant.models import Gene
from django.db import transaction

class Command(BaseCommand):
    help = 'Imports HGNC gene data from a TSV file'

    def handle(self, *args, **options):
        url = "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt"
        self.stdout.write(f"Downloading HGNC data from {url}...")
        
        response = requests.get(url)
        response.raise_for_status()
        
        # Parse TSV data
        content = response.content.decode('utf-8')
        reader = csv.DictReader(io.StringIO(content), delimiter='\t')
        
        genes_to_create = []
        genes_to_update = []
        
        self.stdout.write("Processing genes...")
        
        # Get existing genes to decide whether to update or create
        existing_genes = {g.hgnc_id: g for g in Gene.objects.all()}
        
        count = 0
        for row in reader:
            hgnc_id = row.get('hgnc_id')
            if not hgnc_id:
                continue
                
            gene_data = {
                'symbol': row.get('symbol', ''),
                'name': row.get('name', ''),
                'alias_symbol': row.get('alias_symbol', ''),
                'alias_name': row.get('alias_name', ''),
                'ensembl_gene_id': row.get('ensembl_gene_id', ''),
                'entrez_id': row.get('entrez_id', ''),
                'omim_id': row.get('omim_id', ''),
                'location': row.get('location', ''),
                'prev_symbol': row.get('prev_symbol', ''),
                'prev_name': row.get('prev_name', ''),
                'locus_type': row.get('locus_type', ''),
                'locus_group': row.get('locus_group', ''),
                'gene_family': row.get('gene_family', ''),
                'uniprot_ids': row.get('uniprot_ids', ''),
                'pubmed_id': row.get('pubmed_id', ''),
                'refseq_accession': row.get('refseq_accession', ''),
            }
            
            if hgnc_id in existing_genes:
                gene = existing_genes[hgnc_id]
                has_changes = False
                for key, value in gene_data.items():
                    if getattr(gene, key) != value:
                        setattr(gene, key, value)
                        has_changes = True
                if has_changes:
                    genes_to_update.append(gene)
            else:
                genes_to_create.append(Gene(hgnc_id=hgnc_id, **gene_data))
            
            count += 1
            if count % 1000 == 0:
                self.stdout.write(f"Processed {count} genes...")

        with transaction.atomic():
            if genes_to_create:
                self.stdout.write(f"Creating {len(genes_to_create)} new genes...")
                Gene.objects.bulk_create(genes_to_create, batch_size=1000)
            
            if genes_to_update:
                self.stdout.write(f"Updating {len(genes_to_update)} existing genes...")
                Gene.objects.bulk_update(genes_to_update, fields=[
                    'symbol', 'name', 'alias_symbol', 'alias_name', 'ensembl_gene_id',
                    'entrez_id', 'omim_id', 'location', 'prev_symbol', 'prev_name',
                    'locus_type', 'locus_group', 'gene_family', 'uniprot_ids',
                    'pubmed_id', 'refseq_accession'
                ], batch_size=1000)
                
        self.stdout.write(self.style.SUCCESS(f"Successfully imported HGNC data. Total processed: {count}"))
