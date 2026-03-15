"""Clear all non-essential data from the database.

Deletion order respects FK constraints:
  1  Variant subclasses → Variant base → Gene
  2  AnalysisReport / AnalysisRequestForm
  3  Analysis → Pipeline → Test → Sample
  4  CrossIdentifier → Individual (after nullifying self-refs) → Family
  5  Note · Task · TaggedStatus · Project
  6  Status (preserving defaults) · StatusGroup
  7  Lookup tables: AnalysisType, PipelineType, TestType, SampleType, IdentifierType
  8  Institution
  9  Ontologies (optional, --keep-ontologies)
 10  Non-superuser Users

Flags:
  --include-history   Also wipe simple_history records for our apps
  --keep-genes        Keep HGNC Gene data
  --keep-ontologies   Keep Ontology / Term data
  --yes               Skip the confirmation prompt
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from lab import history_notifications
from simple_history.signals import post_create_historical_record


DEFAULT_STATUSES = [
    "Registered", "Active", "Completed", "Cancelled",
    "Pending", "In Progress", "Awaiting Data Arrival",
]


class Command(BaseCommand):
    help = "Clear all entries from the database except the superuser and default statuses."

    def add_arguments(self, parser):
        parser.add_argument(
            "--include-history",
            action="store_true",
            help="Also delete simple_history historical records for lab / variant models.",
        )
        parser.add_argument(
            "--keep-genes",
            action="store_true",
            help="Keep imported HGNC Gene data.",
        )
        parser.add_argument(
            "--keep-ontologies",
            action="store_true",
            help="Keep loaded Ontology / Term / Synonym / Relationship data.",
        )
        parser.add_argument(
            "--yes", "-y",
            action="store_true",
            dest="yes",
            help="Skip the confirmation prompt.",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            confirm = input(
                "This will delete ALL lab data (variants, individuals, analyses, etc.).\n"
                "Type 'yes' to continue: "
            )
            if confirm.strip().lower() != "yes":
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        # Disconnect history signal to prevent notification errors during bulk deletes
        post_create_historical_record.disconnect(
            receiver=history_notifications.notify_on_history
        )
        try:
            self._clear(options)
        finally:
            post_create_historical_record.connect(
                receiver=history_notifications.notify_on_history
            )

        self.stdout.write(self.style.SUCCESS("Database cleared successfully."))

    # ------------------------------------------------------------------

    def _delete(self, qs, label: str):
        count, _ = qs.delete()
        self.stdout.write(f"  Deleted {count:>6}  {label}")

    def _clear(self, options):
        from lab.models import (
            Analysis,
            AnalysisReport,
            AnalysisRequestForm,
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
            StatusGroup,
            TaggedStatus,
            Task,
            Test,
            TestType,
        )
        from variant.models import (
            Annotation,
            Classification,
            CNV,
            delins,
            Gene,
            Repeat,
            SNV,
            SV,
            Variant,
        )

        # ── 1. Variant data ───────────────────────────────────────────
        self.stdout.write("Phase 1: Variant data")
        self._delete(Classification.objects.all(), "Classification")
        self._delete(Annotation.objects.all(), "Annotation")
        # Delete concrete subclasses before the polymorphic base
        self._delete(SNV.objects.all(), "SNV")
        self._delete(CNV.objects.all(), "CNV")
        self._delete(SV.objects.all(), "SV")
        self._delete(Repeat.objects.all(), "Repeat")
        self._delete(delins.objects.all(), "delins")
        self._delete(Variant.objects.all(), "Variant (base)")
        if not options["keep_genes"]:
            self._delete(Gene.objects.all(), "Gene")

        # ── 2. Reports and request forms ──────────────────────────────
        self.stdout.write("Phase 2: Reports / request forms")
        self._delete(AnalysisReport.objects.all(), "AnalysisReport")
        self._delete(AnalysisRequestForm.objects.all(), "AnalysisRequestForm")

        # ── 3. Analysis chain (leaf → root) ───────────────────────────
        self.stdout.write("Phase 3: Analysis → Pipeline → Test → Sample")
        # Analysis.performed_by is M2M — cleared automatically on delete
        self._delete(Analysis.objects.all(), "Analysis")
        self._delete(Pipeline.objects.all(), "Pipeline")
        self._delete(Test.objects.all(), "Test")
        self._delete(Sample.objects.all(), "Sample")

        # ── 4. Individuals ────────────────────────────────────────────
        self.stdout.write("Phase 4: CrossIdentifier → Individual → Family")
        # Nullify self-referential FKs before deletion
        Individual.objects.all().update(mother=None, father=None)
        self._delete(CrossIdentifier.objects.all(), "CrossIdentifier")
        self._delete(Individual.objects.all(), "Individual")
        self._delete(Family.objects.all(), "Family")

        # ── 5. Notes / Tasks / TaggedStatuses / Projects ──────────────
        self.stdout.write("Phase 5: Notes · Tasks · TaggedStatuses · Projects")
        self._delete(Note.objects.all(), "Note")
        self._delete(Task.objects.all(), "Task")
        self._delete(TaggedStatus.objects.all(), "TaggedStatus")
        self._delete(Project.objects.all(), "Project")

        # ── 6. Statuses ───────────────────────────────────────────────
        self.stdout.write("Phase 6: Status · StatusGroup")
        removed, _ = Status.objects.exclude(name__in=DEFAULT_STATUSES).delete()
        self.stdout.write(f"  Deleted {removed:>6}  Status (non-default)")
        self.stdout.write(f"  Kept           Status (defaults: {DEFAULT_STATUSES})")
        self._delete(StatusGroup.objects.all(), "StatusGroup")

        # ── 7. Lookup / type tables ───────────────────────────────────
        self.stdout.write("Phase 7: Lookup tables")
        self._delete(AnalysisType.objects.all(), "AnalysisType")
        self._delete(PipelineType.objects.all(), "PipelineType")
        self._delete(TestType.objects.all(), "TestType")
        self._delete(SampleType.objects.all(), "SampleType")
        self._delete(IdentifierType.objects.all(), "IdentifierType")

        # ── 8. Institutions ───────────────────────────────────────────
        self.stdout.write("Phase 8: Institution")
        self._delete(Institution.objects.all(), "Institution")

        # ── 9. Ontologies (optional) ──────────────────────────────────
        if not options["keep_ontologies"]:
            self.stdout.write("Phase 9: Ontologies")
            try:
                from ontologies.models import (
                    CrossReference,
                    Relationship,
                    Synonym,
                    Term,
                    Ontology,
                )
                self._delete(CrossReference.objects.all(), "CrossReference")
                self._delete(Relationship.objects.all(), "Relationship")
                self._delete(Synonym.objects.all(), "Synonym")
                self._delete(Term.objects.all(), "Term")
                self._delete(Ontology.objects.all(), "Ontology")
            except ImportError:
                self.stdout.write("  ontologies app not found, skipping.")
        else:
            self.stdout.write("Phase 9: Ontologies — kept (--keep-ontologies).")

        # ── 10. simple_history records (optional) ─────────────────────
        if options["include_history"]:
            self.stdout.write("Phase 10: Historical records")
            self._clear_history()

        # ── 11. Users ─────────────────────────────────────────────────
        self.stdout.write("Phase 11: Users")
        self._delete(User.objects.filter(is_superuser=False), "User (non-superuser)")

    def _clear_history(self):
        """Delete all simple_history records for lab and variant models."""
        from lab.models import (
            HistoricalAnalysis,
            HistoricalAnalysisReport,
            HistoricalAnalysisRequestForm,
            HistoricalAnalysisType,
            HistoricalCrossIdentifier,
            HistoricalFamily,
            HistoricalIdentifierType,
            HistoricalIndividual,
            HistoricalInstitution,
            HistoricalNote,
            HistoricalPipeline,
            HistoricalPipelineType,
            HistoricalProject,
            HistoricalSample,
            HistoricalSampleType,
            HistoricalStatus,
            HistoricalStatusGroup,
            HistoricalTask,
            HistoricalTest,
            HistoricalTestType,
        )
        lab_historical = [
            HistoricalAnalysis, HistoricalAnalysisReport, HistoricalAnalysisRequestForm,
            HistoricalAnalysisType, HistoricalCrossIdentifier, HistoricalFamily,
            HistoricalIdentifierType, HistoricalIndividual, HistoricalInstitution,
            HistoricalNote, HistoricalPipeline, HistoricalPipelineType,
            HistoricalProject, HistoricalSample, HistoricalSampleType,
            HistoricalStatus, HistoricalStatusGroup, HistoricalTask,
            HistoricalTest, HistoricalTestType,
        ]
        for model in lab_historical:
            self._delete(model.objects.all(), model.__name__)

        try:
            from variant.models import (
                HistoricalAnnotation,
                HistoricalClassification,
                HistoricalCNV,
                Historicaldelins,
                HistoricalRepeat,
                HistoricalSNV,
                HistoricalSV,
                HistoricalVariant,
            )
            for model in [
                HistoricalAnnotation, HistoricalClassification, HistoricalCNV,
                Historicaldelins, HistoricalRepeat, HistoricalSNV,
                HistoricalSV, HistoricalVariant,
            ]:
                self._delete(model.objects.all(), model.__name__)
        except ImportError:
            pass
