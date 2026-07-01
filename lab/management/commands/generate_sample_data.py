"""Generate realistic sample data for development and testing.

Prerequisite checkpoints (mirrors import_all.py Step 0 / Step 1):
  0a  Load ontologies_data.json fixture if ontology table is empty
  0b  Import HGNC gene data if Gene table is empty
  0c  Run ozbek_set_id_priorities so IdentifierType priorities are configured
  0d  Ensure published plot templates are seeded for gallery/dashboard use
"""

import random
import re
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from lab.models import (
    Analysis,
    AnalysisType,
    AnalysisReport,
    CrossIdentifier,
    Family,
    IdentifierType,
    Individual,
    Institution,
    Note,
    Pipeline,
    PipelineType,
    Project,
    PlotTemplate,
    Sample,
    SampleType,
    Status,
    StatusGroup,
    TaggedStatus,
    Task,
    Test,
    TestType,
)
from lab.management.commands._import_helpers import (
    get_or_create_contact_for_user,
    get_or_create_status,
    get_or_create_status_group,
    identifier_type_example_for_name,
)
from ontologies.models import Ontology, Term
from variant.models import Classification, Gene, SNV, Variant

User = get_user_model()

REQUIRED_PLOT_TEMPLATE_SPECS = {
    "sample-distribution-sunburst": {
        "default_col_span": 1,
        "show_download_menu": False,
    },
    "custom-sunburst": {
        "default_col_span": 2,
        "show_download_menu": False,
    },
    "analysis-status-bar": {
        "default_col_span": 1,
        "show_download_menu": False,
    },
    "hpo-term-network": {
        "default_col_span": 2,
        "show_download_menu": False,
    },
}

REQUIRED_PLOT_TEMPLATE_SLUGS = set(REQUIRED_PLOT_TEMPLATE_SPECS)


def _parse_report_text_field_reference_markdown(md_text: str) -> dict[str, dict[str, str]]:
    """
    Parse `report_text_field_reference.md` into:
      { "WES": { "positive_report_template": "...", ... }, ... }
    """
    lines = md_text.splitlines()
    parsed: dict[str, dict[str, str]] = {}
    current_test: str | None = None

    key_re = re.compile(r'^`(?P<key>[a-zA-Z0-9_]+)`\s*$')
    section_re = re.compile(r'^##\s+(?P<name>.+)\s*$')
    inline_value_re = re.compile(r'^`(?P<val>[^`]*)`\s*$')

    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")

        sec_m = section_re.match(line)
        if sec_m:
            current_test = sec_m.group("name").strip()
            parsed.setdefault(current_test, {})
            i += 1
            continue

        if current_test is None:
            i += 1
            continue

        key_m = key_re.match(line.strip())
        if not key_m:
            i += 1
            continue

        field_name = key_m.group("key")

        # Find next non-empty line for the value.
        j = i + 1
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        if j >= len(lines):
            raise RuntimeError(f"Unexpected EOF while reading value for {current_test}.{field_name}")

        val_line = lines[j].strip()
        if val_line.startswith("```"):
            j += 1
            content: list[str] = []
            while j < len(lines):
                if lines[j].strip().startswith("```"):
                    break
                content.append(lines[j])
                j += 1
            else:
                raise RuntimeError(f"Missing closing fence for {current_test}.{field_name}")

            value = "\n".join(content).strip("\n")
            parsed[current_test][field_name] = value
            i = j + 1
            continue

        in_m = inline_value_re.match(val_line)
        if in_m:
            parsed[current_test][field_name] = in_m.group("val")
            i = j + 1
            continue

        # Fallback: take raw line.
        parsed[current_test][field_name] = val_line
        i = j + 1

    return parsed


