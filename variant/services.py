import requests
import json
from django.utils import timezone
from django.db.models import Count, Q
from .models import Annotation
from lab.models import Pipeline, Status

class DiagnosticService:
    """Service to calculate diagnostic yield and pipeline statistics"""

    def get_diagnostic_yield(self, pipeline_type=None):
        """
        Calculate diagnostic yield: Solved Pipelines / Total Pipelines
        Returns a dict with counts and percentage.
        """
        queryset = Pipeline.objects.all()
        if pipeline_type:
            queryset = queryset.filter(type=pipeline_type)
            
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
        """Return variants linked to solved pipelines"""
        solved_statuses = ["Solved - P/LP", "Solved - VUS"]
        return Pipeline.objects.filter(status__name__in=solved_statuses).values_list('found_variants', flat=True)


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
        # GET request for region
        # https://rest.ensembl.org/vep/human/region/:region/:allele?
        
        base_url = "https://rest.ensembl.org/vep/human/region"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        
        region_str = ""
        
        # Helper to strip 'chr' prefix if present, as Ensembl expects just the number/letter
        chrom = variant.chromosome.replace("chr", "")
        
        if hasattr(variant, 'snv'):
            snv = variant.snv
            # Check for insertion (start > end)
            if snv.start > snv.end:
                # Insertion: 9:22125503-22125502:1/C
                # Format: {chr}:{start}-{end}:1/{alt}
                region_str = f"{chrom}:{snv.start}-{snv.end}:1/{snv.alternate}"
            else:
                # SNV: 1:6524705:6524705/T
                # Format: {chr}:{start}:{end}/{alt}
                region_str = f"{chrom}:{snv.start}:{snv.end}/{snv.alternate}"
                
        elif hasattr(variant, 'sv'):
            sv = variant.sv
            # SV: 7:100318423-100321323:1/DUP
            # Map types
            type_map = {
                "deletion": "DEL",
                "duplication": "DUP",
                "insertion": "INS", 
                "inversion": "INV",
            }
            vep_type = type_map.get(sv.sv_type, sv.sv_type.upper())
            # Format: {chr}:{start}-{end}:1/{type}
            region_str = f"{chrom}:{sv.start}-{sv.end}:1/{vep_type}"
            
        if not region_str:
            return None
            
        url = f"{base_url}/{region_str}"
        params = {"hgvs": 1}
        
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                self._save_annotation(variant, "vep", data)
                return data
            else:
                print(f"VEP Error: {response.status_code} {response.text}")
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

