from django.core.management.base import BaseCommand
from lab.models import Individual
from pyhpo import Ontology, HPOSet
from django.utils import timezone

class Command(BaseCommand):
    help = 'Identifies patients with phenotypes similar to Developmental Epileptic Encephalopathies (DEE)'

    def handle(self, *args, **options):
        self.stdout.write("Initializing HPO Ontology... (this may take a moment)")
        # Initialize the Ontology (loads data into memory)
        Ontology()
        today = timezone.now().date()

        # 1. Identify all DEE diseases in the ontology
        # We look for diseases with "developmental and epileptic encephalopathy" in their name.
        dee_diseases = [
            dis for dis in Ontology.omim_diseases
            if "developmental and epileptic encephalopathy" in dis.name.lower()
            or "epileptic encephalopathy" in dis.name.lower()
        ]
        
        if not dee_diseases:
            self.stdout.write(self.style.WARNING("No specific DEE diseases found. Checking for generic 'Epileptic Encephalopathy'..."))
            dee_diseases = [d for d in Ontology.omim_diseases if "epileptic encephalopathy" in d.name.lower()]

        self.stdout.write(f"Found {len(dee_diseases)} DEE-related disease profiles for comparison.")

        # 2. Fetch Patients and build HPO Sets
        individuals = Individual.objects.prefetch_related('hpo_terms').all()
        results = []

        self.stdout.write("Analyzing patients...")
        
        for patient in individuals:
            # Get HPO term objects for the patient (filtering for 'HP' ontology type=1)
            patient_term_objs = [
                t for t in patient.hpo_terms.all() 
                if t.ontology.type == 1
            ]
            
            # Extract IDs for calculation (e.g., "HP:0001234")
            patient_term_ids = [t.term for t in patient_term_objs]

            if not patient_term_ids:
                continue

            # Create a display string of terms (e.g., "HP:0001234, HP:0002345")
            terms_display = ", ".join([f"{t.term} {t.label}" for t in patient_term_objs])

            # Create an HPOSet for the patient
            patient_hpo_set = HPOSet.from_queries(patient_term_ids)

            # 3. Calculate Similarity
            # We calculate similarity to all DEE diseases and find the single best match for this patient.
            best_score = 0.0
            best_match_disease = None

            for disease in dee_diseases:
                try:
                    score = patient_hpo_set.similarity(disease.hpo_set())
                    if score > best_score:
                        best_score = score
                        best_match_disease = disease
                except Exception:
                    continue


            # Update header to include Patient HPO Terms
            dob = patient.birth_date
            if dob:
                age = (today - dob).days / 365.25
            else:
                dob = "None"
                age = "None"

            if best_match_disease:
                results.append({
                    'patient': patient,
                    'dob': dob,
                    'age': age,
                    'score': best_score,
                    'matched_disease': best_match_disease,
                    'hpo_count': len(patient_term_ids),
                    'terms': terms_display  # <--- Added terms to result set
                })

        # 4. Sort and Display Results
        # Sort by score descending
        results.sort(key=lambda x: x['score'], reverse=True)

        self.stdout.write(self.style.SUCCESS(f"\nTop Candidates for Developmental Epileptic Encephalopathy:\n"))
        
        header = f"{'Score'}\t{'Patient ID'}\tDOB\tAge\t{'Matched DEE Variant'}\t{'Count'}\t{'Patient HPO Terms'}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        # Show top 20
        for res in results:
            patient_str = str(res['patient'])
            # Print row with terms at the end
            if res['age'] != "None":
                self.stdout.write(f"{res['score']:0.2f}\t{patient_str}\t{res['patient'].sex}\t{res['dob']}\t{res['age']:0.2f}\t{res['matched_disease']}\t{res['hpo_count']}\t{res['terms']}")
            else:
                self.stdout.write(f"{res['score']:0.2f}\t{patient_str}\t{res['patient'].sex}\t{res['dob']}\tNone\t{res['matched_disease']}\t{res['hpo_count']}\t{res['terms']}")
