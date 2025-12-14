from django.core.management.base import BaseCommand
from django.utils import timezone
from lab.models import Individual
from pyhpo import Ontology, HPOSet

class Command(BaseCommand):
    help = 'Counts patients < 18 years old who have Seizure/Epilepsy related HPO terms'

    def handle(self, *args, **options):
        self.stdout.write("Initializing HPO Ontology... (this may take a moment)")
        Ontology()

        # Get the HPO term for "Seizure" (HP:0001250)
        # This is the standard parent term for all seizure/epilepsy phenotypes in HPO.
        try:
            seizure_term = Ontology.get_hpo_object('Seizure')
        except LookupError:
             # Fallback if name lookup fails, though 'Seizure' is standard
            seizure_term = Ontology.hpo(1250)

        self.stdout.write(f"Filtering for phenotype: {seizure_term.name} ({seizure_term.id}) and descendants.")

        # Fetch all individuals with their HPO terms preloaded
        individuals = Individual.objects.prefetch_related('hpo_terms').all()
        
        matching_patients = []
        today = timezone.now().date()

        self.stdout.write("Analyzing patients...")

        for patient in individuals:
            # 1. Check Age (< 18)
            # birth_date is encrypted, so we access it here to let the field decrypt it
            dob = patient.birth_date
            if not dob:
                continue

            # Calculate age accurately accounting for leap years
            age = (today - dob).days / 365.25
            
            if age >= 18:
                continue

            # 2. Check for Epilepsy/Seizure Terms
            # Get patient's HPO terms (filtering for 'HP' ontology type=1)
            patient_term_ids = [
                t.term for t in patient.hpo_terms.all() 
                if t.ontology.type == 1
            ]

            if not patient_term_ids:
                continue

            # Check if any of the patient's terms are "Seizure" or a child of "Seizure"
            has_epilepsy = False
            try:
                # We iterate through patient terms and check lineage
                for term_id in patient_term_ids:
                    try:
                        # Parse term ID (e.g. "HP:0001250" -> 1250) or use query lookup
                        # Using get_hpo_object handles "HP:0001250" string format correctly usually, 
                        # or we strip 'HP:' if needed. PyHPO usually handles the string.
                        term = Ontology.get_hpo_object(term_id)
                        
                        # Check if term is Seizure or a descendant of Seizure
                        if term == seizure_term or term.child_of(seizure_term):
                            has_epilepsy = True
                            break
                    except (ValueError, LookupError):
                        continue
            except Exception as e:
                # Fallback safety
                continue

            if has_epilepsy:
                matching_patients.append({
                    'patient': patient,
                    'age': age,
                    'terms': ", ".join(patient_term_ids)
                })

        # Output Results
        self.stdout.write(self.style.SUCCESS(f"\nFound {len(matching_patients)} patients under 18 with Seizure/Epilepsy phenotypes:\n"))
        
        header = f"{'Patient ID':<40} | {'Age':<5} | {'HPO Terms'}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        for match in matching_patients:
            self.stdout.write(f"{str(match['patient']):<40} | {match['age']:.1f}  | {match['terms']}")
