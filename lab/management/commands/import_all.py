"""Comprehensive data import command for Özbek Lab.

Sheets processed from the master XLSX
---------------------------------------
  OZBEK LAB          – Families, Institutions, Individuals, Samples
  Analiz Takip        – Test + Analysis per row (pipeline linked later by Gennext sheet)
  Variant List        – SNV variants
  Kurumlar            – Institution coordinate / metadata lookup (replaces Gönderen Kurum Harita)
  Sanger Konfirmasyonları – Sanger tests
  WGS_TÜSEB          – WGS tests from TÜSEB
  External            – Individuals without primary/secondary cross-ID
  Katar-Uzun Okuma Hastaları – Long Read WGS (Katar)
  Dubai-Uzun Okuma Hastaları – Long Read WGS (Dubai)
  CP_COHORT           – CP cohort project assignment
  RNA SEQ             – RNA Seq tests
  Gennext Analiz Listesi – Gennext pipelines (links Analiz Takip analyses)
  RarePipe Analiz Listesi – RarePipe pipelines (⚠ date column missing — remind user)

Optional external inputs
------------------------
  --rarepipe-tsv      – Legacy RarePipe TSV samplesheet
  --yayin-ici         – Path to Yayın_İçi XLSX (sheet GÜNCELyayıniciyedek)
  --forms-dir / --reports-dir – File attachment directories

Processing order
----------------
  0a Load ontologies_data.json fixture (if Ontology table empty)
  0b import_hgnc_data (if Gene table empty)
  1  Setup statuses / IdentifierTypes / AnalysisTypes / ozbek_set_id_priorities
  2  Families + Institutions (OZBEK LAB pass 1)
  3  Individuals + CrossIdentifiers (OZBEK LAB pass 2)
  4  Samples (OZBEK LAB pass 3)
  5  Analiz Takip → Test + Analysis (pipeline=None, linked in step 9)
  6  RarePipe TSV (--rarepipe-tsv)
  7  Parent links
  8  Sanger Konfirmasyonları
  9  WGS_TÜSEB
 10  External
 11  Katar / Dubai long-read sheets
 12  CP_COHORT
 13  RNA SEQ
 14  Gennext Analiz Listesi (creates Pipelines and links to analyses from step 5)
 15  RarePipe Analiz Listesi (⚠ skipped — no date column yet)
 16  Variant List
 17  link_imported_genes
 18  File attachments
 19  Yayın_İçi (--yayin-ici)

REMINDERS (ask after implementation):
  • CNV / SV / Repeat variant format in Variant List (Q5)
  • RarePipe Analiz Listesi: add a date column (Q10)
  • Yayın_İçi Variant column format (Q12)
"""

import csv
import os
import re
from pathlib import Path

import openpyxl
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files import File
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from lab.models import (
    Analysis,
    AnalysisReport,
    AnalysisRequestForm,
    CrossIdentifier,
    Family,
    IdentifierType,
    Individual,
    Institution,
    Pipeline,
    Project,
    Sample,
    Status,
    Task,
    Test,
)
from ontologies.models import Ontology
from variant.models import Classification, Gene, SNV, Variant

from lab.management.commands._import_helpers import (
    build_id_map,
    get_family_id,
    get_hpo_terms,
    get_initials,
    get_or_create_analysis_type,
    get_or_create_pipeline_type,
    get_or_create_sample_type,
    get_or_create_status,
    get_or_create_test_type,
    get_or_create_user,
    map_classification,
    map_inheritance,
    normalize_id,
    normalize_sex,
    parse_and_add_notes,
    parse_date,
    parse_date_from_filename,
    parse_variant_string,
    to_bool,
)

User = get_user_model()

# ---------------------------------------------------------------------------
# Zygosity map (spreadsheet labels → model choice keys)
# ---------------------------------------------------------------------------
ZYGOSITY_MAP = {
    "het.": "het",
    "hom.": "hom",
    "hemizigot": "hemi",
    "heteroplazmi": "hetpl",
}


def _map_zygosity_strict(value, warn_fn=None):
    """Return model key for *value*, or None and call warn_fn if unrecognised."""
    if not value:
        if warn_fn:
            warn_fn(f"  Zygosity is empty — skipping variant")
        return None
    mapped = ZYGOSITY_MAP.get(str(value).strip().lower())
    if mapped is None and warn_fn:
        warn_fn(f"  Unrecognised zygosity {value!r} — skipping variant")
    return mapped


