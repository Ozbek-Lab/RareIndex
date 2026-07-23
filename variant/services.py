import requests
import json
from django.utils import timezone
from django.db.models import Count, Q
from .models import Annotation, ACMGEvidenceOverride, CNV, SNV, SV, delins
from lab.models import Pipeline, Status, Individual

class DiagnosticService:
    """Service to calculate diagnostic yield and analysis statistics"""

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
            
        solved_count = queryset.filter(
            test__sample__individual__statuses__name__iexact="Solved"
        ).distinct().count()
        
        return {
            "total": total,
            "solved": solved_count,
            "yield_percentage": round((solved_count / total) * 100, 2)
        }

    def get_variants_leading_to_diagnosis(self):
        """Return variants linked to solved individuals."""
        from variant.models import Variant
        solved_individuals = Individual.objects.filter(statuses__name__iexact="Solved").distinct()
        return Variant.objects.filter(individual__in=solved_individuals).values_list("id", flat=True).distinct()


class AnnotationService:
    """Service to handle external annotation APIs"""
    
    def fetch_myvariant_info(self, variant):
        """Fetch annotation from MyVariant.info"""
        # Construct HGVS ID or similar
        # For SNV: chr1:g.123A>G
        # Assuming hg38
        snv = None
        if isinstance(variant, (SNV, delins)):
            snv = variant
        elif hasattr(variant, 'snv'):
            snv = variant.snv
        if snv is None:
            return None # MyVariant mostly for SNVs/indels
        
        chrom = snv.chromosome.replace("chr", "")
        hgvs_id = f"chr{chrom}:g.{snv.start}{snv.reference}>{snv.alternate}"
        
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
        
        if isinstance(variant, (SNV, delins)) or hasattr(variant, 'snv'):
            snv = variant if isinstance(variant, (SNV, delins)) else variant.snv
            # Check for insertion (start > end)
            if snv.start > snv.end:
                # Insertion: 9:22125503-22125502:1/C
                # Format: {chr}:{start}-{end}:1/{alt}
                region_str = f"{chrom}:{snv.start}-{snv.end}:1/{snv.alternate}"
            else:
                # SNV: 1:6524705:6524705/T
                # Format: {chr}:{start}:{end}/{alt}
                region_str = f"{chrom}:{snv.start}:{snv.end}/{snv.alternate}"
                
        elif isinstance(variant, SV) or hasattr(variant, 'sv'):
            sv = variant if isinstance(variant, SV) else variant.sv
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

        elif isinstance(variant, CNV) or hasattr(variant, 'cnv'):
            cnv = variant if isinstance(variant, CNV) else variant.cnv
            type_map = {
                "loss": "DEL",
                "gain": "DUP",
            }
            vep_type = type_map.get(cnv.cnv_type)
            if vep_type:
                # CNVs use the same Ensembl region notation as structural deletions/duplications.
                region_str = f"{chrom}:{cnv.start}-{cnv.end}:1/{vep_type}"
            
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
        """Fetch annotation from GeneBe."""
        snv = getattr(variant, "snv", None)
        if snv is None and hasattr(variant, "reference") and hasattr(variant, "alternate"):
            snv = variant

        if snv is None:
            return None

        ref = getattr(snv, "reference", None)
        alt = getattr(snv, "alternate", None)
        pos = getattr(snv, "start", None)
        chrom = getattr(snv, "chromosome", None)

        if not all([chrom, pos, ref, alt]):
            return None

        chrom = str(chrom).removeprefix("chr")
        url = "https://api.genebe.net/cloud/api-public/v1/variant"
        params = {
            "chr": chrom,
            "pos": pos,
            "ref": ref,
            "alt": alt,
            "genome": "hg38",
        }

        try:
            response = requests.get(
                url,
                params=params,
                headers={"Accept": "application/json"},
                timeout=20,
            )
            if response.status_code == 200:
                data = response.json()
                self._save_annotation(variant, "genebe", data)
                self._sync_genebe_evidence(variant, data)
                return data
            print(f"GeneBe Error: {response.status_code} {response.text}")
        except Exception as e:
            print(f"Error fetching GeneBe: {e}")
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

    def _sync_genebe_evidence(self, variant, data):
        """Store normalized GeneBe criteria rows for later manual overrides."""
        from .templatetags.variant_filters import parse_acmg_criteria

        if not isinstance(data, dict):
            return

        variant_items = data.get("variants") if isinstance(data.get("variants"), list) else []
        if not variant_items and data:
            variant_items = [data]

        evidence_rows = []
        seen = set()

        def add_criteria(raw_value, gene_symbol="", transcript=""):
            gene_symbol = (gene_symbol or "").strip()
            transcript = (transcript or "").strip()
            for item in parse_acmg_criteria(raw_value):
                code = item.get("code")
                key = (gene_symbol, transcript, code)
                if code and key not in seen:
                    seen.add(key)
                    evidence_rows.append((gene_symbol, transcript, code, item.get("strength", "")))

        for item in variant_items:
            if not isinstance(item, dict):
                continue
            add_criteria(item.get("acmg_criteria"))
            for gene_record in item.get("acmg_by_gene", []) or []:
                if isinstance(gene_record, dict):
                    add_criteria(
                        gene_record.get("criteria"),
                        gene_record.get("gene_symbol"),
                        gene_record.get("transcript"),
                    )

        current_qs = ACMGEvidenceOverride.objects.filter(variant=variant, source="genebe")
        for record in current_qs:
            key = (
                (record.gene_symbol or "").strip(),
                (record.transcript or "").strip(),
                (record.criterion or "").strip().replace(" ", "_").upper(),
            )
            if key not in seen:
                record.delete()

        for gene_symbol, transcript, code, strength in evidence_rows:
            ACMGEvidenceOverride.objects.update_or_create(
                variant=variant,
                gene_symbol=gene_symbol,
                transcript=transcript,
                criterion=code,
                source="genebe",
                defaults={
                    "included": True,
                    "strength": strength,
                    "note": "",
                },
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

        # Parse GeneBe data
        genebe_annotations = variant.annotations.filter(source="genebe")
        for annotation in genebe_annotations:
            data = annotation.data if isinstance(annotation.data, dict) else {}
            variant_items = data.get("variants") if isinstance(data.get("variants"), list) else []
            if not variant_items and data:
                variant_items = [data]

            for item in variant_items:
                if not isinstance(item, dict):
                    continue
                gene_symbol = item.get("gene_symbol")
                if gene_symbol:
                    gene_symbols.add(gene_symbol)
                for gene_record in item.get("acmg_by_gene", []) or []:
                    if isinstance(gene_record, dict) and gene_record.get("gene_symbol"):
                        gene_symbols.add(gene_record["gene_symbol"])
                for consequence in item.get("consequences", []) or []:
                    if isinstance(consequence, dict) and consequence.get("gene_symbol"):
                        gene_symbols.add(consequence["gene_symbol"])

        if gene_symbols:
            genes = Gene.objects.filter(symbol__in=gene_symbols)
            variant.genes.add(*genes)
            print(f"Linked genes {gene_symbols} to variant {variant}")
