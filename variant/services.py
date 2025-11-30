import requests
import json
from django.utils import timezone
from django.db.models import Count, Q
from .models import Annotation
from lab.models import Analysis, Status

class DiagnosticService:
    """Service to calculate diagnostic yield and analysis statistics"""

    def get_diagnostic_yield(self, analysis_type=None):
        """
        Calculate diagnostic yield: Solved Analyses / Total Analyses
        Returns a dict with counts and percentage.
        """
        queryset = Analysis.objects.all()
        if analysis_type:
            queryset = queryset.filter(type=analysis_type)
            
        total = queryset.count()
        if total == 0:
            return {"total": 0, "solved": 0, "yield_percentage": 0.0}
            
        # Define solved statuses
        solved_statuses = ["Solved - P/LP", "Solved - VUS"]
        solved_count = queryset.filter(status__name__in=solved_statuses).count()
        
        return {
            "total": total,
            "solved": solved_count,
            "yield_percentage": round((solved_count / total) * 100, 2)
        }

    def get_variants_leading_to_diagnosis(self):
        """Return variants linked to solved analyses"""
        solved_statuses = ["Solved - P/LP", "Solved - VUS"]
        return Analysis.objects.filter(status__name__in=solved_statuses).values_list('found_variants', flat=True)


class AnnotationService:
    """Service to handle external annotation APIs"""
    
    def fetch_myvariant_info(self, variant):
        """Fetch annotation from MyVariant.info"""
        # Construct HGVS ID or similar
        # For SNV: chr1:g.123A>G
        # Assuming hg38
        if not hasattr(variant, 'snv'):
            return None # MyVariant mostly for SNVs/indels
        
        snv = variant.snv
        hgvs_id = f"chr{snv.chromosome}:g.{snv.start}{snv.reference}>{snv.alternate}"
        
        url = f"https://myvariant.info/v1/variant/{hgvs_id}"
        params = {'assembly': 'hg38'}
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                self._save_annotation(variant, "myvariant", data)
                return data
        except Exception as e:
            print(f"Error fetching MyVariant: {e}")
        return None

    def fetch_vep(self, variant):
        """Fetch annotation from Ensembl VEP"""
        # POST request for region
        # https://rest.ensembl.org/vep/human/region
        
        url = "https://rest.ensembl.org/vep/human/region"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        
        # Format: "{chr} {start} {end} {allele_string} {strand}"
        # allele_string: REF/ALT
        # strand: 1 (plus)
        
        if hasattr(variant, 'snv'):
            snv = variant.snv
            allele_string = f"{snv.reference}/{snv.alternate}"
            # VEP region: start end (inclusive)
            # For SNV start=end
            # But variant.start/end might be 0-based or 1-based?
            # Assuming 1-based for now as per VCF/standard
            
            payload = {
                "variants": [
                    f"{snv.chromosome} {snv.start} {snv.end} {allele_string} 1"
                ],
                "assembly_name": "GRCh38"
            }
            
            try:
                response = requests.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    self._save_annotation(variant, "vep", data)
                    return data
            except Exception as e:
                print(f"Error fetching VEP: {e}")
        return None

    def fetch_genebe(self, variant):
        """Fetch annotation from Genebe"""
        # https://api.genebe.net/cloud/api-public/v1/variant/{variant}
        # Variant format: chr-pos-ref-alt
        
        if hasattr(variant, 'snv'):
            snv = variant.snv
            variant_str = f"{snv.chromosome}-{snv.start}-{snv.reference}-{snv.alternate}"
            
            url = f"https://api.genebe.net/cloud/api-public/v1/variants/{variant_str}"
            params = {'genome': 'hg38'}
            
            try:
                response = requests.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    self._save_annotation(variant, "genebe", data)
                    return data
            except Exception as e:
                print(f"Error fetching Genebe: {e}")
        return None

    def _save_annotation(self, variant, source, data):
        """Save or update annotation"""
        Annotation.objects.update_or_create(
            variant=variant,
            source=source,
            defaults={
                'data': data,
                'source_version': timezone.now().strftime("%Y-%m-%d"),
                'updated_at': timezone.now()
            }
        )

    def link_genes(self, variant):
        """Link variant to genes based on annotations"""
        from .models import Gene
        
        gene_symbols = set()
        
        # Parse VEP data
        vep_annotations = variant.annotations.filter(source="vep")
        for annotation in vep_annotations:
            data = annotation.data
            if isinstance(data, list):
                for item in data:
                    if "transcript_consequences" in item:
                        for transcript in item["transcript_consequences"]:
                            if "gene_symbol" in transcript:
                                gene_symbols.add(transcript["gene_symbol"])
        
        # Parse MyVariant data
        myvariant_annotations = variant.annotations.filter(source="myvariant")
        for annotation in myvariant_annotations:
            data = annotation.data
            # MyVariant structure varies, check common paths
            # clinvar.gene.symbol
            if "clinvar" in data and "gene" in data["clinvar"]:
                gene_data = data["clinvar"]["gene"]
                if isinstance(gene_data, dict) and "symbol" in gene_data:
                    gene_symbols.add(gene_data["symbol"])
            # cadd.gene.symbol (not always present)
            
        if gene_symbols:
            genes = Gene.objects.filter(symbol__in=gene_symbols)
            variant.genes.add(*genes)
            print(f"Linked genes {gene_symbols} to variant {variant}")

