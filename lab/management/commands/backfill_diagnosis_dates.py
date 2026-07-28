from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from lab.models import AnalysisReport, Individual
from variant.models import Variant


class Command(BaseCommand):
    help = (
        "Backfill Individual.diagnosis_date from positive reports linked to "
        "causative variants for solved individuals by default."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write changes. Without this flag the command only prints a dry run.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace existing diagnosis_date values when they differ.",
        )
        parser.add_argument(
            "--strategy",
            choices=("earliest", "latest"),
            default="earliest",
            help="Which matching positive report date to use when several exist.",
        )
        parser.add_argument(
            "--individual-id",
            type=int,
            action="append",
            dest="individual_ids",
            help="Limit to one individual id. May be passed multiple times.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Limit the number of individuals processed, useful for inspection.",
        )
        parser.add_argument(
            "--solved-status",
            default="Solved",
            help="Individual status name that marks a solved case.",
        )
        parser.add_argument(
            "--causative-status",
            default="Causative",
            help="Variant status name that marks a causative variant.",
        )
        parser.add_argument(
            "--positive-report-status",
            default="Positive",
            help="AnalysisReport status name that marks a positive report.",
        )
        parser.add_argument(
            "--include-unsolved",
            action="store_true",
            help=(
                "Also backfill individuals that do not have the solved status. "
                "By default only solved individuals are considered."
            ),
        )
        parser.add_argument(
            "--include-noncausative",
            action="store_true",
            help=(
                "Also use reports linked to variants without the causative status, "
                "and reports linked to individuals through analysis when no variant "
                "link exists. By default only causative variants are considered."
            ),
        )
        parser.add_argument(
            "--include-negative",
            action="store_true",
            help=(
                "Also use reports without the positive report status. "
                "By default only positive reports are considered."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        overwrite = options["overwrite"]
        strategy = options["strategy"]
        individual_ids = options.get("individual_ids") or []
        limit = options.get("limit")
        solved_status = options["solved_status"]
        causative_status = options["causative_status"]
        positive_report_status = options["positive_report_status"]
        include_unsolved = options["include_unsolved"]
        include_noncausative = options["include_noncausative"]
        include_negative = options["include_negative"]

        matches = self._matching_reports(
            individual_ids=individual_ids,
            solved_status=solved_status,
            causative_status=causative_status,
            positive_report_status=positive_report_status,
            include_unsolved=include_unsolved,
            include_noncausative=include_noncausative,
            include_negative=include_negative,
        )
        if not matches:
            scope = "individuals" if include_unsolved else "solved individuals"
            variant_scope = (
                "reported variants or analysis-linked reports"
                if include_noncausative
                else "causative variants"
            )
            report_scope = "reports" if include_negative else "positive reports"
            self.stdout.write(
                self.style.WARNING(
                    f"No matching {scope} found for {report_scope} linked to "
                    f"{variant_scope}."
                )
            )
            self._print_diagnostics(
                solved_status=solved_status,
                causative_status=causative_status,
                positive_report_status=positive_report_status,
                include_unsolved=include_unsolved,
                include_noncausative=include_noncausative,
                include_negative=include_negative,
                individual_ids=individual_ids,
            )
            return

        selected = []
        skipped_existing = []
        for individual_id, rows in sorted(matches.items()):
            rows = sorted(
                rows,
                key=lambda row: (row["report_date"], row["report_id"]),
                reverse=(strategy == "latest"),
            )
            chosen = rows[0]
            individual = chosen["individual"]
            current_date = individual.diagnosis_date
            new_date = chosen["report_date"]
            if current_date and current_date != new_date and not overwrite:
                skipped_existing.append((individual, current_date, new_date, chosen))
                continue
            if current_date == new_date:
                continue
            selected.append((individual, new_date, chosen))
            if limit and len(selected) >= limit:
                break

        self._print_summary(
            selected=selected,
            skipped_existing=skipped_existing,
            apply_changes=apply_changes,
            overwrite=overwrite,
            strategy=strategy,
            include_unsolved=include_unsolved,
            include_noncausative=include_noncausative,
            include_negative=include_negative,
        )

        if not apply_changes or not selected:
            return

        with transaction.atomic():
            for individual, new_date, _chosen in selected:
                individual.diagnosis_date = new_date
                individual.save(update_fields=["diagnosis_date"])

        self.stdout.write(
            self.style.SUCCESS(f"Updated diagnosis_date for {len(selected)} individuals.")
        )

    def _matching_reports(
        self,
        *,
        individual_ids=None,
        solved_status,
        causative_status,
        positive_report_status,
        include_unsolved,
        include_noncausative,
        include_negative,
    ):
        matches = defaultdict(list)

        variant_qs = (
            Variant.objects.filter(
                reports__created_at__isnull=False,
                reports__isnull=False,
            )
            .select_related("individual")
            .values(
                "id",
                "individual_id",
                "individual__diagnosis_date",
                "reports__id",
                "reports__created_at",
            )
            .distinct()
        )
        if not include_unsolved:
            variant_qs = variant_qs.filter(individual__statuses__name__iexact=solved_status)
        if not include_noncausative:
            variant_qs = variant_qs.filter(statuses__name__iexact=causative_status)
        if not include_negative:
            variant_qs = variant_qs.filter(reports__statuses__name__iexact=positive_report_status)
        if individual_ids:
            variant_qs = variant_qs.filter(individual_id__in=individual_ids)

        individuals = Individual.objects.in_bulk(
            {row["individual_id"] for row in variant_qs}
        )
        for row in variant_qs:
            report_created_at = row["reports__created_at"]
            if not report_created_at:
                continue
            individual = individuals.get(row["individual_id"])
            if not individual:
                continue
            matches[row["individual_id"]].append(
                {
                    "individual": individual,
                    "report_id": row["reports__id"],
                    "report_date": report_created_at.date(),
                    "variant_id": row["id"],
                    "source": "variant",
                }
            )

        if include_noncausative:
            report_qs = (
                AnalysisReport.objects.filter(
                    analysis__pipeline__test__sample__individual__isnull=False,
                    created_at__isnull=False,
                )
                .values(
                    "id",
                    "created_at",
                    "analysis__pipeline__test__sample__individual_id",
                )
                .distinct()
            )
            if not include_unsolved:
                report_qs = report_qs.filter(
                    analysis__pipeline__test__sample__individual__statuses__name__iexact=solved_status,
                )
            if not include_negative:
                report_qs = report_qs.filter(statuses__name__iexact=positive_report_status)
            if individual_ids:
                report_qs = report_qs.filter(
                    analysis__pipeline__test__sample__individual_id__in=individual_ids,
                )

            report_individuals = Individual.objects.in_bulk(
                {
                    row["analysis__pipeline__test__sample__individual_id"]
                    for row in report_qs
                }
            )
            for row in report_qs:
                report_created_at = row["created_at"]
                individual_id = row["analysis__pipeline__test__sample__individual_id"]
                individual = report_individuals.get(individual_id)
                if not report_created_at or not individual:
                    continue
                matches[individual_id].append(
                    {
                        "individual": individual,
                        "report_id": row["id"],
                        "report_date": report_created_at.date(),
                        "variant_id": None,
                        "source": "analysis",
                    }
                )
        return matches

    def _print_diagnostics(
        self,
        *,
        solved_status,
        causative_status,
        positive_report_status,
        include_unsolved,
        include_noncausative,
        include_negative,
        individual_ids,
    ):
        individual_filter = {}
        if individual_ids:
            individual_filter["pk__in"] = individual_ids

        solved_individuals = Individual.objects.filter(
            **individual_filter,
            statuses__name__iexact=solved_status,
        ).distinct()
        causative_variants = Variant.objects.filter(
            individual__in=Individual.objects.filter(**individual_filter),
            statuses__name__iexact=causative_status,
        ).distinct()
        positive_reports = AnalysisReport.objects.filter(
            variants__individual__in=Individual.objects.filter(**individual_filter),
            statuses__name__iexact=positive_report_status,
        ).distinct()
        positive_reports_by_analysis = AnalysisReport.objects.filter(
            analysis__pipeline__test__sample__individual__in=Individual.objects.filter(**individual_filter),
            statuses__name__iexact=positive_report_status,
        ).distinct()
        reports_with_variants = AnalysisReport.objects.filter(
            variants__individual__in=Individual.objects.filter(**individual_filter),
            variants__isnull=False,
        ).distinct()
        reports_with_analysis_individual = AnalysisReport.objects.filter(
            analysis__pipeline__test__sample__individual__in=Individual.objects.filter(**individual_filter),
        ).distinct()
        causative_variants_with_reports = causative_variants.filter(
            reports__isnull=False,
        ).distinct()
        causative_variants_with_positive_reports = causative_variants.filter(
            reports__statuses__name__iexact=positive_report_status,
        ).distinct()
        scoped_variants = Variant.objects.filter(
            individual__in=Individual.objects.filter(**individual_filter),
            reports__created_at__isnull=False,
            reports__isnull=False,
        ).distinct()
        if not include_unsolved:
            scoped_variants = scoped_variants.filter(
                individual__statuses__name__iexact=solved_status,
            )
        if not include_noncausative:
            scoped_variants = scoped_variants.filter(
                statuses__name__iexact=causative_status,
            )
        if not include_negative:
            scoped_variants = scoped_variants.filter(
                reports__statuses__name__iexact=positive_report_status,
            )
        scoped_analysis_reports = AnalysisReport.objects.filter(
            analysis__pipeline__test__sample__individual__in=Individual.objects.filter(**individual_filter),
            created_at__isnull=False,
        ).distinct()
        if not include_unsolved:
            scoped_analysis_reports = scoped_analysis_reports.filter(
                analysis__pipeline__test__sample__individual__statuses__name__iexact=solved_status,
            )
        if not include_negative:
            scoped_analysis_reports = scoped_analysis_reports.filter(
                statuses__name__iexact=positive_report_status,
            )

        self.stdout.write("Diagnostics:")
        self.stdout.write(
            f"  Individuals with status {solved_status!r}: {solved_individuals.count()}"
        )
        self.stdout.write(
            f"  Variants with status {causative_status!r}: {causative_variants.count()}"
        )
        self.stdout.write(
            f"  Reports with status {positive_report_status!r}: {positive_reports.count()}"
        )
        self.stdout.write(
            "  Reports with status "
            f"{positive_report_status!r} via analysis path: {positive_reports_by_analysis.count()}"
        )
        self.stdout.write(
            f"  Reports linked to any variant: {reports_with_variants.count()}"
        )
        self.stdout.write(
            "  Reports linked to an individual through analysis: "
            f"{reports_with_analysis_individual.count()}"
        )
        self.stdout.write(
            "  Causative variants linked to any report: "
            f"{causative_variants_with_reports.count()}"
        )
        self.stdout.write(
            "  Causative variants linked to a positive report: "
            f"{causative_variants_with_positive_reports.count()}"
        )
        self.stdout.write(
            "  Matching variants after selected scope filters: "
            f"{scoped_variants.count()}"
        )
        self.stdout.write(
            "  Matching reports via analysis after selected scope filters: "
            f"{scoped_analysis_reports.count() if include_noncausative else 0}"
        )

    def _print_summary(
        self,
        *,
        selected,
        skipped_existing,
        apply_changes,
        overwrite,
        strategy,
        include_unsolved,
        include_noncausative,
        include_negative,
    ):
        mode = "APPLY" if apply_changes else "DRY RUN"
        solved_scope = "solved + unsolved" if include_unsolved else "solved only"
        variant_scope = "reported variants or analysis-linked reports" if include_noncausative else "causative variants"
        report_scope = "all report statuses" if include_negative else "positive reports"
        self.stdout.write(
            f"{mode}: strategy={strategy}, overwrite={overwrite}, "
            f"scope={solved_scope}, {variant_scope}, {report_scope}"
        )
        self.stdout.write(f"Candidates to update: {len(selected)}")
        self.stdout.write(f"Skipped existing different dates: {len(skipped_existing)}")

        for individual, new_date, chosen in selected[:25]:
            current = individual.diagnosis_date or "-"
            variant_label = chosen["variant_id"] if chosen["variant_id"] is not None else "-"
            self.stdout.write(
                "  "
                f"Individual {individual.pk}: {current} -> {new_date} "
                f"(report {chosen['report_id']}, variant {variant_label}, "
                f"source {chosen['source']})"
            )

        if len(selected) > 25:
            self.stdout.write(f"  ... {len(selected) - 25} more updates not shown")

        for individual, current_date, new_date, chosen in skipped_existing[:10]:
            variant_label = chosen["variant_id"] if chosen["variant_id"] is not None else "-"
            self.stdout.write(
                self.style.WARNING(
                    "  "
                    f"Skipped Individual {individual.pk}: existing {current_date}, "
                    f"candidate {new_date} "
                    f"(report {chosen['report_id']}, variant {variant_label}, "
                    f"source {chosen['source']})"
                )
            )

        if skipped_existing and not overwrite:
            self.stdout.write(
                self.style.WARNING(
                    "Pass --overwrite to replace existing differing diagnosis_date values."
                )
            )
