"""Generate realistic sample data for development and testing.

Prerequisite checkpoints (mirrors import_all.py Step 0 / Step 1):
  0a  Load ontologies_data.json fixture if ontology table is empty
  0b  Import HGNC gene data if Gene table is empty
  0c  Run ozbek_set_id_priorities so IdentifierType priorities are configured
"""

import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from lab.models import (
    Analysis,
    AnalysisType,
    CrossIdentifier,
    Family,
    IdentifierType,
    Individual,
    Institution,
    Note,
    Pipeline,
    PipelineType,
    Project,
    Sample,
    SampleType,
    Status,
    Task,
    Test,
    TestType,
)
from ontologies.models import Ontology, Term
from variant.models import Classification, Gene, SNV

User = get_user_model()


class Command(BaseCommand):
    help = "Generate sample data for testing"

    def add_arguments(self, parser):
        parser.add_argument("--families", type=int, default=15,
                            help="Number of families to create")
        parser.add_argument("--samples-per-individual", type=int, default=1,
                            help="Number of samples per individual")
        parser.add_argument("--tests-per-sample", type=int, default=2,
                            help="Number of tests per sample")
        parser.add_argument("--pipelines-per-test", type=int, default=1,
                            help="Number of pipelines per test")
        parser.add_argument("--analyses-per-pipeline", type=int, default=1,
                            help="Number of analyses per pipeline")
        parser.add_argument("--variants-per-analysis", type=int, default=1,
                            help="Number of variants per analysis")
        parser.add_argument("--tasks-per-object", type=int, default=1,
                            help="Number of tasks per object")
        parser.add_argument("--skip-hgnc", dest="skip_hgnc", action="store_true",
                            help="Skip HGNC gene data download check")

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        # ── Checkpoint 0a: ontologies ──────────────────────────────────
        self._ensure_ontologies()

        # ── Checkpoint 0b: HGNC genes ─────────────────────────────────
        if not options["skip_hgnc"]:
            if not Gene.objects.exists():
                self.stdout.write(self.style.WARNING(
                    "Step 0b: Gene table empty — running import_hgnc_data…"))
                call_command("import_hgnc_data")
            else:
                self.stdout.write("Step 0b: Gene table already populated.")

        # ── Checkpoint 0c: ID priorities ──────────────────────────────
        self.stdout.write("Step 0c: Setting ID priorities…")
        call_command("ozbek_set_id_priorities")

        # ── Users ──────────────────────────────────────────────────────
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            self.stdout.write("Creating default superuser…")
            user = User.objects.create_superuser("admin", "admin@example.com", "admin")
        if not User.objects.filter(username="pleb").exists():
            self.stdout.write("Creating pleb user…")
            User.objects.create_user("pleb", "pleb@example.com", "pleb")
        if not User.objects.filter(username="normal").exists():
            self.stdout.write("Creating normal user…")
            User.objects.create_user("normal", "normal@example.com", "normal")

        # ── Setup ──────────────────────────────────────────────────────
        all_statuses    = self._create_statuses(user)
        sample_types    = self._create_sample_types(user)
        test_types      = self._create_test_types(user)
        pipeline_types  = self._create_pipeline_types(user)
        analysis_types  = self._create_analysis_types(user)
        institution     = self._get_or_create_institution(user)
        project         = self._create_project(user, all_statuses)
        identifier_types = self._create_identifier_types(user)

        hpo_terms = list(Term.objects.filter(ontology__type=1).order_by("?")[:50])
        self.stdout.write(f"HPO terms available: {len(hpo_terms)}")
        if not hpo_terms:
            self.stdout.write(self.style.WARNING(
                "No HPO terms found — run generate_sample_data after loading ontologies."))

        # ── Families ──────────────────────────────────────────────────
        all_individuals = []
        for i in range(options["families"]):
            family_id = self._generate_unique_family_id(i + 1)
            family_date = timezone.now() - timedelta(days=100)
            family = self._create_family(family_id, user)
            self._create_note(family, user)
            self._create_tasks(family, user, all_statuses, project,
                                options["tasks_per_object"], family_date)

            mother_date = family_date + timedelta(days=random.randint(1, 3))
            mother = self._create_individual(
                "Mother", family, user, institution,
                all_statuses["individual"]["registered"],
                hpo_terms, is_index=False, creation_date=mother_date)
            self._create_note(mother, user)
            self._create_identifiers(
                mother, identifier_types, f"{family_id}.2",
                f"RD3.F{i+1:02d}.2", user)

            father_date = family_date + timedelta(days=random.randint(1, 3))
            father = self._create_individual(
                "Father", family, user, institution,
                all_statuses["individual"]["registered"],
                hpo_terms, is_index=False, creation_date=father_date)
            self._create_note(father, user)
            self._create_identifiers(
                father, identifier_types, f"{family_id}.3",
                f"RD3.F{i+1:02d}.3", user)
            all_individuals.extend([mother, father])
            children = []
            if i % 2 == 0:
                for child_num in range(1, 3):
                    child_date = family_date + timedelta(days=random.randint(2, 5))
                    proband = self._create_individual(
                        f"Proband{child_num}", family, user, institution,
                        all_statuses["individual"]["active"],
                        hpo_terms, mother=mother, father=father,
                        is_index=True, creation_date=child_date)
                    self._create_note(proband, user)
                    self._create_identifiers(
                        proband, identifier_types,
                        f"{family_id}.1.{child_num}",
                        f"RD3.F{i+1:02d}.1.{child_num}", user)
                    children.append(proband)
            else:
                child_date = family_date + timedelta(days=random.randint(2, 5))
                proband = self._create_individual(
                    "Proband", family, user, institution,
                    all_statuses["individual"]["active"],
                    hpo_terms, mother=mother, father=father,
                    is_index=True, creation_date=child_date)
                self._create_note(proband, user)
                self._create_identifiers(
                    proband, identifier_types, f"{family_id}.1.1",
                    f"RD3.F{i+1:02d}.1.1", user)
                children.append(proband)
            all_individuals.extend(children)
            for ind in [mother, father] + children:
                base_date = (ind.get_created_at() or timezone.now()) + timedelta(
                    days=random.randint(1, 21))
                self._create_tasks(ind, user, all_statuses, project,
                                    options["tasks_per_object"], base_date)

            for ind in [mother, father] + children:
                self._create_samples(
                    ind, institution, sample_types, test_types, pipeline_types,
                    options["samples_per_individual"],
                    options["tests_per_sample"],
                    options["pipelines_per_test"],
                    options["analyses_per_pipeline"],
                    options["variants_per_analysis"],
                    options["tasks_per_object"],
                    user, all_statuses, project, analysis_types)

        if all_individuals:
            project.individuals.add(*all_individuals)

        self.stdout.write(self.style.SUCCESS("Successfully generated sample data"))

    # ==================================================================
    # Checkpoints
    # ==================================================================

    def _ensure_ontologies(self):
        """Load ontologies_data.json fixture if the Ontology table is empty."""
        if Ontology.objects.exists():
            self.stdout.write("Step 0a: Ontologies already loaded.")
            return
        self.stdout.write(self.style.WARNING(
            "Step 0a: Ontology table empty — loading ontologies_data.json fixture…"))
        call_command("loaddata", "ontologies_data.json")
        loaded = Ontology.objects.count()
        if loaded:
            self.stdout.write(self.style.SUCCESS(
                f"Step 0a: Loaded {loaded} ontologies."))
        else:
            self.stdout.write(self.style.WARNING(
                "Step 0a: Fixture loaded but no Ontology objects found. "
                "Check that ontologies_data.json is in a fixtures/ directory."))

    # ==================================================================
    # Setup helpers
    # ==================================================================

    def _create_statuses(self, user):
        """Create a status set per model type, returned as a nested dict."""
        all_statuses = {}
        status_data = {
            "registered": ("Registered", "gray",   "fa-user-plus"),
            "active":     ("Active",     "green",  "fa-play"),
            "completed":  ("Completed",  "blue",   "fa-check-circle"),
            "cancelled":  ("Cancelled",  "red",    "fa-times-circle"),
            "pending":    ("Pending",    "yellow", "fa-clock"),
        }
        from lab.models import Analysis as _Analysis, Sample as _Sample, Test as _Test
        from lab.models import Pipeline as _Pipeline, Task as _Task
        for model_type in [Individual, _Sample, _Test, _Pipeline, _Task, _Analysis]:
            ct = ContentType.objects.get_for_model(model_type)
            model_statuses = {}
            for key, (name, color, icon) in status_data.items():
                st, _ = Status.objects.get_or_create(
                    name=name, content_type=ct,
                    defaults={"color": color, "icon": icon, "created_by": user})
                if not st.icon:
                    st.icon = icon; st.save()
                model_statuses[key] = st
            all_statuses[model_type.__name__.lower()] = model_statuses
        return all_statuses

    def _create_sample_types(self, user):
        types = ["DNA", "RNA", "Plasma", "Serum", "Whole Blood"]
        return {t.lower().replace(" ", "_"):
                SampleType.objects.get_or_create(name=t, defaults={"created_by": user})[0]
                for t in types}

    def _create_test_types(self, user):
        types = ["WGS", "WES", "Panel"]
        return {t.lower():
                TestType.objects.get_or_create(name=t, defaults={"created_by": user})[0]
                for t in types}

    def _create_pipeline_types(self, user):
        types = ["Bioinformatics", "Interpretation", "Validation"]
        return {t.lower():
                PipelineType.objects.get_or_create(name=t, defaults={"created_by": user})[0]
                for t in types}

    def _create_analysis_types(self, user):
        types = ["Initial", "Reanalysis"]
        return {t.lower():
                AnalysisType.objects.get_or_create(
                    name=t,
                    defaults={"description": f"{t} clinical interpretation",
                               "created_by": user})[0]
                for t in types}

    def _get_or_create_institution(self, user):
        inst, _ = Institution.objects.get_or_create(
            name="Rare Disease Lab",
            defaults={
                "created_by": user,
                "city": "Ankara",
                "center_name": "Genetics Center",
                "speciality": "Medical Genetics",
            })
        return inst

    def _create_project(self, user, all_statuses):
        proj, created = Project.objects.get_or_create(
            name="Rare Disease Pilot",
            defaults={
                "description": "Pilot project for rare disease analysis",
                "created_by": user,
            })
        if created:
            ct = ContentType.objects.get_for_model(Project)
            p_status, _ = Status.objects.get_or_create(
                name="Ongoing", content_type=ct,
                defaults={"color": "purple", "created_by": user})
            proj.statuses.set([p_status])
        return proj

    def _create_identifier_types(self, user):
        config = [
            ("RareBoost", "RareBoost", 1, True),
            ("Biobank",   "Biobank",   2, True),
            ("ERDERA",    "ERDERA",    3, False),
        ]
        result = {}
        for name, description, priority, show_in_table in config:
            id_type, _ = IdentifierType.objects.get_or_create(
                name=name,
                defaults={"description": description, "created_by": user,
                           "use_priority": priority, "is_shown_in_table": show_in_table})
            changed = False
            if id_type.use_priority != priority:
                id_type.use_priority = priority; changed = True
            if id_type.is_shown_in_table != show_in_table:
                id_type.is_shown_in_table = show_in_table; changed = True
            if not id_type.description:
                id_type.description = description; changed = True
            if changed:
                id_type.save()
            result[name.lower()] = id_type
        return result

    # ==================================================================
    # Individual helpers
    # ==================================================================

    def _generate_unique_family_id(self, family_number):
        base_id = f"RB_2025_{family_number:02d}"
        counter = 0
        family_id = base_id
        while Family.objects.filter(family_id=family_id).exists():
            counter += 1
            family_id = f"{base_id}_{counter}"
        return family_id

    def _generate_unique_erdera_id(self):
        erdera_type = IdentifierType.objects.filter(name="ERDERA").first()
        if not erdera_type:
            return str(random.randint(1000000000, 9999999999))
        for _ in range(100):
            erdera_id = str(random.randint(1000000000, 9999999999))
            if not CrossIdentifier.objects.filter(
                    id_type=erdera_type, id_value=erdera_id).exists():
                return erdera_id
        return str(random.randint(1000000000, 9999999999))

    def _create_family(self, family_id, user):
        return Family.objects.create(family_id=family_id, created_by=user)

    def _create_individual(self, first_name, family, user, institution, status,
                            hpo_terms, mother=None, father=None,
                            is_index=False, creation_date=None):
        ind = Individual.objects.create(
            full_name=f"{first_name} {family.family_id}",
            family=family,
            mother=mother,
            father=father,
            is_index=is_index,
            sex=random.choice(["male", "female"]),
            birth_date=(creation_date or timezone.now()).date() - timedelta(
                days=random.randint(365 * 5, 365 * 50)),
            created_by=user,
            created_at=creation_date or timezone.now(),
        )
        # statuses is a TaggableManager — must be set AFTER save
        if status:
            ind.statuses.set([status])
        ind.institution.add(institution)
        if hpo_terms:
            ind.hpo_terms.add(*random.sample(hpo_terms, min(random.randint(1, 5), len(hpo_terms))))
        return ind

    def _create_identifiers(self, individual, identifier_types, lab_id, biobank_id, user):
        rareboost_type = identifier_types.get("rareboost")
        biobank_type   = identifier_types.get("biobank")
        erdera_type    = identifier_types.get("erdera")

        if rareboost_type and not CrossIdentifier.objects.filter(
                id_type=rareboost_type, id_value=lab_id).exists():
            if not CrossIdentifier.objects.filter(
                    individual=individual, id_type=rareboost_type).exists():
                CrossIdentifier.objects.create(
                    individual=individual, id_type=rareboost_type,
                    id_value=lab_id,
                    link=f"https://www.rareboost.com/individual/{lab_id}",
                    created_by=user)

        if biobank_type and not CrossIdentifier.objects.filter(
                id_type=biobank_type, id_value=biobank_id).exists():
            if not CrossIdentifier.objects.filter(
                    individual=individual, id_type=biobank_type).exists():
                CrossIdentifier.objects.create(
                    individual=individual, id_type=biobank_type,
                    id_value=biobank_id,
                    link=f"https://www.biobank.com/individual/{biobank_id}",
                    created_by=user)

        if erdera_type and not CrossIdentifier.objects.filter(
                individual=individual, id_type=erdera_type).exists():
            CrossIdentifier.objects.create(
                individual=individual, id_type=erdera_type,
                id_value=self._generate_unique_erdera_id(),
                link=f"https://www.erdera.com/individual/",
                created_by=user)

    # ==================================================================
    # Note / Task helpers
    # ==================================================================

    def _create_note(self, obj, user, text=None):
        Note.objects.create(
            content_object=obj,
            content=text or f"Auto-generated note for {obj}",
            user=user)

    def _create_tasks(self, obj, user, all_statuses, project, num_tasks, base_date):
        if not hasattr(base_date, "date"):
            base_date = timezone.datetime.combine(
                base_date, timezone.datetime.min.time()
            ).replace(tzinfo=timezone.get_current_timezone())

        # Assign a random subset (1–5) of available task statuses
        task_statuses = list(all_statuses.get("task", {}).values())

        for i in range(num_tasks):
            task = Task.objects.create(
                title=f"Task {i+1} for {obj}",
                description="Auto-generated task",
                content_object=obj,
                project=project,
                priority=random.choice(["low", "medium", "high"]),
                assigned_to=user,
                created_by=user,
                due_date=base_date + timedelta(days=random.randint(1, 30)),
            )

            if task_statuses:
                max_count = min(5, len(task_statuses))
                count = random.randint(1, max_count)
                selected_statuses = random.sample(task_statuses, count)
                task.statuses.set(selected_statuses)

    # ==================================================================
    # Sample / Test / Pipeline / Analysis / Variant chain
    # ==================================================================

    def _create_samples(
        self, individual, institution, sample_types, test_types, pipeline_types,
        num_samples, tests_per_sample, pipelines_per_test, analyses_per_pipeline,
        variants_per_analysis, tasks_per_object, user, all_statuses, project,
        analysis_types,
    ):
        active_sample  = all_statuses["sample"].get("active")
        active_test    = all_statuses["test"].get("active")
        active_pipeline = all_statuses["pipeline"].get("active")

        for _ in range(num_samples):
            sample_type = random.choice(list(sample_types.values()))
            receipt_date = (timezone.now() - timedelta(days=random.randint(10, 100))).date()

            sample = Sample.objects.create(
                individual=individual,
                sample_type=sample_type,
                receipt_date=receipt_date,
                isolation_by=user,
                created_by=user,
            )
            if active_sample:
                sample.statuses.set([active_sample])
            self._create_tasks(sample, user, all_statuses, project,
                                tasks_per_object, receipt_date)

            for _ in range(tests_per_sample):
                test_type    = random.choice(list(test_types.values()))
                performed_date = receipt_date + timedelta(days=random.randint(1, 10))

                # Test.performed_by is now FK → Institution (nullable)
                test = Test.objects.create(
                    sample=sample,
                    test_type=test_type,
                    performed_date=performed_date,
                    performed_by=institution,     # Institution FK
                    created_by=user,
                )
                if active_test:
                    test.statuses.set([active_test])
                self._create_tasks(test, user, all_statuses, project,
                                    tasks_per_object, performed_date)

                for _ in range(pipelines_per_test):
                    pipeline_type  = random.choice(list(pipeline_types.values()))
                    pipeline_date  = performed_date + timedelta(days=random.randint(1, 5))

                    pipeline = Pipeline.objects.create(
                        test=test,
                        type=pipeline_type,
                        performed_date=pipeline_date,
                        performed_by=user,        # Pipeline.performed_by is still FK → User
                        created_by=user,
                    )
                    if active_pipeline:
                        pipeline.statuses.set([active_pipeline])
                    self._create_tasks(pipeline, user, all_statuses, project,
                                        tasks_per_object, pipeline_date)

                    self._create_analyses(
                        individual=individual,
                        pipeline=pipeline,
                        analysis_types=analysis_types,
                        analyses_per_pipeline=analyses_per_pipeline,
                        variants_per_analysis=variants_per_analysis,
                        tasks_per_object=tasks_per_object,
                        user=user,
                        all_statuses=all_statuses,
                        project=project,
                    )

    def _create_analyses(
        self, individual, pipeline, analysis_types, analyses_per_pipeline,
        variants_per_analysis, tasks_per_object, user, all_statuses, project,
    ):
        if analyses_per_pipeline <= 0:
            return
        active_analysis = all_statuses["analysis"].get("active")
        types = list(analysis_types.values()) if analysis_types else []

        for _ in range(analyses_per_pipeline):
            analysis_type  = random.choice(types) if types else None
            performed_date = pipeline.performed_date + timedelta(days=random.randint(1, 10))

            # Analysis.performed_by is now M2M — cannot be passed to create()
            analysis = Analysis.objects.create(
                pipeline=pipeline,
                type=analysis_type,
                performed_date=performed_date,
                created_by=user,
            )
            analysis.performed_by.add(user)    # M2M — set after creation
            if active_analysis:
                analysis.statuses.set([active_analysis])

            self._create_tasks(analysis, user, all_statuses, project,
                                tasks_per_object, performed_date)

            self._create_variants(
                individual=individual,
                analysis=analysis,          # pass analysis, not pipeline
                user=user,
                all_statuses=all_statuses,
                variants_per_analysis=variants_per_analysis,
            )

    def _create_variants(
        self, individual, analysis, user, all_statuses, variants_per_analysis,
    ):
        if variants_per_analysis <= 0:
            return

        specific_variants = [
            "chr10-77984023 A>G",    "chr10-77982811 C>T",
            "chr10-78009515 C>T",    "chr7-94053779 C>T",
            "chr1-241959054 CAA>C",  "chrX-41437781 C>CCTAG",
            "chr1-6825194 G>T",      "chr7-73683072 C>A",
            "chr20-22584278 T>C",    "chr13-35645867 A>T",
            "chr4-84794563 C>T",     "chr15-45152472 T>A",
            "chrX-155898245 AG>C",   "chr8-96785174 CAA>C",
            "chr9-841776 C>G",       "chr1-36091267 A>C",
            "chr20-50892050 TTCA>T", "chrX-120560586 T>C",
        ]
        selected = (random.sample(specific_variants, variants_per_analysis)
                    if variants_per_analysis <= len(specific_variants)
                    else [random.choice(specific_variants)
                          for _ in range(variants_per_analysis)])

        for variant_str in selected:
            loc_part, alleles_part = variant_str.split(" ")
            chrom_part, pos_part   = loc_part.split("-")
            ref, alt               = alleles_part.split(">")
            chrom = chrom_part        # keep "chr" prefix — Variant.save normalises
            start = int(pos_part)

            # Variant.analysis replaces the old Variant.pipeline FK
            snv = SNV.objects.create(
                individual=individual,
                analysis=analysis,
                chromosome=chrom,
                start=start,
                end=start,
                zygosity=random.choice(["het", "hom", "het", "het"]),
                reference=ref,
                alternate=alt,
                created_by=user,
            )

            Classification.objects.create(
                variant=snv,
                user=user,
                classification=random.choice([
                    "pathogenic", "likely_pathogenic", "vus",
                    "likely_benign", "benign"]),
                inheritance=random.choice(["ad", "ar", "de_novo", "unknown"]),
                notes="Auto-generated classification",
            )