def _normalize_testtype_report_payload(payload: dict[str, str]) -> dict[str, str]:
    normalized = dict(payload)

    fallback_pairs = (
        ("default_method_text", ("positive_method_text", "negative_method_text")),
        ("default_filtering_text", ("positive_filtering_text", "negative_filtering_text")),
        ("default_limitations_text", ("positive_limitations_text", "negative_limitations_text")),
    )
    for target, candidates in fallback_pairs:
        if normalized.get(target):
            continue
        for candidate in candidates:
            candidate_value = normalized.get(candidate)
            if candidate_value:
                normalized[target] = candidate_value
                break

    return normalized


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
        contact = get_or_create_contact_for_user(user, user)
        if not User.objects.filter(username="pleb").exists():
            self.stdout.write("Creating pleb user…")
            User.objects.create_user("pleb", "pleb@example.com", "pleb")
        if not User.objects.filter(username="normal").exists():
            self.stdout.write("Creating normal user…")
            User.objects.create_user("normal", "normal@example.com", "normal")

        # ── Checkpoint 0d: Plot templates ───────────────────────────
        self._ensure_plot_templates()

        # ── Setup ──────────────────────────────────────────────────────
        all_statuses    = self._create_statuses(user)
        sample_types    = self._create_sample_types(user)
        test_types      = self._create_test_types(user)
        pipeline_types  = self._create_pipeline_types(user)
        analysis_types  = self._create_analysis_types(user)
        institutions    = self._get_or_create_institutions(user)
        projects        = self._create_projects(user, all_statuses)
        identifier_types = self._create_identifier_types(user)

        hpo_terms = list(Term.objects.filter(ontology__type=1).order_by("?")[:50])
        self.stdout.write(f"HPO terms available: {len(hpo_terms)}")
        if not hpo_terms:
            self.stdout.write(self.style.WARNING(
                "No HPO terms found — run generate_sample_data after loading ontologies."))

        # ── Families ──────────────────────────────────────────────────
        for i in range(options["families"]):
            family_id = self._generate_unique_family_id(i + 1)
            family_number = self._family_number_from_family_id(family_id)
            institution = institutions[i % len(institutions)]
            project = projects[i % len(projects)]
            family_date = timezone.now() - timedelta(days=100)
            family = self._create_family(family_id, user)
            self._create_note(family, user)
            self._create_tasks(family, user, all_statuses, project,
                                options["tasks_per_object"], family_date)

            mother_date = family_date + timedelta(days=random.randint(1, 3))
            mother = self._create_individual(
                "Mother", family, user, institution,
                self._individual_statuses(all_statuses, family_number, 0),
                hpo_terms, is_index=False, creation_date=mother_date)
            self._create_note(mother, user)
            self._create_identifiers(
                mother, identifier_types, f"{family_id}.2",
                f"RD3.F{family_number:02d}.2", user)

            father_date = family_date + timedelta(days=random.randint(1, 3))
            father = self._create_individual(
                "Father", family, user, institution,
                self._individual_statuses(all_statuses, family_number, 1),
                hpo_terms, is_index=False, creation_date=father_date)
            self._create_note(father, user)
            self._create_identifiers(
                father, identifier_types, f"{family_id}.3",
                f"RD3.F{family_number:02d}.3", user)
            children = []
            if i % 2 == 0:
                for child_num in range(1, 3):
                    child_date = family_date + timedelta(days=random.randint(2, 5))
                    proband = self._create_individual(
                        f"Proband{child_num}", family, user, institution,
                        self._individual_statuses(all_statuses, family_number, child_num + 1),
                        hpo_terms, mother=mother, father=father,
                        is_index=True, creation_date=child_date)
                    self._create_note(proband, user)
                    self._create_identifiers(
                        proband, identifier_types,
                        f"{family_id}.1.{child_num}",
                        f"RD3.F{family_number:02d}.1.{child_num}", user)
                    children.append(proband)
            else:
                child_date = family_date + timedelta(days=random.randint(2, 5))
                proband = self._create_individual(
                    "Proband", family, user, institution,
                    self._individual_statuses(all_statuses, family_number, 2),
                    hpo_terms, mother=mother, father=father,
                    is_index=True, creation_date=child_date)
                self._create_note(proband, user)
                self._create_identifiers(
                    proband, identifier_types, f"{family_id}.1.1",
                    f"RD3.F{family_number:02d}.1.1", user)
                children.append(proband)
            family_individuals = [mother, father] + children
            project.individuals.add(*family_individuals)
            for ind in family_individuals:
                base_date = (ind.get_created_at() or timezone.now()) + timedelta(
                    days=random.randint(1, 21))
                self._create_tasks(ind, user, all_statuses, project,
                                    options["tasks_per_object"], base_date)

            for ind in family_individuals:
                self._create_samples(
                    ind, contact, institution, sample_types, test_types, pipeline_types,
                    options["samples_per_individual"],
                    options["tests_per_sample"],
                    options["pipelines_per_test"],
                    options["analyses_per_pipeline"],
                    options["variants_per_analysis"],
                    options["tasks_per_object"],
                    user, all_statuses, project, analysis_types)

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

    def _ensure_plot_templates(self):
        """Ensure the published Marimo-backed plot templates are seeded."""
        existing_templates = {
            slug: {
                "default_col_span": default_col_span,
                "show_download_menu": show_download_menu,
            }
            for slug, default_col_span, show_download_menu in PlotTemplate.objects.filter(
                slug__in=REQUIRED_PLOT_TEMPLATE_SLUGS,
                is_published=True,
            ).values_list("slug", "default_col_span", "show_download_menu")
        }
        missing_slugs = sorted(REQUIRED_PLOT_TEMPLATE_SLUGS - set(existing_templates))
        mismatched_specs = sorted(
            slug
            for slug, spec in REQUIRED_PLOT_TEMPLATE_SPECS.items()
            if any(existing_templates.get(slug, {}).get(field) != value for field, value in spec.items())
        )

        if not missing_slugs and not mismatched_specs:
            self.stdout.write("Step 0d: Plot templates already seeded.")
            return

        self.stdout.write(
            self.style.WARNING(
                f"Step 0d: Plot templates need seeding (missing={missing_slugs}, spec_mismatch={mismatched_specs}) — seeding defaults…"
            )
        )
        call_command("seed_plot_templates")

    # ==================================================================
    # Setup helpers
    # ==================================================================

    def _create_statuses(self, user):
        """Create a status set per model type, returned as a nested dict."""
        def ct_for(model):
            return ContentType.objects.get_for_model(model)

        def group_for(model, group_name):
            return get_or_create_status_group(group_name, ct_for(model)) if group_name else None

        def s(model, name, color, icon, short_name="", group_name=None, connected_models=()):
            connected_classes = [ct_for(m) for m in connected_models]
            return get_or_create_status(
                name,
                "",
                color,
                user,
                ct_for(model),
                icon,
                short_name=short_name,
                group=group_for(model, group_name),
                connected_classes=connected_classes or None,
            )

        all_statuses = {
            "individual": {
                "active": s(Individual, "Active", "green", "fa-user-check", short_name="Act", group_name="Activity"),
                "inactive": s(Individual, "Inactive", "grey", "fa-user-slash", short_name="Ina", group_name="Activity"),
                "affected": s(Individual, "Affected", "red", "fa-disease", short_name="Aff", group_name="Affectedness"),
                "healthy": s(Individual, "Healthy", "green", "fa-heart", short_name="Hea", group_name="Affectedness"),
                "unsolved": s(Individual, "Unsolved", "brown", "fa-circle-xmark", short_name="Uns", group_name="Solved"),
                "solved": s(Individual, "Solved", "green", "fa-circle-check", short_name="Sol", group_name="Solved"),
            },
            "sample": {
                "planned": s(Sample, "Planned", "yellow", "fa-calendar", short_name="Plan", group_name="Process"),
                "received": s(Sample, "Recieved - In lab process", "orange", "fa-vials", short_name="Rec", group_name="Process"),
                "isolated": s(Sample, "Isolated", "green", "fa-circle-check", short_name="Iso", group_name="Process"),
                "available": s(Sample, "Available", "green", "fa-circle-check", short_name="Ava", group_name="Availability"),
                "not_available": s(Sample, "Not Available", "red", "fa-ban", short_name="N/A", group_name="Availability", connected_models=(Individual,)),
            },
            "test": {
                "planned": s(Test, "Planned", "yellow", "fa-flask", short_name="Plan", group_name="Process", connected_models=(Individual,)),
                "waiting": s(Test, "Waiting Data/Bioinformatic process", "orange", "fa-spinner", short_name="Wait", group_name="Process"),
                "completed": s(Test, "Data Delivered / Completed", "green", "fa-circle-check", short_name="Comp", group_name="Process"),
                "previous": s(Test, "Previous", "grey", "fa-clock-rotate-left", short_name="Prev", group_name="Previous"),
            },
            "pipeline": {
                "planned": s(Pipeline, "Planned", "yellow", "fa-diagram-project", short_name="Plan", group_name="Process"),
                "waiting": s(Pipeline, "Waiting Data/Bioinformatic process", "orange", "fa-spinner", short_name="Wait", group_name="Process"),
                "completed": s(Pipeline, "Bioinformatic process completed", "green", "fa-circle-check", short_name="Comp", group_name="Process"),
            },
            "analysis": {
                "planned": s(Analysis, "Planned", "yellow", "fa-calendar", short_name="PLan", group_name="Process"),
                "waiting": s(Analysis, "Waiting Confirmation", "orange", "fa-spinner", short_name="Conf", group_name="Process"),
                "completed": s(Analysis, "Completed", "blue", "fa-circle-check", short_name="Comp", group_name="Process", connected_models=(Individual,)),
                "reported": s(Analysis, "Reported", "green", "fa-file-circle-check", short_name="Rep", group_name="Process"),
                "initial": s(Analysis, "Initial Analysis", "orange", "fa-seedling", short_name="Int", group_name="Occasion"),
                "reanalysis": s(Analysis, "Reanalysis", "yellow", "fa-rotate", short_name="Rea", group_name="Occasion"),
            },
            "analysisreport": {
                "negative": s(AnalysisReport, "Negative", "red", "fa-circle-xmark", short_name="Neg", group_name="Result", connected_models=(Individual,)),
                "positive": s(AnalysisReport, "Positive", "green", "fa-circle-check", short_name="Pos", group_name="Result", connected_models=(Individual,)),
                "delivered": s(AnalysisReport, "Delivered to Clinician", "green", "fa-envelope-open-text", short_name="Del", group_name="Informed"),
            },
            "project": {
                "in_planning": s(Project, "In Planning", "blue", "", short_name="Plan", group_name="Process"),
                "in_progress": s(Project, "In Progress", "yellow", "", short_name="Prog", group_name="Process"),
                "on_hold": s(Project, "On Hold", "orange", "", short_name="Hold", group_name="Process"),
                "completed": s(Project, "Completed", "green", "", short_name="Comp", group_name="Process"),
                "cancelled": s(Project, "Cancelled", "grey", "", short_name="Canc", group_name="Process"),
            },
            "task": {
                "assigned": s(Task, "Assigned", "yellow", "", short_name="Asg", group_name="Process"),
                "active": s(Task, "Active", "orange", "", short_name="Act", group_name="Process"),
                "completed": s(Task, "Completed", "green", "", short_name="Comp", group_name="Process"),
                "cancelled": s(Task, "Cancelled", "grey", "", short_name="Canc", group_name="Process"),
            },
            "variant": {
                "not_reported": s(Variant, "Not reported", "red", "", short_name="NRep", group_name="Process"),
                "reported": s(Variant, "Reported", "green", "", short_name="Rep", group_name="Process"),
                "causative": s(Variant, "Causative", "green", "", short_name="Caus", group_name="Causativity", connected_models=(Individual,)),
                "suspected": s(Variant, "Suspected Causative", "yellow", "", short_name="SCaus", group_name="Causativity"),
                "secondary": s(Variant, "Secondary Finding", "blue", "", short_name="2nd", group_name="Causativity"),
                "previous": s(Variant, "Previously reported", "pink", "", short_name="PrevRep", group_name="Previous"),
                "ruled_out": s(Variant, "Ruled Out", "red", "", short_name="R/O", group_name="Validity"),
                "ongoing_sanger": s(Variant, "Ongoing Confirmation", "purple", "", short_name="Conf", group_name="Validity", connected_models=(Individual,)),
                "ongoing_func": s(Variant, "Ongoing Functional Study", "blue", "", short_name="Func", group_name="Functional", connected_models=(Individual,)),
                "novel_gene": s(Variant, "Novel Gene Disease Association", "green", "", short_name="Novel", group_name="Novel", connected_models=(Individual,)),
                "candidate": s(Variant, "Candidate Gene-Variant Association", "orange", "", short_name="Cand", group_name="Candidate", connected_models=(Individual,)),
            },
        }
        return all_statuses

    def _create_sample_types(self, user):
        types = ["DNA", "RNA", "Plasma", "Serum", "Whole Blood"]
        return {t.lower().replace(" ", "_"):
                SampleType.objects.get_or_create(name=t, defaults={"created_by": user})[0]
                for t in types}

    def _create_test_types(self, user):
        types = ["WGS", "WES", "Panel"]
        test_types = {
            t.lower(): TestType.objects.get_or_create(
                name=t, defaults={"created_by": user}
            )[0]
            for t in types
        }
        self._backfill_testtype_report_fields(test_types.values())
        return test_types

    def _backfill_testtype_report_fields(self, test_types) -> None:
        """Backfill empty TestType report fields from `report_text_field_reference.md`."""
        repo_root = Path(__file__).resolve().parents[3]
        md_path = repo_root / "report_text_field_reference.md"
        if not md_path.exists():
            self.stdout.write(self.style.WARNING(
                f"report_text_field_reference.md not found at {md_path} — skipping report text backfill."
            ))
            return

        parsed = _parse_report_text_field_reference_markdown(
            md_path.read_text(encoding="utf-8")
        )
        lower_to_canonical = {k.strip().lower(): k for k in parsed.keys()}

        model_fields = {f.name for f in TestType._meta.fields}

        for tt in test_types:
            if not getattr(tt, "name", None):
                continue
            canonical_name = lower_to_canonical.get(tt.name.strip().lower())
            if not canonical_name:
                continue
            payload = _normalize_testtype_report_payload(parsed[canonical_name])

            updates: dict[str, str] = {}
            for field_name, value in payload.items():
                if field_name not in model_fields:
                    continue
                current = getattr(tt, field_name, "")
                if current is None or (isinstance(current, str) and current.strip() == ""):
                    updates[field_name] = value

            if updates:
                TestType.objects.filter(pk=tt.pk).update(**updates)

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

    def _get_or_create_institutions(self, user):
        institution_specs = [
            {
                "name": "Ankara Rare Disease Lab",
                "city": "Ankara",
                "center_name": "Genetics Center",
                "speciality": "Medical Genetics",
                "latitude": 39.9334,
                "longitude": 32.8597,
            },
            {
                "name": "Istanbul Genomics Center",
                "city": "Istanbul",
                "center_name": "Genomic Medicine Unit",
                "speciality": "Clinical Genetics",
                "latitude": 41.0082,
                "longitude": 28.9784,
            },
            {
                "name": "Izmir Pediatric Genetics Clinic",
                "city": "Izmir",
                "center_name": "Pediatric Rare Disease Program",
                "speciality": "Pediatric Genetics",
                "latitude": 38.4237,
                "longitude": 27.1428,
            },
            {
                "name": "Bursa Metabolic Diseases Center",
                "city": "Bursa",
                "center_name": "Metabolic Genetics Service",
                "speciality": "Metabolic Diseases",
                "latitude": 40.1885,
                "longitude": 29.0610,
            },
            {
                "name": "Antalya Neuromuscular Genetics Unit",
                "city": "Antalya",
                "center_name": "Neuromuscular Disorders Program",
                "speciality": "Neurology",
                "latitude": 36.8969,
                "longitude": 30.7133,
            },
        ]
        institutions = []
        update_fields = {
            "city",
            "center_name",
            "speciality",
            "latitude",
            "longitude",
        }
        for spec in institution_specs:
            defaults = {"created_by": user, **spec}
            inst, _ = Institution.objects.get_or_create(
                name=spec["name"],
                defaults=defaults,
            )
            changed_fields = []
            for field in update_fields:
                value = spec[field]
                if getattr(inst, field) != value:
                    setattr(inst, field, value)
                    changed_fields.append(field)
            if changed_fields:
                inst.save(update_fields=changed_fields)
            institutions.append(inst)
        return institutions

    def _create_projects(self, user, all_statuses):
        project_specs = [
            {
                "name": "Rare Disease Pilot",
                "description": "Pilot project for rare disease analysis",
                "status": "in_planning",
                "priority": "medium",
                "due_offset_days": 120,
            },
            {
                "name": "Pediatric Neurogenetics Cohort",
                "description": "Longitudinal analysis of pediatric neurogenetic cases",
                "status": "in_progress",
                "priority": "high",
                "due_offset_days": 90,
            },
            {
                "name": "Metabolic Disorders Review",
                "description": "Focused review of inherited metabolic disease families",
                "status": "on_hold",
                "priority": "medium",
                "due_offset_days": 180,
            },
            {
                "name": "Solved Families Archive",
                "description": "Archived project for solved demonstration families",
                "status": "completed",
                "priority": "low",
                "due_offset_days": -30,
            },
            {
                "name": "Legacy Panel Follow-up",
                "description": "Cancelled legacy panel follow-up project",
                "status": "cancelled",
                "priority": "low",
                "due_offset_days": -10,
            },
        ]
        projects = []
        for spec in project_specs:
            due_date = timezone.now().date() + timedelta(days=spec["due_offset_days"])
            project, _ = Project.objects.get_or_create(
                name=spec["name"],
                defaults={
                    "description": spec["description"],
                    "priority": spec["priority"],
                    "due_date": due_date,
                    "created_by": user,
                },
            )
            changed_fields = []
            for field, value in (
                ("description", spec["description"]),
                ("priority", spec["priority"]),
                ("due_date", due_date),
            ):
                if getattr(project, field) != value:
                    setattr(project, field, value)
                    changed_fields.append(field)
            if changed_fields:
                project.save(update_fields=changed_fields)

            status = all_statuses["project"].get(spec["status"])
            if status:
                project.statuses.set([status])
            projects.append(project)
        return projects

    def _create_identifier_types(self, user):
        config = [
            ("RareBoost", "RareBoost", 1, True),
            ("Biobank",   "Biobank",   2, True),
            ("ERDERA",    "ERDERA",    3, False),
        ]
        result = {}
        for name, description, priority, show_in_table in config:
            example = identifier_type_example_for_name(name)
            id_type, _ = IdentifierType.objects.get_or_create(
                name=name,
                defaults={
                    "description": description,
                    "example": example,
                    "created_by": user,
                    "use_priority": priority,
                    "is_shown_in_table": show_in_table,
                })
            changed = False
            if id_type.use_priority != priority:
                id_type.use_priority = priority; changed = True
            if id_type.is_shown_in_table != show_in_table:
                id_type.is_shown_in_table = show_in_table; changed = True
            if not id_type.description:
                id_type.description = description; changed = True
            if example and not id_type.example:
                id_type.example = example; changed = True
            if changed:
                id_type.save()
            result[name.lower()] = id_type
        return result

    # ==================================================================
    # Individual helpers
    # ==================================================================

    def _status_cycle(self, statuses, domain, keys, seed):
        choices = [statuses[domain][key] for key in keys if statuses[domain].get(key)]
        if not choices:
            return None
        return choices[seed % len(choices)]

    def _statuses_from_groups(self, *statuses):
        return [status for status in statuses if status]

    def _individual_statuses(self, all_statuses, family_number, member_index):
        seed = family_number + member_index
        return self._statuses_from_groups(
            self._status_cycle(all_statuses, "individual", ("active", "inactive"), seed),
            self._status_cycle(all_statuses, "individual", ("affected", "healthy"), seed + 1),
            self._status_cycle(all_statuses, "individual", ("unsolved", "solved"), seed + 2),
        )

    def _sample_statuses(self, all_statuses, seed):
        return self._statuses_from_groups(
            self._status_cycle(all_statuses, "sample", ("planned", "received", "isolated"), seed),
            self._status_cycle(all_statuses, "sample", ("available", "not_available"), seed + 1),
        )

    def _test_statuses(self, all_statuses, seed):
        statuses = self._statuses_from_groups(
            self._status_cycle(all_statuses, "test", ("planned", "waiting", "completed"), seed),
        )
        if seed % 4 == 0 and all_statuses["test"].get("previous"):
            statuses.append(all_statuses["test"]["previous"])
        return statuses

    def _pipeline_statuses(self, all_statuses, seed):
        return self._statuses_from_groups(
            self._status_cycle(all_statuses, "pipeline", ("planned", "waiting", "completed"), seed),
        )

    def _analysis_statuses(self, all_statuses, seed):
        return self._statuses_from_groups(
            self._status_cycle(all_statuses, "analysis", ("planned", "waiting", "completed", "reported"), seed),
            self._status_cycle(all_statuses, "analysis", ("initial", "reanalysis"), seed + 1),
        )

    def _variant_statuses(self, all_statuses, seed):
        statuses = self._statuses_from_groups(
            self._status_cycle(all_statuses, "variant", ("not_reported", "reported"), seed),
            self._status_cycle(all_statuses, "variant", ("causative", "suspected", "secondary"), seed + 1),
            self._status_cycle(all_statuses, "variant", ("ruled_out", "ongoing_sanger"), seed + 2),
        )
        optional_statuses = (
            ("previous", 5),
            ("ongoing_func", 4),
            ("novel_gene", 6),
            ("candidate", 3),
        )
        for key, divisor in optional_statuses:
            status = all_statuses["variant"].get(key)
            if status and seed % divisor == 0:
                statuses.append(status)
        return statuses

    def _set_variant_statuses(self, variant, statuses):
        statuses = [status for status in statuses if status]
        variant.statuses.set(statuses)
        variant_ct = ContentType.objects.get_for_model(Variant)
        for status in statuses:
            TaggedStatus.objects.get_or_create(
                content_type=variant_ct,
                object_id=variant.pk,
                tag=status,
            )

    def _generate_unique_family_id(self, family_number):
        candidate_number = max(int(family_number), 1)
        family_id = f"RB_2025_{candidate_number:02d}"
        while Family.objects.filter(family_id=family_id).exists():
            candidate_number += 1
            family_id = f"RB_2025_{candidate_number:02d}"
        return family_id

    def _family_number_from_family_id(self, family_id):
        match = re.fullmatch(r"RB_20\d\d_(\d+)", family_id)
        if not match:
            raise ValueError(f"Unexpected generated family ID format: {family_id}")
        return int(match.group(1))

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

    def _create_individual(self, first_name, family, user, institution, statuses,
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
        if statuses:
            ind.statuses.set(statuses)
        ind.institution.add(institution)
        affected_status = any(status.name == "Affected" for status in statuses)
        if hpo_terms and affected_status:
            ind.hpo_terms.add(*random.sample(hpo_terms, min(random.randint(1, 5), len(hpo_terms))))
            if ind.is_affected != affected_status:
                ind.is_affected = affected_status
                ind.save(update_fields=["is_affected"])
        else:
            if ind.is_affected:
                ind.is_affected = False
                ind.save(update_fields=["is_affected"])
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

    def _task_payload_for_object(self, obj, index):
        if isinstance(obj, Family):
            family_id = obj.family_id
            tasks = [
                (
                    f"Review pedigree for {family_id}",
                    "Confirm family structure, consanguinity notes, and affected relatives before interpretation.",
                ),
                (
                    f"Confirm trio availability for {family_id}",
                    "Check whether parental samples are present and ready for segregation review.",
                ),
                (
                    f"Prepare case summary for {family_id}",
                    "Summarize phenotype, prior testing, and key clinical question for the genomic board.",
                ),
            ]
        elif isinstance(obj, Individual):
            individual_id = obj.primary_id
            tasks = [
                (
                    f"Curate phenotype terms for {individual_id}",
                    "Review HPO terms and update affectedness before analysis handoff.",
                ),
                (
                    f"Check consent and referral notes for {individual_id}",
                    "Verify consent status, clinician details, and referral documentation.",
                ),
                (
                    f"Review candidate diagnosis for {individual_id}",
                    "Compare clinical diagnosis notes with the current genomic findings.",
                ),
            ]
        elif isinstance(obj, Sample):
            sample_label = f"{obj.individual.primary_id} {obj.sample_type}"
            tasks = [
                (
                    f"Confirm sample QC for {sample_label}",
                    "Check concentration, integrity, and sample availability before sequencing.",
                ),
                (
                    f"Verify sample identity for {sample_label}",
                    "Cross-check sample label, individual ID, and biobank identifier.",
                ),
                (
                    f"Schedule library prep for {sample_label}",
                    "Coordinate wet-lab preparation and expected processing date.",
                ),
            ]
        elif isinstance(obj, Test):
            test_label = f"{obj.test_type} for {obj.sample.individual.primary_id}"
            tasks = [
                (
                    f"Confirm data receipt for {test_label}",
                    "Verify FASTQ or BAM delivery and record the data receipt status.",
                ),
                (
                    f"Review test scope for {test_label}",
                    "Confirm assay type, coverage expectations, and requested analysis scope.",
                ),
                (
                    f"Flag test notes for {test_label}",
                    "Capture wet-lab or service-provider notes before pipeline launch.",
                ),
            ]
        elif isinstance(obj, Pipeline):
            pipeline_label = f"{obj.type.name} for {obj.test.sample.individual.primary_id}"
            tasks = [
                (
                    f"Launch pipeline run for {pipeline_label}",
                    "Start the bioinformatics workflow and record input/output locations.",
                ),
                (
                    f"Review pipeline QC for {pipeline_label}",
                    "Inspect alignment, coverage, and variant-calling quality metrics.",
                ),
                (
                    f"Hand off variants for {pipeline_label}",
                    "Send prioritized variants and QC notes to the interpretation team.",
                ),
            ]
        elif isinstance(obj, Analysis):
            analysis_label = f"{obj.type or 'Analysis'} for {obj.pipeline.test.sample.individual.primary_id}"
            tasks = [
                (
                    f"Interpret candidate variants for {analysis_label}",
                    "Review inheritance, phenotype fit, and ACMG evidence for prioritized variants.",
                ),
                (
                    f"Prepare report draft for {analysis_label}",
                    "Draft result language, limitations, and recommendations for clinician review.",
                ),
                (
                    f"Confirm segregation plan for {analysis_label}",
                    "Identify variants that need Sanger confirmation or family segregation testing.",
                ),
            ]
        else:
            tasks = [
                (
                    f"Review genomic diagnostic item for {obj}",
                    "Coordinate the next handoff in the diagnostic workflow.",
                ),
            ]
        return tasks[index % len(tasks)]

    def _create_tasks(self, obj, user, all_statuses, project, num_tasks, base_date):
        if not hasattr(base_date, "date"):
            base_date = timezone.datetime.combine(
                base_date, timezone.datetime.min.time()
            ).replace(tzinfo=timezone.get_current_timezone())

        task_statuses = list(all_statuses.get("task", {}).values())

        for i in range(num_tasks):
            title, description = self._task_payload_for_object(obj, i)
            due_date = self._task_due_date(base_date, obj, i)
            status = self._task_status_for_due_date(task_statuses, due_date, i)
            task = Task.objects.create(
                title=title,
                description=description,
                content_object=obj,
                project=project,
                priority=random.choice(["low", "medium", "high"]),
                assigned_to=user,
                created_by=user,
                due_date=due_date,
            )

            if status:
                task.statuses.set([status])

    def _task_due_date(self, base_date, obj, index):
        """Mix overdue, upcoming, and later deadlines for demo task views."""
        today_start = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
        pattern = (getattr(obj, "pk", 0) or 0) + index
        if pattern % 6 == 0:
            return today_start - timedelta(days=random.randint(1, 7))
        if pattern % 6 in (1, 2, 3):
            return today_start + timedelta(days=random.randint(1, 14))
        if pattern % 6 == 4:
            return today_start + timedelta(days=random.randint(15, 45))
        return max(
            base_date + timedelta(days=random.randint(1, 30)),
            today_start + timedelta(days=random.randint(46, 75)),
        )

    def _task_status_for_due_date(self, task_statuses, due_date, index):
        if not task_statuses:
            return None

        by_name = {status.name.lower(): status for status in task_statuses}
        if due_date and due_date < timezone.now():
            return by_name.get("completed") or random.choice(task_statuses)

        pending = [
            by_name[name]
            for name in ("assigned", "active")
            if name in by_name
        ]
        if pending:
            return pending[index % len(pending)]
        return random.choice(task_statuses)

    # ==================================================================
    # Sample / Test / Pipeline / Analysis / Variant chain
    # ==================================================================

    def _create_samples(
        self, individual, contact, institution, sample_types, test_types, pipeline_types,
        num_samples, tests_per_sample, pipelines_per_test, analyses_per_pipeline,
        variants_per_analysis, tasks_per_object, user, all_statuses, project,
        analysis_types,
    ):
        for _ in range(num_samples):
            sample_type = random.choice(list(sample_types.values()))
            receipt_date = (timezone.now() - timedelta(days=random.randint(10, 100))).date()

            sample = Sample.objects.create(
                individual=individual,
                sample_type=sample_type,
                receipt_date=receipt_date,
                isolation_by=contact,
                created_by=user,
            )
            sample.statuses.set(self._sample_statuses(all_statuses, sample.pk))
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
                test.statuses.set(self._test_statuses(all_statuses, test.pk))
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
                    pipeline.statuses.set(self._pipeline_statuses(all_statuses, pipeline.pk))
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
            analysis.statuses.set(self._analysis_statuses(all_statuses, analysis.pk))

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

            classification_choices = [
                "pathogenic",
                "likely_pathogenic",
                "vus",
                "likely_benign",
                "benign",
            ]
            inheritance_choices = ["ad", "ar", "x_linked", "mitochondrial", "de_novo", "unknown"]
            classification = Classification.objects.create(
                variant=snv,
                user=user,
                classification=classification_choices[snv.pk % len(classification_choices)],
                inheritance=inheritance_choices[snv.pk % len(inheritance_choices)],
                notes="Auto-generated classification",
            )
            self._set_variant_statuses(
                snv,
                self._variant_statuses(all_statuses, snv.pk),
            )
