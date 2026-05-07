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
        self._individual_unsure_import_status = all_statuses["individual"].get("unsure_import")
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
                all_statuses["individual"]["active"],
                hpo_terms, is_index=False, creation_date=mother_date)
            self._create_note(mother, user)
            self._create_identifiers(
                mother, identifier_types, f"{family_id}.2",
                f"RD3.F{i+1:02d}.2", user)

            father_date = family_date + timedelta(days=random.randint(1, 3))
            father = self._create_individual(
                "Father", family, user, institution,
                all_statuses["individual"]["active"],
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
                    ind, contact, institution, sample_types, test_types, pipeline_types,
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
                "unsure_import": s(Individual, "Unsure Import", "orange", "fa-circle-question"),
            },
            "sample": {
                "planned": s(Sample, "Planned", "yellow", "fa-calendar", short_name="Plan", group_name="Process"),
                "received": s(Sample, "Recieved - In lab process", "orange", "fa-vials", short_name="Rec", group_name="Process"),
                "isolated": s(Sample, "Isolated", "green", "fa-circle-check", short_name="Iso", group_name="Process"),
                "available": s(Sample, "Available", "green", "fa-circle-check", short_name="Ava", group_name="Availability"),
                "not_available": s(Sample, "Not Available", "red", "fa-ban", short_name="N/A", group_name="Availability", connected_models=(Individual,)),
                "unsure_import": s(Sample, "Unsure Import", "orange", "fa-circle-question"),
            },
            "test": {
                "planned": s(Test, "Planned", "yellow", "fa-flask", short_name="Plan", group_name="Process", connected_models=(Individual,)),
                "waiting": s(Test, "Waiting Data/Bioinformatic process", "orange", "fa-spinner", short_name="Wait", group_name="Process"),
                "completed": s(Test, "Data Delivered / Completed", "green", "fa-circle-check", short_name="Comp", group_name="Process"),
                "previous": s(Test, "Previous", "grey", "fa-clock-rotate-left", short_name="Prev", group_name="Previous"),
                "unsure_import": s(Test, "Unsure Import", "orange", "fa-circle-question"),
            },
            "pipeline": {
                "planned": s(Pipeline, "Planned", "yellow", "fa-diagram-project", short_name="Plan", group_name="Process"),
                "waiting": s(Pipeline, "Waiting Data/Bioinformatic process", "orange", "fa-spinner", short_name="Wait", group_name="Process"),
                "completed": s(Pipeline, "Bioinformatic process completed", "green", "fa-circle-check", short_name="Comp", group_name="Process"),
                "unsure_import": s(Pipeline, "Unsure Import", "orange", "fa-circle-question"),
            },
            "analysis": {
                "planned": s(Analysis, "Planned", "yellow", "fa-calendar", short_name="PLan", group_name="Process"),
                "waiting": s(Analysis, "Waiting Confirmation", "orange", "fa-spinner", short_name="Conf", group_name="Process"),
                "completed": s(Analysis, "Completed", "blue", "fa-circle-check", short_name="Comp", group_name="Process", connected_models=(Individual,)),
                "reported": s(Analysis, "Reported", "green", "fa-file-circle-check", short_name="Rep", group_name="Process"),
                "initial": s(Analysis, "Initial Analysis", "orange", "fa-seedling", short_name="Int", group_name="Occasion"),
                "reanalysis": s(Analysis, "Reanalysis", "yellow", "fa-rotate", short_name="Rea", group_name="Occasion"),
                "unsure_import": s(Analysis, "Unsure Import", "orange", "fa-circle-question"),
            },
            "analysisreport": {
                "negative": s(AnalysisReport, "Negative", "red", "fa-circle-xmark", short_name="Neg", group_name="Result", connected_models=(Individual,)),
                "positive": s(AnalysisReport, "Positive", "green", "fa-circle-check", short_name="Pos", group_name="Result", connected_models=(Individual,)),
                "delivered": s(AnalysisReport, "Delivered to Clinician", "green", "fa-envelope-open-text", short_name="Del", group_name="Informed"),
                "unsure_import": s(AnalysisReport, "Unsure Import", "orange", "fa-circle-question"),
            },
            "project": {
                "in_planning": s(Project, "In Planning", "blue", "fa-compass-drafting", short_name="Plan", group_name="Process"),
                "in_progress": s(Project, "In Progress", "yellow", "fa-diagram-project", short_name="Prog", group_name="Process"),
                "on_hold": s(Project, "On Hold", "orange", "fa-pause", short_name="Hold", group_name="Process"),
                "completed": s(Project, "Completed", "green", "fa-flag-checkered", short_name="Comp", group_name="Process"),
                "cancelled": s(Project, "Cancelled", "grey", "fa-ban", short_name="Canc", group_name="Process"),
            },
            "task": {
                "assigned": s(Task, "Assigned", "yellow", "fa-list-check", short_name="Ass", group_name="Process"),
                "active": s(Task, "Active", "orange", "fa-spinner", short_name="Act", group_name="Process"),
                "completed": s(Task, "Completed", "green", "fa-circle-check", short_name="Comp", group_name="Process"),
                "cancelled": s(Task, "Cancelled", "grey", "fa-ban", short_name="Canc", group_name="Process"),
            },
            "variant": {
                "not_reported": s(Variant, "Not reported", "red", "fa-circle-question", short_name="NRep", group_name="Process"),
                "reported": s(Variant, "Reported", "green", "fa-circle-check", short_name="Rep", group_name="Process"),
                "causative": s(Variant, "Causative", "green", "fa-dna", short_name="Caus", group_name="Causativity", connected_models=(Individual,)),
                "suspected": s(Variant, "Suspected Causative", "yellow", "fa-question", short_name="SCaus", group_name="Causativity"),
                "secondary": s(Variant, "Secondary Finding", "blue", "fa-circle-half-stroke", short_name="2nd", group_name="Causativity"),
                "previous": s(Variant, "Previously reported", "pink", "fa-clock-rotate-left", short_name="PrevRep", group_name="Previous"),
                "ruled_out": s(Variant, "Ruled Out", "red", "fa-xmark", short_name="R/O", group_name="Validity"),
                "ongoing_sanger": s(Variant, "Ongoing Sanger Confirmation", "purple", "fa-vial", short_name="Sang", group_name="Validity", connected_models=(Individual,)),
                "ongoing_func": s(Variant, "Ongoing Functional Study", "blue", "fa-flask", short_name="Func", group_name="Functional", connected_models=(Individual,)),
                "novel_gene": s(Variant, "Novel Gene Disease Association", "green", "fa-plus", short_name="Novel", group_name="Novel", connected_models=(Individual,)),
                "candidate": s(Variant, "Candidate Gene-Variant Association", "yellow", "fa-magnifying-glass", short_name="Cand", group_name="Candidate", connected_models=(Individual,)),
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
            proj.statuses.set([all_statuses["project"]["in_planning"]])
        return proj

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
            if not ind.is_affected:
                ind.is_affected = True
                ind.save(update_fields=["is_affected"])
        else:
            if ind.is_affected:
                ind.is_affected = False
                ind.save(update_fields=["is_affected"])
            unsure_import = getattr(self, "_individual_unsure_import_status", None)
            if unsure_import and not ind.statuses.filter(pk=unsure_import.pk).exists():
                ind.statuses.add(unsure_import)
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
                task.statuses.set([random.choice(task_statuses)])

    # ==================================================================
    # Sample / Test / Pipeline / Analysis / Variant chain
    # ==================================================================

    def _create_samples(
        self, individual, contact, institution, sample_types, test_types, pipeline_types,
        num_samples, tests_per_sample, pipelines_per_test, analyses_per_pipeline,
        variants_per_analysis, tasks_per_object, user, all_statuses, project,
        analysis_types,
    ):
        available_sample = all_statuses["sample"].get("available")
        waiting_test = all_statuses["test"].get("waiting")
        waiting_pipeline = all_statuses["pipeline"].get("waiting")

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
            if available_sample:
                sample.statuses.set([available_sample])
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
                if waiting_test:
                    test.statuses.set([waiting_test])
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
                    if waiting_pipeline:
                        pipeline.statuses.set([waiting_pipeline])
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
        planned_analysis = all_statuses["analysis"].get("planned")
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
            if planned_analysis:
                analysis.statuses.set([planned_analysis])

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

            classification = Classification.objects.create(
                variant=snv,
                user=user,
                classification=random.choice([
                    "pathogenic", "likely_pathogenic", "vus",
                    "likely_benign", "benign"]),
                inheritance=random.choice(["ad", "ar", "de_novo", "unknown"]),
                notes="Auto-generated classification",
            )
            if classification.classification in {"pathogenic", "likely_pathogenic"}:
                variant_statuses = [
                    all_statuses["variant"].get("reported"),
                    all_statuses["variant"].get("causative"),
                ]
                if random.random() < 0.7:
                    variant_statuses.append(all_statuses["variant"].get("ongoing_sanger"))
            elif classification.classification == "vus":
                variant_statuses = [
                    all_statuses["variant"].get("reported"),
                    all_statuses["variant"].get("suspected"),
                ]
            else:
                variant_statuses = [
                    all_statuses["variant"].get("not_reported"),
                    all_statuses["variant"].get("ruled_out"),
                ]

            if random.random() < 0.25:
                variant_statuses.append(all_statuses["variant"].get("ongoing_func"))
            if random.random() < 0.15:
                variant_statuses.append(all_statuses["variant"].get("novel_gene"))
            if random.random() < 0.15:
                variant_statuses.append(all_statuses["variant"].get("candidate"))

            snv.statuses.set([status for status in variant_statuses if status])