class Command(BaseCommand):
    help = "Comprehensive Özbek Lab data import (XLSX + optional external files)"

    # ------------------------------------------------------------------
    # Arguments
    # ------------------------------------------------------------------

    def add_arguments(self, parser):
        parser.add_argument("xlsx_file", type=str, help="Path to the master XLSX file")
        parser.add_argument("--admin-username", required=True,
                            help="Username for created_by / performed_by fallback")
        parser.add_argument("--rarepipe-tsv", dest="rarepipe_tsv",
                            help="Path to legacy RarePipe TSV samplesheet")
        parser.add_argument("--yayin-ici", dest="yayin_ici",
                            help="Path to Yayın_İçi XLSX (GÜNCELyayıniciyedek sheet)")
        parser.add_argument("--forms-dir", dest="forms_dir",
                            help="Directory of analysis request form files")
        parser.add_argument("--reports-dir", dest="reports_dir",
                            help="Directory of analysis report files")
        parser.add_argument("--skip-hgnc", dest="skip_hgnc", action="store_true",
                            help="Skip HGNC gene data download check")
        parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                            help="Validate without writing to the database")

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        self.dry_run: bool = options["dry_run"]
        if self.dry_run:
            self.stdout.write(self.style.WARNING("-- DRY RUN: nothing will be saved --"))

        try:
            self.admin_user = User.objects.get(username=options["admin_username"])
        except User.DoesNotExist:
            raise CommandError(f"Admin user {options['admin_username']!r} not found")

        file_path = options["xlsx_file"]
        if not os.path.exists(file_path):
            raise CommandError(f"File not found: {file_path}")

        # Instance-level state shared between steps
        self.analysis_map: dict = {}       # (lab_id, tt_name) → Analysis

        # Step 0a — ontologies
        self._step0a_ensure_ontologies()

        # Step 0b — HGNC genes
        self._step0b_ensure_hgnc(options["skip_hgnc"])

        # Step 1
        self.statuses, self.id_types = self._step1_setup()

        # Load workbook
        self.stdout.write(f"Loading workbook: {file_path}")
        wb = openpyxl.load_workbook(file_path, data_only=True)
        kurumlar_map = self._load_kurumlar_map(wb)
        rows = self._load_ozbek_lab_rows(wb)

        # Steps 2–4 — OZBEK LAB
        families, institutions, unknown_inst = self._step2_families_institutions(
            rows, kurumlar_map)
        self._step3_individuals(rows, families, institutions, unknown_inst)
        self._step4_samples(rows)

        # Step 5 — Analiz Takip
        self._step5_analiz_takip(wb)

        # Step 6 — RarePipe TSV (external)
        if options.get("rarepipe_tsv"):
            self._step6_rarepipe(options["rarepipe_tsv"])

        # Step 7 — Parent links
        self._step7_parent_links(families)

        # Steps 8–15 — extra sheets
        self._step_sanger(wb)
        self._step_wgs_tuseb(wb)
        self._step_external(wb, kurumlar_map)
        self._step_long_read(wb, "Katar-Uzun Okuma Hastaları", "Katar",
                             "Qatar - Long Read WGS Project")
        self._step_long_read(wb, "Dubai-Uzun Okuma Hastaları", "Dubai",
                             "Dubai - Long Read WGS Project")
        self._step_cp_cohort(wb)
        self._step_rna_seq(wb)
        self._step_gennext_analiz(wb)       # links Analiz Takip analyses to pipelines
        self._step_rarepipe_analiz(wb)      # ⚠ skipped — no date column yet

        # Step 16 — Variant List
        self._step_variants(wb)

        # Step 17 — link_imported_genes
        if not self.dry_run:
            self.stdout.write("Step 17: Linking genes via annotations…")
            call_command("link_imported_genes")

        # Step 18 — file attachments
        if options.get("forms_dir") or options.get("reports_dir"):
            self._step_file_attachments(options.get("forms_dir"), options.get("reports_dir"))

        # Step 19 — Yayın_İçi
        if options.get("yayin_ici"):
            self._step_yayin_ici(options["yayin_ici"])

        self.stdout.write(self.style.SUCCESS("Import completed successfully."))

    # ==================================================================
    # Step 0a — Ontologies
    # ==================================================================

    def _step0a_ensure_ontologies(self) -> None:
        """Load the bundled ontologies_data.json fixture when the Ontology
        table is empty so that HPO terms are available for the rest of the
        import (individuals, Yayın_İçi HPO attachments, etc.)."""
        if Ontology.objects.exists():
            self.stdout.write("Step 0a: Ontologies already loaded.")
            return
        self.stdout.write(self.style.WARNING(
            "Step 0a: Ontology table empty — loading ontologies_data.json fixture…"))
        if not self.dry_run:
            call_command("loaddata", "ontologies_data.json")
            loaded = Ontology.objects.count()
            if loaded:
                self.stdout.write(self.style.SUCCESS(
                    f"Step 0a: Loaded {loaded} ontologies."))
            else:
                self.stdout.write(self.style.WARNING(
                    "Step 0a: Fixture loaded but no Ontology objects found. "
                    "Ensure ontologies_data.json is in a fixtures/ directory."))

    # ==================================================================
    # Step 0b — HGNC
    # ==================================================================

    def _step0b_ensure_hgnc(self, skip_hgnc: bool) -> None:
        if skip_hgnc:
            self.stdout.write("Step 0b: --skip-hgnc set.")
            return
        if Gene.objects.exists():
            self.stdout.write("Step 0b: Gene table populated — skipping import_hgnc_data.")
            return
        self.stdout.write(self.style.WARNING(
            "Step 0b: Gene table empty — running import_hgnc_data…"))
        if not self.dry_run:
            call_command("import_hgnc_data")

    # ==================================================================
    # Step 1 — Setup
    # ==================================================================

    def _step1_setup(self) -> tuple:
        self.stdout.write("Step 1: Setting up statuses, identifier types, analysis types…")
        ct = self._content_types()

        def s(name, desc, color, ct_key, icon):
            return get_or_create_status(name, desc, color, self.admin_user,
                                        ct.get(ct_key), icon)

        statuses = {
            "individual": {
                "registered":  s("Registered",  "Initial status",                "gray",       "individual", "fa-user-plus"),
                "solved":       s("Solved",       "Entry solved",                  "green",      "individual", "fa-circle-check"),
                "unsolved":     s("Unsolved",     "Entry unsolved",                "red",        "individual", "fa-circle-xmark"),
                "solved_plp":   s("Solved - P/LP","Solved pathogenic",            "green",      "individual", "fa-circle-check"),
                "solved_vus":   s("Solved - VUS", "Solved with VUS",              "lightgreen", "individual", "fa-circle-check"),
                "novel_gene":   s("Novel Gene Disease Assoc.", "Novel association","purple",    "individual", "fa-plus"),
                "candidate":    s("Candidate gene-variant", "Candidate",          "orange",     "individual", "fa-magnifying-glass"),
            },
            "sample": {
                "not_available":     s("Not Available",          "Placeholder",    "gray",   "sample", "fa-ban"),
                "pending_blood":     s("Pending Blood Recovery", "Awaiting draw",  "red",    "sample", "fa-droplet"),
                "pending_isolation": s("Pending Isolation",      "Awaiting iso",   "yellow", "sample", "fa-vials"),
                "available":         s("Available",              "Ready",          "green",  "sample", "fa-circle-check"),
            },
            "test": {
                "completed":   s("Completed",            "Done",                   "green",  "test", "fa-circle-check"),
                "in_progress": s("In Progress",          "Ongoing",                "yellow", "test", "fa-spinner"),
                "pending":     s("Pending",              "Waiting",                "red",    "test", "fa-clock"),
                "previous":    s("Previous",             "Historical",             "orange", "test", "fa-clock-rotate-left"),
                "sent":        s("Sent",                 "Sent for sequencing",    "blue",   "test", "fa-paper-plane"),
                "awaiting":    s("Awaiting Data Arrival","Waiting for data",       "red",    "test", "fa-hourglass-half"),
            },
            "pipeline": {
                "completed":   s("Completed",   "Done",     "green",  "pipeline", "fa-circle-check"),
                "in_progress": s("In Progress", "Ongoing",  "yellow", "pipeline", "fa-spinner"),
            },
            "analysis": {
                "completed":    s("Completed",    "Done",          "green",  "analysis", "fa-circle-check"),
                "in_progress":  s("In Progress",  "Ongoing",       "yellow", "analysis", "fa-spinner"),
                "pending_data": s("Pending Data", "Waiting",       "red",    "analysis", "fa-hourglass-half"),
            },
            "project": {
                "in_progress": s("In Progress", "Active",  "green",  "project", "fa-diagram-project"),
                "setting_up":  s("Setting Up",  "Setup",   "yellow", "project", "fa-gears"),
                "completed":   s("Completed",   "Done",    "gray",   "project", "fa-flag-checkered"),
            },
            "task": {
                "active":    s("Active",    "Ongoing", "yellow", "task", "fa-list-check"),
                "completed": s("Completed", "Done",    "green",  "task", "fa-circle-check"),
                "overdue":   s("Overdue",   "Late",    "red",    "task", "fa-triangle-exclamation"),
            },
        }

        id_types = {}
        if not self.dry_run:
            for name in ("RareBoost", "Biobank"):
                id_type, _ = IdentifierType.objects.get_or_create(
                    name=name,
                    defaults={"description": f"{name} identifier",
                              "created_by": self.admin_user},
                )
                id_types[name] = id_type

            for at_name in ("Clinical WES", "Clinical WGS", "Research WGS",
                            "Research WES", "RNA-seq", "Reanalysis"):
                get_or_create_analysis_type(at_name, self.admin_user)

            Institution.objects.get_or_create(
                name="Unknown",
                defaults={"contact": "Placeholder", "created_by": self.admin_user},
            )
            call_command("ozbek_set_id_priorities")

        return statuses, id_types

    # ------------------------------------------------------------------
    # Workbook helpers
    # ------------------------------------------------------------------

    def _content_types(self) -> dict:
        return {
            "individual": ContentType.objects.get_for_model(Individual),
            "sample":     ContentType.objects.get_for_model(Sample),
            "test":       ContentType.objects.get_for_model(Test),
            "pipeline":   ContentType.objects.get_for_model(Pipeline),
            "analysis":   ContentType.objects.get_for_model(Analysis),
            "project":    ContentType.objects.get_for_model(Project),
            "task":       ContentType.objects.get_for_model(Task),
        }

    def _load_kurumlar_map(self, wb) -> dict:
        """Load institution metadata from the Kurumlar sheet (replaces Gönderen Kurum Harita)."""
        kurumlar_map: dict = {}
        try:
            ws = wb["Kurumlar"]
        except KeyError:
            self.stdout.write(self.style.WARNING(
                "Sheet 'Kurumlar' not found — proceeding without institution metadata."))
            return kurumlar_map
        headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1)) if c.value]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(c is None for c in row):
                continue
            d = dict(zip(headers, row[:len(headers)]))
            name = str(d.get("Kurum") or "").strip()
            if not name:
                continue
            info: dict = {}
            coord_val = d.get("Harita")
            if coord_val:
                try:
                    lat_str, lon_str = [p.strip() for p in str(coord_val).split(",")[:2]]
                    info["coords"] = (float(lat_str), float(lon_str))
                except Exception:
                    pass
            for col, key in (("Şehir", "city"), ("Resmi Ad", "official_name"),
                              ("Merkez", "center_name"), ("Birim", "speciality")):
                val = d.get(col)
                if val:
                    info[key] = str(val).strip()
            kurumlar_map[name] = info
        return kurumlar_map

    def _load_ozbek_lab_rows(self, wb) -> list:
        ws = wb["OZBEK LAB"]
        headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(c is None for c in row):
                continue
            rows.append({h: v for h, v in zip(headers, row) if h is not None})
        return rows

    def _ws_rows(self, wb, sheet_name: str):
        """Yield (row_dict, headers) for each non-blank row in a sheet. Returns [] if absent."""
        try:
            ws = wb[sheet_name]
        except KeyError:
            self.stdout.write(self.style.WARNING(
                f"  Sheet '{sheet_name}' not found — skipping."))
            return
        headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(c is None for c in row):
                continue
            yield dict(zip(headers, row[:len(headers)]))

    # ==================================================================
    # Step 2 — Families + Institutions
    # ==================================================================

    def _step2_families_institutions(self, rows, kurumlar_map) -> tuple:
        self.stdout.write("Step 2: Families and institutions…")
        unique_fids: set = set()
        inst_contacts: dict = {}  # name → set of contact strings

        for row in rows:
            lab_id = row.get("Özbek Lab. ID")
            if not lab_id:
                continue
            fid = get_family_id(lab_id)
            if fid:
                unique_fids.add(fid)

            # Parse clinician name / contact from combined column
            klinisyen_raw = str(row.get("Klinisyen & İletişim Bilgileri") or "")
            contact_part = ""
            if "/" in klinisyen_raw:
                _, contact_part = klinisyen_raw.split("/", 1)
                contact_part = contact_part.strip()

            inst_raw = str(row.get("Gönderen Kurum/Birim") or "")
            for name in [n.strip() for n in inst_raw.split(",") if n.strip()]:
                inst_contacts.setdefault(name, set())
                if contact_part:
                    inst_contacts[name].add(contact_part)

        families: dict = {}
        institutions: dict = {}
        unknown_inst = None

        if self.dry_run:
            self.stdout.write(f"  [DRY] {len(unique_fids)} families, "
                              f"{len(inst_contacts)} institutions.")
            return families, institutions, unknown_inst

        for fid in unique_fids:
            family, _ = Family.objects.get_or_create(
                family_id=fid, defaults={"created_by": self.admin_user})
            families[fid] = family

        unknown_inst, _ = Institution.objects.get_or_create(
            name="Unknown",
            defaults={"contact": "Placeholder", "created_by": self.admin_user})

        for name, contacts in inst_contacts.items():
            info = kurumlar_map.get(name, {})
            lat, lon = info.get("coords", (None, None)) if "coords" in info else (None, None)
            institution, created = Institution.objects.get_or_create(
                name=name,
                defaults={
                    "contact": "\n".join(contacts) if contacts else "",
                    "created_by": self.admin_user,
                    "latitude": lat or 0.0,
                    "longitude": lon or 0.0,
                    "city": info.get("city", ""),
                    "official_name": info.get("official_name", ""),
                    "center_name": info.get("center_name", ""),
                    "speciality": info.get("speciality", ""),
                },
            )
            if not created:
                changed = False
                if contacts:
                    existing = set(institution.contact.split("\n")) if institution.contact else set()
                    merged = "\n".join(existing | contacts)
                    if merged != institution.contact:
                        institution.contact = merged; changed = True
                for attr, src in (("latitude", lat), ("longitude", lon),
                                   ("center_name", info.get("center_name")),
                                   ("speciality", info.get("speciality"))):
                    if src and not getattr(institution, attr):
                        setattr(institution, attr, src); changed = True
                if changed:
                    institution.save()
            institutions[name] = institution

        self.stdout.write(f"  Families: {len(families)}  Institutions: {len(institutions)}")
        return families, institutions, unknown_inst

    # ==================================================================
    # Step 3 — Individuals + CrossIdentifiers
    # ==================================================================

    def _step3_individuals(self, rows, families, institutions, unknown_inst) -> set:
        self.stdout.write("Step 3: Individuals and cross identifiers…")
        all_individuals: set = set()
        registered = self.statuses["individual"].get("registered")

        for row in rows:
            lab_id = row.get("Özbek Lab. ID")
            full_name = row.get("Ad-Soyad")
            if not lab_id or not full_name:
                continue
            fid = get_family_id(lab_id)
            family = families.get(fid)
            if not family and not self.dry_run:
                self.stdout.write(self.style.WARNING(f"  Family missing for {lab_id} — skip"))
                continue

            if self.dry_run:
                self.stdout.write(f"  [DRY] {get_initials(full_name)} ({lab_id})")
                continue

            inst_raw = str(row.get("Gönderen Kurum/Birim") or "")
            inst_list = [institutions.get(n.strip(), unknown_inst)
                         for n in inst_raw.split(",") if n.strip()]
            inst_list = [i for i in inst_list if i] or ([unknown_inst] if unknown_inst else [])

            is_index = bool(re.search(r"\.1(\.|$)", str(lab_id)))

            tc_val = row.get("TC Kimlik No")
            if isinstance(tc_val, float):
                tc_val = int(tc_val)
            elif isinstance(tc_val, str):
                try:
                    tc_val = int(tc_val.strip()) if tc_val.strip() else None
                except ValueError:
                    tc_val = None
            else:
                tc_val = None

            sex_val         = normalize_sex(row.get("Cinsiyet"))
            is_alive_val    = to_bool(row.get("Yaşıyor mu?"))
            is_affected_val = to_bool(row.get("Etkilenmiş mi?"))
            age_of_onset    = str(row.get("Age of Onset") or "").strip()
            council_date    = parse_date(row.get("Konsey Tarihi"))
            diagnosis       = str(row.get("Tanı") or "").strip()
            diagnosis_date  = parse_date(row.get("Tanı Tarihi"))
            birth_date      = parse_date(row.get("Doğum Tarihi"))
            icd11_code      = str(row.get("ICD11") or "").strip()
            consanguinity   = to_bool(row.get("Akrabalık"))
            registration_date = parse_date(row.get("Geliş Tarihi"))

            individual = Individual.objects.filter(
                cross_ids__id_value=str(lab_id)).first()
            if not individual and family:
                individual = Individual.objects.filter(
                    full_name=full_name, family=family).first()

            if not individual:
                individual = Individual.objects.create(
                    full_name=full_name, family=family,
                    birth_date=birth_date, icd11_code=icd11_code,
                    is_index=is_index, tc_identity=tc_val,
                    sex=sex_val or "",
                    is_alive=True if is_alive_val is None else is_alive_val,
                    is_affected=False if is_affected_val is None else is_affected_val,
                    age_of_onset=age_of_onset, council_date=council_date,
                    diagnosis=diagnosis, diagnosis_date=diagnosis_date,
                    registration_date=registration_date,
                    created_by=self.admin_user,
                )
                if registered:
                    individual.statuses.set([registered])
                self.stdout.write(self.style.SUCCESS(
                    f"  Created: {get_initials(full_name)} ({lab_id})"))
            else:
                changed = False
                for attr, val in (
                    ("birth_date", birth_date), ("icd11_code", icd11_code),
                    ("tc_identity", tc_val), ("age_of_onset", age_of_onset),
                    ("council_date", council_date), ("diagnosis", diagnosis),
                    ("diagnosis_date", diagnosis_date),
                    ("registration_date", registration_date),
                ):
                    if val and not getattr(individual, attr):
                        setattr(individual, attr, val); changed = True
                if sex_val and not individual.sex:
                    individual.sex = sex_val; changed = True
                if is_alive_val is not None and individual.is_alive != is_alive_val:
                    individual.is_alive = is_alive_val; changed = True
                if is_affected_val is not None and individual.is_affected != is_affected_val:
                    individual.is_affected = is_affected_val; changed = True
                if individual.is_index != is_index:
                    individual.is_index = is_index; changed = True
                if changed:
                    individual.save()

            if inst_list:
                individual.institution.set(inst_list)

            if consanguinity is not None and family and family.is_consanguineous != consanguinity:
                family.is_consanguineous = consanguinity
                family.save()

            # Physician from "Klinisyen & İletişim Bilgileri" (before the "/")
            klinisyen_raw = str(row.get("Klinisyen & İletişim Bilgileri") or "")
            if klinisyen_raw:
                clinician_name = klinisyen_raw.split("/", 1)[0].strip()
                if clinician_name:
                    physician = get_or_create_user(clinician_name, self.admin_user)
                    individual.physicians.add(physician)

            hpo_terms = get_hpo_terms(row.get("HPO kodları"), self.stdout)
            if hpo_terms:
                individual.hpo_terms.add(*hpo_terms)

            # Projects
            projects_field = row.get("Projeler")
            if projects_field:
                for pname in [p.strip() for p in str(projects_field).split(",") if p.strip()]:
                    project, _ = Project.objects.get_or_create(
                        name=pname,
                        defaults={"created_by": self.admin_user, "priority": "medium"})
                    project.individuals.add(individual)

            # Notes
            parse_and_add_notes(row.get("Kurum Notları"), individual, self.admin_user)
            parse_and_add_notes(row.get("Takip Notları"), individual, self.admin_user)
            parse_and_add_notes(row.get("Genel Notlar/Sonuçlar"), individual, self.admin_user)
            parse_and_add_notes(row.get("İleri tetkik / planlanan"), individual, self.admin_user)
            tamamlanan = row.get("Tamamlanan Tetkik")
            if tamamlanan:
                parse_and_add_notes(
                    f"Tamamlanan tetkikler\n{tamamlanan}", individual, self.admin_user)

            # CrossIdentifiers
            rb_type = self.id_types.get("RareBoost")
            if rb_type:
                CrossIdentifier.objects.get_or_create(
                    individual=individual, id_type=rb_type,
                    defaults={"id_value": str(lab_id), "created_by": self.admin_user})
            bb_type = self.id_types.get("Biobank")
            bb_val = row.get("Biyobanka ID")
            if bb_type and bb_val:
                CrossIdentifier.objects.get_or_create(
                    individual=individual, id_type=bb_type,
                    defaults={"id_value": str(bb_val), "created_by": self.admin_user})

            # Other IDs column: "IDType:IDValue, IDType2:IDValue2"
            self._parse_other_ids(row.get("Other IDs"), individual)

            all_individuals.add(individual)

        self.stdout.write(f"  Individuals: {len(all_individuals)}")
        return all_individuals

    def _parse_other_ids(self, raw, individual):
        if not raw:
            return
        for pair in str(raw).split(","):
            pair = pair.strip()
            if ":" not in pair:
                continue
            id_type_name, id_value = pair.split(":", 1)
            id_type_name = id_type_name.strip()
            id_value = id_value.strip()
            if not id_type_name or not id_value:
                continue
            id_type, _ = IdentifierType.objects.get_or_create(
                name=id_type_name,
                defaults={"description": f"{id_type_name} identifier",
                          "created_by": self.admin_user})
            CrossIdentifier.objects.get_or_create(
                individual=individual, id_type=id_type,
                defaults={"id_value": id_value, "created_by": self.admin_user})

    # ==================================================================
    # Step 4 — Samples
    # ==================================================================

    def _step4_samples(self, rows) -> None:
        self.stdout.write("Step 4: Samples…")
        available = self.statuses["sample"]["available"]
        pending   = self.statuses["sample"]["pending_blood"]

        for row in rows:
            lab_id = row.get("Özbek Lab. ID")
            if not lab_id:
                continue
            individual = Individual.objects.filter(
                cross_ids__id_value=str(lab_id)).first()
            if not individual:
                continue

            sample_types_raw = str(row.get("Örnek Tipi") or "")
            for sample_type_name in [s.strip() for s in sample_types_raw.split(",") if s.strip()]:
                if self.dry_run:
                    self.stdout.write(f"  [DRY] Sample {sample_type_name} for {lab_id}")
                    continue

                sample_type = get_or_create_sample_type(sample_type_name, self.admin_user)
                # renamed column: "Saklandığı/İzole edildiği yer"
                isolation_by = get_or_create_user(
                    row.get("Saklandığı/İzole edildiği yer"), self.admin_user)
                receipt_date = parse_date(row.get("Geliş Tarihi"))  # same col as registration_date

                if sample_type_name in ("Tam Kan", "Tam Kan/Serum"):
                    existing = Sample.objects.filter(
                        individual=individual,
                        sample_type__name__in=("Tam Kan", "Tam Kan/Serum")).first()
                else:
                    existing = Sample.objects.filter(
                        individual=individual, sample_type=sample_type).first()

                measurements_raw = row.get("Örnek gön.& OD değ.")
                measurements = str(measurements_raw or "").strip()

                if existing:
                    changed = False
                    if receipt_date and not existing.receipt_date:
                        existing.receipt_date = receipt_date; changed = True
                    if measurements and not existing.sample_measurements:
                        existing.sample_measurements = measurements; changed = True
                    if not existing.isolation_by_id:
                        existing.isolation_by = isolation_by; changed = True
                    if changed:
                        existing.save()
                    if available and existing.receipt_date and not existing.statuses.exists():
                        existing.statuses.set([available])
                    sample = existing
                else:
                    sample = Sample.objects.create(
                        individual=individual, sample_type=sample_type,
                        receipt_date=receipt_date,
                        sample_measurements=measurements,
                        isolation_by=isolation_by,
                        created_by=self.admin_user,
                    )
                    sample.statuses.set([available if receipt_date else pending])

                parse_and_add_notes(row.get("Örnek Notları"), sample, self.admin_user)

    # ==================================================================
    # Step 5 — Analiz Takip → Test + Analysis (pipeline linked later)
    # ==================================================================

    def _step5_analiz_takip(self, wb) -> None:
        self.stdout.write("Step 5: Analiz Takip…")
        try:
            ws = wb["Analiz Takip"]
        except KeyError:
            self.stdout.write(self.style.WARNING("  Sheet 'Analiz Takip' not found."))
            return

        raw_headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        headers = [h for h in raw_headers if h is not None]
        leftover_rows = []

        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(c is None for c in row):
                continue
            d = dict(zip(headers, row[:len(headers)]))
            lab_id = d.get("Özbek Lab. ID")
            if not lab_id:
                leftover_rows.append(d); continue

            individual = Individual.objects.filter(
                cross_ids__id_value=str(lab_id)).first()
            if not individual:
                self.stdout.write(self.style.WARNING(
                    f"  Analiz Takip: no individual for {lab_id}"))
                leftover_rows.append(d); continue

            # VERİ KAYNAĞI is a single value (strip only)
            tt_name = str(d.get("VERİ KAYNAĞI") or "").strip()
            if not tt_name:
                leftover_rows.append(d); continue

            if self.dry_run:
                self.stdout.write(f"  [DRY] Test+Analysis for {lab_id} / {tt_name}")
                continue

            sample = individual.samples.first() or self._get_placeholder_sample(individual)

            data_receipt_date = parse_date(d.get("Data Geliş Tarihi"))

            # Test.performed_by is now FK → Institution
            inst_name = str(d.get("Verinin Geldiği Merkez") or "").strip()
            test_inst = None
            if inst_name:
                test_inst, _ = Institution.objects.get_or_create(
                    name=inst_name,
                    defaults={"created_by": self.admin_user})

            test_type = get_or_create_test_type(tt_name, self.admin_user)
            test, test_created = Test.objects.get_or_create(
                sample=sample, test_type=test_type,
                defaults={
                    "data_receipt_date": data_receipt_date,
                    "performed_by": test_inst,
                    "created_by": self.admin_user,
                },
            )
            if test_created:
                test_completed = self.statuses["test"].get("completed")
                if test_completed:
                    test.statuses.set([test_completed])
            else:
                if data_receipt_date and not test.data_receipt_date:
                    test.data_receipt_date = data_receipt_date
                    test.save()

            # Notes on test
            parse_and_add_notes(d.get("Data Notları"), test, self.admin_user)
            parse_and_add_notes(d.get("Veri İçeriği"), test, self.admin_user)
            parse_and_add_notes(d.get("Veri Notları"), test, self.admin_user)

            # Performed_by for Analysis (union of two columns)
            performers = self._parse_analysis_performers(
                d.get("ANALİZİ KİMLER YAPTI?"), d.get("Analizi Yapan"))

            analiz_tarihi  = parse_date(d.get("Reanaliz bitiş tarihi/ayça bitirdiğinde"))
            analiz_turu    = str(d.get("Analiz Türü") or "").strip()
            analiz_durumu  = str(d.get("Analiz Durumu") or "").strip()
            analysis_type  = get_or_create_analysis_type(analiz_turu, self.admin_user) \
                             if analiz_turu else None

            # Analysis — pipeline=None for now; linked by Gennext step
            analysis = Analysis.objects.create(
                pipeline=None,
                type=analysis_type,
                performed_date=analiz_tarihi,
                created_by=self.admin_user,
            )
            if performers:
                analysis.performed_by.set(performers)

            if analiz_durumu:
                nl = analiz_durumu.lower()
                a_st = (self.statuses["analysis"]["completed"] if "complet" in nl
                        else self.statuses["analysis"]["in_progress"] if "progress" in nl
                        else self.statuses["analysis"]["pending_data"])
                if a_st:
                    analysis.statuses.set([a_st])

            # Notes on Analysis (Test Notları goes HERE, not on Test)
            parse_and_add_notes(d.get("Test Notları"), analysis, self.admin_user)
            plan_note = "\n".join(filter(None, [
                str(d.get("PLAN") or "").strip(),
                str(d.get("ANALİZ STATUS") or "").strip(),
            ]))
            if plan_note:
                parse_and_add_notes(plan_note, analysis, self.admin_user)

            self.analysis_map[(str(lab_id), tt_name)] = analysis

        if leftover_rows:
            self.stdout.write(self.style.WARNING(
                f"  {len(leftover_rows)} Analiz Takip rows could not be matched."))
        self.stdout.write(f"  Analyses created: {len(self.analysis_map)}")

    def _parse_analysis_performers(self, field1, field2) -> list:
        """Union of two performer columns → list of User objects."""
        names: set = set()
        for raw in (field1, field2):
            if not raw:
                continue
            for name in re.split(r"[,\n]", str(raw)):
                name = name.strip()
                if name:
                    names.add(name)
        users = []
        for name in sorted(names):
            users.append(get_or_create_user(name, self.admin_user))
        return users

    # ==================================================================
    # Step 6 — RarePipe TSV (external file, legacy)
    # ==================================================================

    def _step6_rarepipe(self, tsv_path_str: str) -> None:
        self.stdout.write(f"Step 6: RarePipe TSV {tsv_path_str}…")
        tsv_path = Path(tsv_path_str)
        if not tsv_path.exists():
            self.stdout.write(self.style.ERROR(f"  Not found: {tsv_path}")); return

        rows = []
        with tsv_path.open(newline="", encoding="utf-8") as fh:
            for row in csv.reader(fh, delimiter="\t"):
                if any(row):
                    rows.append([c.strip() for c in row])

        versions = {row[4] for row in rows if len(row) >= 5 and row[4]}
        type_map = {v: get_or_create_pipeline_type("RarePipe", self.admin_user, version=v)
                    for v in versions}
        id_map = build_id_map()
        p_completed = self.statuses["pipeline"].get("completed")
        created = skipped = errors = 0

        for i, row in enumerate(rows, start=1):
            if len(row) < 5:
                errors += 1; continue
            filename, output_loc, raw_id, input_loc, version = row[:5]
            if not version:
                errors += 1; continue
            try:
                performed_date = parse_date_from_filename(filename)
            except ValueError as exc:
                self.stdout.write(self.style.ERROR(f"  Row {i}: {exc}")); errors += 1; continue

            individual = id_map.get(normalize_id(raw_id))
            if not individual:
                skipped += 1; continue

            test = (
                Test.objects.filter(sample__individual=individual,
                                    test_type__name__icontains="WGS").order_by("id").first()
                or Test.objects.filter(sample__individual=individual,
                                       test_type__name__icontains="WES").order_by("id").first()
            )
            if not test:
                skipped += 1; continue

            pipeline_type = type_map[version]
            if Pipeline.objects.filter(test=test, type=pipeline_type,
                                        performed_date=performed_date,
                                        output_location=output_loc).exists():
                skipped += 1; continue

            if self.dry_run:
                created += 1; continue

            pipeline = Pipeline.objects.create(
                test=test, performed_date=performed_date, performed_by=self.admin_user,
                type=pipeline_type, input_location=input_loc, output_location=output_loc,
                created_by=self.admin_user)
            if p_completed:
                pipeline.statuses.set([p_completed])
            Analysis.objects.get_or_create(
                pipeline=pipeline,
                defaults={"created_by": self.admin_user})
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"  RarePipe TSV: created={created} skipped={skipped} errors={errors}"))

    # ==================================================================
    # Step 7 — Parent links
    # ==================================================================

    def _step7_parent_links(self, families: dict) -> None:
        self.stdout.write("Step 7: Parent links…")
        updated = 0
        for fam_obj in families.values():
            code_to_ind: dict = {}
            for ind in fam_obj.individuals.all():
                lab_id_val = ind.primary_id
                if not lab_id_val or str(lab_id_val).upper().startswith("NO "):
                    continue
                parts = str(lab_id_val).split(".")
                if len(parts) < 2:
                    continue
                code = ".".join(parts[1:])
                code_to_ind.setdefault(code, ind)

            mother = code_to_ind.get("2")
            father = code_to_ind.get("3")
            if not mother and not father:
                continue
            for code, child in code_to_ind.items():
                if not (code == "1" or code.startswith("1.")):
                    continue
                changed = False
                if mother and child.mother_id != mother.id and child.id != mother.id:
                    child.mother = mother; changed = True
                if father and child.father_id != father.id and child.id != father.id:
                    child.father = father; changed = True
                if changed:
                    child.save(); updated += 1
        self.stdout.write(self.style.SUCCESS(f"  Updated: {updated}"))

    # ==================================================================
    # Step 8 — Sanger Konfirmasyonları
    # ==================================================================

    def _step_sanger(self, wb) -> None:
        self.stdout.write("Step 8: Sanger Konfirmasyonları…")
        sanger_type = get_or_create_test_type("Sanger", self.admin_user)
        created = skipped = 0
        for d in self._ws_rows(wb, "Sanger Konfirmasyonları"):
            lab_id = str(d.get("Özbek Lab. ID") or "").strip()
            if not lab_id:
                skipped += 1; continue
            individual = Individual.objects.filter(
                cross_ids__id_value=lab_id).first()
            if not individual:
                skipped += 1; continue
            if self.dry_run:
                created += 1; continue

            sample = individual.samples.first() or self._get_placeholder_sample(individual)
            test, test_created = Test.objects.get_or_create(
                sample=sample, test_type=sanger_type,
                defaults={"created_by": self.admin_user})
            if test_created:
                self.statuses["test"].get("completed") and \
                    test.statuses.set([self.statuses["test"]["completed"]])

            note_lines = "\n".join(filter(None, [
                str(d.get("Chromosomal Position") or "").strip(),
                str(d.get("Sanger Conf. Status") or "").strip(),
            ]))
            parse_and_add_notes(note_lines, test, self.admin_user)
            created += 1
        self.stdout.write(f"  Sanger: created={created} skipped={skipped}")

    # ==================================================================
    # Step 9 — WGS_TÜSEB
    # ==================================================================

    def _step_wgs_tuseb(self, wb) -> None:
        self.stdout.write("Step 9: WGS_TÜSEB…")
        project, _ = Project.objects.get_or_create(
            name="WGS - TÜSEB",
            defaults={"created_by": self.admin_user, "priority": "medium"})
        wgs_type = get_or_create_test_type("WGS", self.admin_user)
        completed  = self.statuses["test"].get("completed")
        awaiting   = self.statuses["test"].get("awaiting")
        id_map = build_id_map()
        bb_type = self.id_types.get("Biobank")

        measurement_cols = [
            "Total Hacim ( ul)", "Nanodrop Ölçümü (ng/ul)",
            "A260/280", "A260/230", "Qubit Ölçümü",
        ]
        created = skipped = 0

        for d in self._ws_rows(wb, "WGS_TÜSEB"):
            lab_id = str(d.get("Özbek Lab. ID") or "").strip()
            individual = None
            if lab_id:
                individual = Individual.objects.filter(
                    cross_ids__id_value=lab_id).first()
            if not individual and bb_type:
                bb_val = str(d.get("Biyobanka ID") or "").strip()
                if bb_val:
                    individual = Individual.objects.filter(
                        cross_ids__id_type=bb_type,
                        cross_ids__id_value=bb_val).first()
            if not individual:
                skipped += 1; continue
            if self.dry_run:
                created += 1; continue

            project.individuals.add(individual)
            sample = individual.samples.first() or self._get_placeholder_sample(individual)

            # Consolidated measurements
            parts = [f"{col}: {d[col]}"
                     for col in measurement_cols
                     if d.get(col) is not None and str(d.get(col)).strip()]
            measurements = " | ".join(parts)

            test, test_created = Test.objects.get_or_create(
                sample=sample, test_type=wgs_type,
                defaults={
                    "service_send_date": parse_date(d.get("Dizilemeye Gönderilme Tarihi")),
                    "data_receipt_date": parse_date(d.get("Data Gelme Tarihi")),
                    "created_by": self.admin_user,
                })
            if test_created and measurements:
                sample.sample_measurements = (
                    (sample.sample_measurements + " | " if sample.sample_measurements else "")
                    + measurements)
                sample.save()

            # Status
            status_raw = str(d.get("Data Geliş Durumu") or "").strip().lower()
            if status_raw == "geldi":
                test_status = completed
            elif status_raw == "data bekleniyor":
                test_status = awaiting
            else:
                test_status = None
            if test_status and not test.statuses.exists():
                test.statuses.set([test_status])

            parse_and_add_notes(d.get("Data Notları"), test, self.admin_user)
            created += 1

        self.stdout.write(f"  WGS_TÜSEB: created={created} skipped={skipped}")

    # ==================================================================
    # Step 10 — External
    # ==================================================================

    def _step_external(self, wb, kurumlar_map) -> None:
        self.stdout.write("Step 10: External individuals…")
        created_count = skipped = 0

        for d in self._ws_rows(wb, "External"):
            id_type_name = str(d.get("ID Type") or "").strip()
            id_value     = str(d.get("ID Value") or "").strip()
            full_name    = str(d.get("Ad-Soyad") or "").strip()
            if not id_type_name or not id_value or not full_name:
                skipped += 1; continue
            if self.dry_run:
                self.stdout.write(f"  [DRY] External: {full_name}")
                created_count += 1; continue

            # One family per individual (family_id = sanitized id_value)
            fam_id = re.sub(r"[^A-Za-z0-9_\-]", "_", id_value)
            family, _ = Family.objects.get_or_create(
                family_id=fam_id, defaults={"created_by": self.admin_user})

            # Institution
            inst_raw = str(d.get("Gönderen Kurum/Birim") or "")
            inst_list = []
            for name in [n.strip() for n in inst_raw.split(",") if n.strip()]:
                info = kurumlar_map.get(name, {})
                lat, lon = info.get("coords", (None, None)) if "coords" in info else (None, None)
                inst, _ = Institution.objects.get_or_create(
                    name=name,
                    defaults={
                        "contact": "", "created_by": self.admin_user,
                        "latitude": lat or 0.0, "longitude": lon or 0.0,
                        "city": info.get("city", ""), "official_name": info.get("official_name", ""),
                    })
                inst_list.append(inst)

            tc_val = d.get("TC Kimlik No")
            if isinstance(tc_val, float):
                tc_val = int(tc_val)
            elif isinstance(tc_val, str):
                try:
                    tc_val = int(tc_val.strip()) if tc_val.strip() else None
                except ValueError:
                    tc_val = None
            else:
                tc_val = None

            # Cross-ID type
            ext_id_type, _ = IdentifierType.objects.get_or_create(
                name=id_type_name,
                defaults={"description": id_type_name, "created_by": self.admin_user})

            individual = Individual.objects.filter(
                cross_ids__id_type=ext_id_type, cross_ids__id_value=id_value).first()

            if not individual:
                individual = Individual.objects.create(
                    full_name=full_name, family=family,
                    birth_date=parse_date(d.get("Doğum Tarihi")),
                    icd11_code=str(d.get("ICD11") or ""),
                    is_index=True, tc_identity=tc_val,
                    council_date=parse_date(d.get("Konsey Tarihi")),
                    created_by=self.admin_user)
                if self.statuses["individual"].get("registered"):
                    individual.statuses.set([self.statuses["individual"]["registered"]])

            if inst_list:
                individual.institution.set(inst_list)

            CrossIdentifier.objects.get_or_create(
                individual=individual, id_type=ext_id_type,
                defaults={"id_value": id_value, "created_by": self.admin_user})

            bb_type = self.id_types.get("Biobank")
            bb_val = str(d.get("Biyobanka ID") or "").strip()
            if bb_type and bb_val:
                CrossIdentifier.objects.get_or_create(
                    individual=individual, id_type=bb_type,
                    defaults={"id_value": bb_val, "created_by": self.admin_user})

            self._parse_other_ids(d.get("Other IDs"), individual)

            # Physician
            klinisyen_raw = str(d.get("Klinisyen & İletişim Bilgileri") or "")
            if klinisyen_raw:
                clinician_name = klinisyen_raw.split("/", 1)[0].strip()
                if clinician_name:
                    individual.physicians.add(
                        get_or_create_user(clinician_name, self.admin_user))

            hpo_terms = get_hpo_terms(d.get("HPO kodları"), self.stdout)
            if hpo_terms:
                individual.hpo_terms.add(*hpo_terms)

            # Sample
            receipt_date = parse_date(d.get("Geliş Tarihi/ay/gün/yıl"))
            sample_type_name = str(d.get("Örnek Tipi") or "").strip()
            sample = None
            if sample_type_name:
                sample_type = get_or_create_sample_type(sample_type_name, self.admin_user)
                isolation_by = get_or_create_user(
                    d.get("İzolasyonu yapan"), self.admin_user)
                measurements = str(d.get("Örnek gön.& OD değ.") or "").strip()
                sample, s_created = Sample.objects.get_or_create(
                    individual=individual, sample_type=sample_type,
                    defaults={
                        "receipt_date": receipt_date,
                        "sample_measurements": measurements,
                        "isolation_by": isolation_by,
                        "created_by": self.admin_user,
                    })
                if s_created:
                    avail = self.statuses["sample"]["available"]
                    pend  = self.statuses["sample"]["pending_blood"]
                    sample.statuses.set([avail if receipt_date else pend])
                parse_and_add_notes(d.get("Örnek Notları"), sample, self.admin_user)

            # Test
            test_name = str(d.get("Çalışılan Test Adı") or "").strip()
            if test_name and sample:
                tt = get_or_create_test_type(test_name, self.admin_user)
                test, t_created = Test.objects.get_or_create(
                    sample=sample, test_type=tt,
                    defaults={
                        "performed_date": parse_date(d.get("Çalışılma Tarihi")),
                        "service_send_date": parse_date(d.get("Hiz.Alım.Gön. Tarihi")),
                        "data_receipt_date": parse_date(d.get("Data Geliş tarihi")),
                        "created_by": self.admin_user,
                    })
                parse_and_add_notes(d.get("Test Notları"), test, self.admin_user)

            # Notes on individual
            for col in ("Kurum Notları", "Takip Notları",
                        "Genel Notlar/Sonuçlar", "İleri tetkik / planlanan"):
                parse_and_add_notes(d.get(col), individual, self.admin_user)
            tamamlanan = d.get("Tamamlanan Tetkik")
            if tamamlanan:
                parse_and_add_notes(
                    f"Tamamlanan tetkikler\n{tamamlanan}", individual, self.admin_user)

            # Projects
            projects_field = d.get("Projeler")
            if projects_field:
                for pname in [p.strip() for p in str(projects_field).split(",") if p.strip()]:
                    project, _ = Project.objects.get_or_create(
                        name=pname,
                        defaults={"created_by": self.admin_user, "priority": "medium"})
                    project.individuals.add(individual)

            created_count += 1

        self.stdout.write(f"  External: created/updated={created_count} skipped={skipped}")

    # ==================================================================
    # Step 11 — Long Read (Katar / Dubai)
    # ==================================================================

    def _step_long_read(self, wb, sheet_name: str, note_tag: str, project_name: str) -> None:
        self.stdout.write(f"Step 11 ({note_tag}): {sheet_name}…")
        project, _ = Project.objects.get_or_create(
            name=project_name,
            defaults={"created_by": self.admin_user, "priority": "medium"})
        lr_type = get_or_create_test_type("Long Read WGS", self.admin_user)
        sent_status = self.statuses["test"].get("sent")
        note_cols = [
            "Hastalık Grubu",
            "Biyobankada mevcut örnek tipleri",
            "Materyal",
            "Kalite Metrikleri",
        ]
        created = skipped = 0
        for d in self._ws_rows(wb, sheet_name):
            lab_id = str(d.get("RareBoost ID") or "").strip()
            if not lab_id:
                skipped += 1; continue
            individual = Individual.objects.filter(
                cross_ids__id_value=lab_id).first()
            if not individual:
                skipped += 1; continue
            if self.dry_run:
                created += 1; continue

            project.individuals.add(individual)
            sample = individual.samples.first() or self._get_placeholder_sample(individual)
            test, t_created = Test.objects.get_or_create(
                sample=sample, test_type=lr_type,
                defaults={"created_by": self.admin_user})
            if t_created and sent_status:
                test.statuses.set([sent_status])

            lines = [note_tag]
            for col in note_cols:
                val = str(d.get(col) or "").strip()
                if val:
                    lines.append(f"{col}: {val}")
            parse_and_add_notes("\n".join(lines), test, self.admin_user)
            created += 1
        self.stdout.write(f"  {note_tag}: created={created} skipped={skipped}")

    # ==================================================================
    # Step 12 — CP_COHORT
    # ==================================================================

    def _step_cp_cohort(self, wb) -> None:
        self.stdout.write("Step 12: CP_COHORT…")
        project, _ = Project.objects.get_or_create(
            name="CP Cohort",
            defaults={"created_by": self.admin_user, "priority": "medium"})
        added = 0
        for d in self._ws_rows(wb, "CP_COHORT"):
            lab_id = str(d.get("Özbek Lab. ID") or "").strip()
            if not lab_id:
                continue
            individual = Individual.objects.filter(
                cross_ids__id_value=lab_id).first()
            if not individual:
                continue
            if not self.dry_run:
                project.individuals.add(individual)
                parse_and_add_notes(d.get("Analiz Sonucu"), individual, self.admin_user)
            added += 1
        self.stdout.write(f"  CP_COHORT: {added} individuals")

    # ==================================================================
    # Step 13 — RNA SEQ
    # ==================================================================

    def _step_rna_seq(self, wb) -> None:
        self.stdout.write("Step 13: RNA SEQ…")
        rna_type = get_or_create_test_type("RNA Seq", self.admin_user)
        created = skipped = 0
        for d in self._ws_rows(wb, "RNA SEQ"):
            lab_id = str(d.get("Özbek Lab. ID") or "").strip()
            if not lab_id:
                skipped += 1; continue
            individual = Individual.objects.filter(
                cross_ids__id_value=lab_id).first()
            if not individual:
                skipped += 1; continue
            if self.dry_run:
                created += 1; continue

            sample = individual.samples.first() or self._get_placeholder_sample(individual)
            test, _ = Test.objects.get_or_create(
                sample=sample, test_type=rna_type,
                defaults={
                    "service_send_date": parse_date(d.get("Dizilemeye Gönderim Tarihi")),
                    "created_by": self.admin_user,
                })
            status_note = str(d.get(
                "Data Yüklenme Tarihi (G&More)/Status") or "").strip()
            if status_note:
                parse_and_add_notes(
                    f"Data Yüklenme Tarihi (G&More)/Status: {status_note}",
                    test, self.admin_user)
            parse_and_add_notes(d.get("Notlar"), test, self.admin_user)
            created += 1
        self.stdout.write(f"  RNA SEQ: created={created} skipped={skipped}")

    # ==================================================================
    # Step 14 — Gennext Analiz Listesi (creates Pipelines, links analyses)
    # ==================================================================

    def _step_gennext_analiz(self, wb) -> None:
        self.stdout.write("Step 14: Gennext Analiz Listesi…")
        gennext_type = get_or_create_pipeline_type("Gennext", self.admin_user)
        p_completed  = self.statuses["pipeline"].get("completed")
        created = skipped = errors = 0

        for d in self._ws_rows(wb, "Gennext Analiz Listesi"):
            lab_id = str(d.get("Gennext RBID") or "").strip()
            if not lab_id:
                skipped += 1; continue
            performed_date = parse_date(d.get("Gennext Date"))
            if not performed_date:
                self.stdout.write(self.style.WARNING(
                    f"  Gennext: no date for {lab_id} — skipping"))
                skipped += 1; continue

            individual = Individual.objects.filter(
                cross_ids__id_value=lab_id).first()
            if not individual:
                skipped += 1; continue

            test = (
                Test.objects.filter(sample__individual=individual,
                                    test_type__name__icontains="WES").order_by("id").first()
                or Test.objects.filter(sample__individual=individual,
                                       test_type__name__icontains="WGS").order_by("id").first()
            )
            if not test:
                self.stdout.write(self.style.WARNING(
                    f"  Gennext: no WES/WGS test for {lab_id}"))
                skipped += 1; continue

            output_loc = str(d.get("Gennext Hash") or "").strip()
            if Pipeline.objects.filter(test=test, type=gennext_type,
                                        performed_date=performed_date).exists():
                skipped += 1; continue

            if self.dry_run:
                created += 1; continue

            try:
                pipeline = Pipeline.objects.create(
                    test=test, performed_date=performed_date,
                    performed_by=self.admin_user,
                    type=gennext_type, output_location=output_loc,
                    created_by=self.admin_user)
                if p_completed:
                    pipeline.statuses.set([p_completed])

                parse_and_add_notes(d.get("Gennext"), pipeline, self.admin_user)

                # Link an unlinked Analysis from analysis_map for this individual
                tt_name = test.test_type.name
                analysis = self.analysis_map.get((str(lab_id), tt_name))
                if analysis and analysis.pipeline_id is None:
                    analysis.pipeline = pipeline
                    analysis.save()

                created += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  Gennext error {lab_id}: {exc}"))
                errors += 1

        self.stdout.write(self.style.SUCCESS(
            f"  Gennext: created={created} skipped={skipped} errors={errors}"))

    # ==================================================================
    # Step 15 — RarePipe Analiz Listesi (⚠ INCOMPLETE — no date column)
    # ==================================================================

    def _step_rarepipe_analiz(self, wb) -> None:
        self.stdout.write(self.style.WARNING(
            "Step 15: RarePipe Analiz Listesi — ⚠ SKIPPED.\n"
            "  Reminder: add a Pipeline date column (and output location) to this sheet, "
            "then re-implement this step. (Q10)"))

    # ==================================================================
    # Step 16 — Variant List
    # ==================================================================

    def _step_variants(self, wb) -> None:
        self.stdout.write("Step 16: Variant List…")
        variant_ws = None
        for sheet_name in wb.sheetnames:
            if sheet_name == "Variant List":
                variant_ws = wb[sheet_name]
                break
        if not variant_ws:
            self.stdout.write(self.style.WARNING("  Sheet 'Variant List' not found."))
            return

        variant_ct = ContentType.objects.get_for_model(Variant)
        headers = [c.value for c in next(variant_ws.iter_rows(min_row=1, max_row=1))]
        imported = skipped = errors = 0

        for row in variant_ws.iter_rows(min_row=2, values_only=True):
            if all(c is None for c in row):
                continue
            d = dict(zip(headers, row))
            lab_id = str(d.get("Özbek Lab. ID") or "").strip()
            if not lab_id:
                continue

            individual = Individual.objects.filter(
                cross_ids__id_value=lab_id).first()
            if not individual:
                skipped += 1; continue

            # Zygosity — strict mapping, skip if unrecognised
            zyg = _map_zygosity_strict(
                d.get("Zygosity"),
                warn_fn=lambda msg: self.stdout.write(self.style.WARNING(msg)))
            if zyg is None:
                errors += 1; continue

            parsed = parse_variant_string(d.get("Chromosomal Position"))
            if not parsed:
                # ⚠ CNV/SV/Repeat formats not yet implemented (Q5 — ask after implementation)
                self.stdout.write(self.style.WARNING(
                    f"  Cannot parse '{d.get('Chromosomal Position')}' for {lab_id} "
                    f"— CNV/SV/Repeat formats not yet implemented."))
                errors += 1; continue

            chrom, start_str, ref, alt = parsed

            if self.dry_run:
                imported += 1; continue

            # First analysis for this individual (no Veri Kaynağı mapping available)
            analysis = Analysis.objects.filter(
                pipeline__test__sample__individual=individual).order_by("id").first()
            # Fallback: check analysis_map
            if analysis is None:
                for (lid, _), a in self.analysis_map.items():
                    if lid == str(lab_id):
                        analysis = a; break

            try:
                snv, created_snv = SNV.objects.get_or_create(
                    individual=individual,
                    chromosome=chrom,
                    start=int(start_str),
                    reference=ref,
                    alternate=alt,
                    defaults={
                        "end": int(start_str),
                        "zygosity": zyg,
                        "analysis": analysis,
                        "created_by": self.admin_user,
                    })
                if not created_snv and analysis and snv.analysis_id != analysis.id:
                    snv.analysis = analysis; snv.save()

                # Statuses (created on the fly; no fixed list yet — Q6)
                varyant_durumu = str(d.get("Statuses") or "").strip()
                if varyant_durumu and created_snv:
                    v_st = get_or_create_status(
                        varyant_durumu, "", "gray", self.admin_user, variant_ct)
                    if v_st:
                        snv.statuses.set([v_st])

                imported += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  Variant error {lab_id}: {exc}"))
                errors += 1

        self.stdout.write(self.style.SUCCESS(
            f"  Variants: imported={imported} skipped={skipped} errors={errors}"))

    # ==================================================================
    # Step 18 — File attachments
    # ==================================================================

    def _step_file_attachments(self, forms_dir_str, reports_dir_str) -> None:
        self.stdout.write("Step 18: File attachments…")
        id_regex = re.compile(r"^(RB_\d{4}_[\d\.]+)")

        if forms_dir_str:
            forms_dir = Path(forms_dir_str)
            if forms_dir.exists():
                for fp in sorted(forms_dir.glob("*")):
                    if not fp.is_file() or fp.name.startswith("."): continue
                    m = id_regex.match(fp.name)
                    if not m: continue
                    ind = Individual.objects.filter(
                        cross_ids__id_type__name="RareBoost",
                        cross_ids__id_value=m.group(1)).first()
                    if not ind: continue
                    if AnalysisRequestForm.objects.filter(file__endswith=fp.name).exists(): continue
                    if self.dry_run:
                        self.stdout.write(f"  [DRY] form: {fp.name}"); continue
                    with open(fp, "rb") as fh:
                        form_obj = AnalysisRequestForm(
                            individual=ind,
                            description=f"Imported from {fp.name}",
                            created_by=self.admin_user)
                        form_obj.file.save(fp.name, File(fh))
                        form_obj.save()

        if reports_dir_str:
            reports_dir = Path(reports_dir_str)
            if reports_dir.exists():
                for fp in sorted(reports_dir.glob("*")):
                    if not fp.is_file() or fp.name.startswith("."): continue
                    m = id_regex.match(fp.name)
                    if not m: continue
                    ind = Individual.objects.filter(
                        cross_ids__id_type__name="RareBoost",
                        cross_ids__id_value=m.group(1)).first()
                    if not ind: continue
                    if AnalysisReport.objects.filter(file__endswith=fp.name).exists(): continue
                    fn_lower = fp.name.lower()
                    pqs = Pipeline.objects.filter(test__sample__individual=ind)
                    target = (
                        pqs.filter(type__name__icontains="wgs").last() if "wgs" in fn_lower
                        else pqs.filter(type__name__icontains="wes").last() if "wes" in fn_lower
                        else pqs.filter(type__name__icontains="sanger").last() if "sanger" in fn_lower
                        else pqs.last())
                    if not target: continue
                    if self.dry_run:
                        self.stdout.write(f"  [DRY] report: {fp.name}"); continue
                    with open(fp, "rb") as fh:
                        # Find or create an Analysis on this pipeline
                        target_analysis = target.analyses.first()
                        if not target_analysis:
                            target_analysis = Analysis.objects.create(
                                pipeline=target,
                                created_by=self.admin_user,
                            )
                        rep = AnalysisReport(
                            analysis=target_analysis,
                            description=f"Imported from {fp.name}",
                            created_by=self.admin_user)
                        rep.file.save(fp.name, File(fh))
                        rep.save()

    # ==================================================================
    # Step 20 — Yayın_İçi
    # ==================================================================

    def _step_yayin_ici(self, yayin_ici_path: str) -> None:
        self.stdout.write(f"Step 20: Yayın_İçi ({yayin_ici_path})…")
        if not os.path.exists(yayin_ici_path):
            self.stdout.write(self.style.ERROR(f"  File not found: {yayin_ici_path}")); return

        wb = openpyxl.load_workbook(yayin_ici_path, data_only=True)
        sheet_name = "GÜNCELyayıniciyedek"
        if sheet_name not in wb.sheetnames:
            self.stdout.write(self.style.ERROR(f"  Sheet '{sheet_name}' not found.")); return

        ws = wb[sheet_name]
        headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))
                   if c.value is not None]
        rb_type  = self.id_types.get("RareBoost")
        bb_type  = self.id_types.get("Biobank")
        ct_ind   = ContentType.objects.get_for_model(Individual)
        ct_test  = ContentType.objects.get_for_model(Test)
        updated = skipped = 0

        for vals in ws.iter_rows(min_row=2, values_only=True):
            if all(v is None for v in vals): continue
            d = dict(zip(headers, vals[:len(headers)]))

            # Lookup
            lab_id = str(d.get("RareBoost ID") or "").strip()
            individual = None
            if lab_id:
                qs = Individual.objects.filter(cross_ids__id_value=lab_id)
                if rb_type:
                    qs = qs.filter(cross_ids__id_type=rb_type)
                individual = qs.first()
            if not individual:
                bb_val = str(d.get("Biyobanka ID") or "").strip()
                if bb_val and bb_type:
                    individual = Individual.objects.filter(
                        cross_ids__id_type=bb_type, cross_ids__id_value=bb_val).first()
            if not individual:
                skipped += 1; continue
            if self.dry_run:
                updated += 1; continue

            changed = False
            # Demographic updates (only if missing)
            sex_val = normalize_sex(d.get("Sex"))
            if sex_val and not individual.sex:
                individual.sex = sex_val; changed = True
            alive_val = to_bool(d.get("Status (ex-alive)"))
            if alive_val is not None and individual.is_alive != alive_val:
                individual.is_alive = alive_val; changed = True
            dob = parse_date(d.get("Date of Birth"))
            if dob and not individual.birth_date:
                individual.birth_date = dob; changed = True
            aoo = str(d.get("Age of Onset") or "").strip()
            if aoo and not individual.age_of_onset:
                individual.age_of_onset = aoo; changed = True
            if changed:
                individual.save()

            # Consanguinity
            cons = to_bool(d.get("Consanguinity"))
            if cons is not None and individual.family and \
                    individual.family.is_consanguineous != cons:
                individual.family.is_consanguineous = cons
                individual.family.save()

            # Statuses (two separate columns)
            for col in ("Solved (P/LP and clinically relevant VUS), Candidate gene-variant, Unsolved",
                        "NOTE"):
                status_name = str(d.get(col) or "").strip()
                if status_name:
                    st = Status.objects.filter(
                        name=status_name, content_type=ct_ind).first()
                    if st and not individual.statuses.filter(pk=st.pk).exists():
                        individual.statuses.add(st)

            # Disease Group → project
            disease_group = str(d.get("Disease Group") or "").strip()
            if disease_group:
                for pg in [g.strip() for g in disease_group.split(",") if g.strip()]:
                    proj, _ = Project.objects.get_or_create(
                        name=pg,
                        defaults={"created_by": self.admin_user, "priority": "medium"})
                    proj.individuals.add(individual)

            # Institution
            geldi_merkez = str(d.get("Geldiği merkez") or "").strip()
            if geldi_merkez:
                inst, _ = Institution.objects.get_or_create(
                    name=geldi_merkez, defaults={"created_by": self.admin_user})
                individual.institution.add(inst)
                # Physicians for this institution
                klin_raw = str(d.get("Klinisyen & İletişim Bilgileri") or "")
                for klin in [k.strip() for k in klin_raw.split(",") if k.strip()]:
                    physician = get_or_create_user(klin, self.admin_user)
                    inst.staff.add(physician)

            # HPO
            hpo_terms = get_hpo_terms(d.get("HPO"), self.stdout)
            if hpo_terms:
                individual.hpo_terms.add(*hpo_terms)

            # OMIM note
            omim = str(d.get("OMIM") or "").strip()
            if omim:
                parse_and_add_notes(f"OMIM: {omim}", individual, self.admin_user)

            # Previous tests
            prev_raw = d.get("Previous test")
            if prev_raw:
                prev_status = Status.objects.filter(
                    name="Previous", content_type=ct_test).first()
                for tt_name in self._normalize_test_tokens(str(prev_raw)):
                    tt = get_or_create_test_type(tt_name, self.admin_user)
                    if not individual.get_all_tests().filter(test_type=tt).exists():
                        sample = (individual.samples.first()
                                  or self._get_placeholder_sample(individual))
                        test = Test.objects.create(
                            sample=sample, test_type=tt, created_by=self.admin_user)
                        if prev_status:
                            test.statuses.set([prev_status])

            # RareBoost Reanaliz/WGS/WES/RNA seq
            rb_raw = d.get("RareBoost Reanaliz/WGS/WES/RNA seq")
            if rb_raw:
                self._process_rb_reanaliz(individual, str(rb_raw))

            # Singleton-Trio notes on non-previous tests
            singleton_trio = str(d.get("Singleton-Trio") or "").strip()
            if singleton_trio:
                non_prev_tests = list(
                    individual.get_all_tests()
                    .exclude(statuses__name="Previous")
                    .order_by("id"))
                trio_values = [v.strip() for v in singleton_trio.split(",") if v.strip()]
                if not trio_values:
                    trio_values = [singleton_trio]
                last_val = trio_values[-1]
                for idx, test_obj in enumerate(non_prev_tests):
                    note_val = trio_values[idx] if idx < len(trio_values) else last_val
                    parse_and_add_notes(note_val, test_obj, self.admin_user)

            # Variant column — format unknown, skip and remind
            if d.get("Variant"):
                self.stdout.write(self.style.WARNING(
                    f"  Yayın_İçi: Variant column for {lab_id} skipped "
                    f"(format unknown — Q12, ask after implementation)"))

            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"  Yayın_İçi: updated={updated} skipped={skipped}"))

    def _normalize_test_tokens(self, text: str) -> list:
        """Split and normalise test type strings from the Previous test column."""
        text = text.replace('"Gene Panel, Single Gene"', "Targeted Panel")
        tokens = [t.strip() for t in text.replace("\n", ",").split(",") if t.strip()]
        result = []
        skip_next = False
        for i, tok in enumerate(tokens):
            if skip_next:
                skip_next = False; continue
            tl = tok.lower()
            if tl == "gene panel" and i + 1 < len(tokens) \
                    and tokens[i + 1].lower() == "single gene":
                result.append("Targeted Panel"); skip_next = True
            elif tl in {"wes", "wgs", "cma", "karyotype"}:
                result.append(tok.upper())
            elif tl in {"targeted panel", "gene panel single gene"}:
                result.append("Targeted Panel")
            elif tl in {"rna seq", "rnaseq", "rna-seq"}:
                result.append("RNA Seq")
            else:
                result.append(tok.strip('" '))
        return [r for r in result if r]

    def _process_rb_reanaliz(self, individual, text: str) -> None:
        """Handle the 'RareBoost Reanaliz/WGS/WES/RNA seq' column."""
        ct_test = ContentType.objects.get_for_model(Test)
        parts = [p.strip() for p in text.replace("\n", ",").split(",") if p.strip()]
        has_reanalysis = any(p.lower() in {"reanalysis", "wgs reanalysis"} for p in parts)
        if has_reanalysis:
            order = (["WGS", "WES", "Targeted Panel"]
                     if any(p.lower() == "wgs reanalysis" for p in parts)
                     else ["WES", "WGS", "Targeted Panel"])
            target_test = None
            for name in order:
                target_test = individual.get_all_tests().filter(
                    test_type__name=name).order_by("id").first()
                if target_test:
                    break
            if not target_test:
                wes_tt = get_or_create_test_type("WES", self.admin_user)
                sample = (individual.samples.first()
                          or self._get_placeholder_sample(individual))
                target_test = Test.objects.create(
                    sample=sample, test_type=wes_tt, created_by=self.admin_user)
                completed = Status.objects.filter(
                    name="Completed", content_type=ct_test).first()
                if completed:
                    target_test.statuses.set([completed])

            pipeline_type = get_or_create_pipeline_type("Reanalysis", self.admin_user)
            ct_pipeline = ContentType.objects.get_for_model(Pipeline)
            from datetime import date as date_cls
            pipeline = Pipeline.objects.create(
                test=target_test,
                performed_date=date_cls.today(),
                performed_by=self.admin_user,
                type=pipeline_type,
                created_by=self.admin_user)
            in_progress = Status.objects.filter(
                name="In Progress", content_type=ct_pipeline).first()
            if in_progress:
                pipeline.statuses.set([in_progress])

        for p in parts:
            if p.lower() in {"reanalysis", "wgs reanalysis"}:
                continue
            name = (p.upper() if p.lower() in {"wes", "wgs"}
                    else "RNA Seq" if p.lower() in {"rna seq", "rnaseq", "rna-seq"}
                    else "Targeted Panel" if p.lower() == "targeted panel"
                    else p)
            tt = get_or_create_test_type(name, self.admin_user)
            if not individual.get_all_tests().filter(test_type=tt).exists():
                sample = (individual.samples.first()
                          or self._get_placeholder_sample(individual))
                test = Test.objects.create(
                    sample=sample, test_type=tt, created_by=self.admin_user)
                completed = Status.objects.filter(
                    name="Completed", content_type=ct_test).first()
                if completed:
                    test.statuses.set([completed])

    # ==================================================================
    # Internal helpers
    # ==================================================================

    def _get_placeholder_sample(self, individual) -> Sample:
        existing = individual.samples.first()
        if existing:
            return existing
        placeholder_type = get_or_create_sample_type("Placeholder", self.admin_user)
        sample = Sample.objects.create(
            individual=individual,
            sample_type=placeholder_type,
            isolation_by=self.admin_user,
            created_by=self.admin_user)
        not_available = self.statuses["sample"].get("not_available")
        if not_available:
            sample.statuses.set([not_available])
        return sample
