"""Shared helper utilities extracted for reuse across data import management commands."""

import re
from datetime import datetime, date

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

User = get_user_model()


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def parse_date(value):
    """Parse a date from an Excel datetime object or various string formats."""
    if not value:
        return None
    if hasattr(value, 'date'):
        return value.date()
    if isinstance(value, str):
        for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d.%m.%Y'):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return None


def parse_date_from_filename(filename):
    """Extract a date from an 8-digit YYYYMMDD segment embedded in a filename."""
    match = re.search(r'(\d{8})', filename)
    if not match:
        raise ValueError(f'Cannot find 8-digit date in filename {filename!r}')
    raw = match.group(1)
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


# ---------------------------------------------------------------------------
# ID utilities
# ---------------------------------------------------------------------------

def get_family_id(lab_id):
    """Return the family-level prefix of a lab ID (everything before the first '.')."""
    if not lab_id:
        return None
    return str(lab_id).split('.')[0]


def normalize_id(value):
    """Replace '.', '_', '-' with '.' for separator-agnostic ID comparison."""
    return re.sub(r'[._\-]', '.', str(value))


def build_id_map():
    """Return {normalized_cross_id_value: Individual} built in bulk to avoid N+1 queries."""
    from lab.models import CrossIdentifier, Individual
    from django.db.models import F, Value
    from django.db.models.functions import Replace

    rows = (
        CrossIdentifier.objects
        .annotate(
            norm=Replace(
                Replace(
                    Replace(F('id_value'), Value('_'), Value('.')),
                    Value('-'), Value('.'),
                ),
                Value('..'), Value('.'),
            )
        )
        .select_related('individual')
        .values_list('norm', 'individual_id')
    )
    individual_ids = {ind_id for _, ind_id in rows}
    individuals = {i.id: i for i in Individual.objects.filter(id__in=individual_ids)}
    mapping: dict = {}
    for norm, ind_id in rows:
        if ind_id in individuals:
            mapping[norm] = individuals[ind_id]
    return mapping


# ---------------------------------------------------------------------------
# User / lookup helpers
# ---------------------------------------------------------------------------

def get_or_create_user(name, admin_user):
    """Normalise *name* to a username and get-or-create the User row."""
    if not name:
        return admin_user
    username = str(name).strip().lower().replace(' ', '_')
    user = User.objects.filter(username=username).first()
    if user:
        return user
    parts = str(name).strip().split()
    try:
        user = User.objects.create_user(
            username=username,
            email=f'{username}@example.com',
            password='changeme123',
            first_name=parts[0] if parts else name,
            last_name=parts[1] if len(parts) > 1 else '',
        )
    except Exception:
        user = User.objects.filter(username=username).first() or admin_user
    return user


def get_or_create_sample_type(name, admin_user):
    """Get or create a SampleType by name."""
    from lab.models import SampleType
    if not name:
        return None
    st, _ = SampleType.objects.get_or_create(name=name, defaults={'created_by': admin_user})
    return st


def get_or_create_test_type(name, admin_user):
    """Get or create a TestType by name."""
    from lab.models import TestType
    if not name:
        return None
    tt, _ = TestType.objects.get_or_create(name=name, defaults={'created_by': admin_user})
    return tt


def get_or_create_pipeline_type(name, admin_user, description='', version=''):
    """Get or create a PipelineType, optionally scoped by version."""
    from lab.models import PipelineType
    if not name:
        return None
    lookup = {'name': name}
    if version:
        lookup['version'] = version
    pt, _ = PipelineType.objects.get_or_create(
        **lookup,
        defaults={'description': description, 'created_by': admin_user},
    )
    return pt


def get_or_create_analysis_type(name, admin_user):
    """Get or create an AnalysisType by name."""
    from lab.models import AnalysisType
    if not name:
        return None
    at, _ = AnalysisType.objects.get_or_create(name=name, defaults={'created_by': admin_user})
    return at


def get_or_create_status(name, description, color, admin_user, content_type=None, icon=None):
    """Get or create a Status, backfilling icon when the record already exists but differs."""
    from lab.models import Status
    if not name:
        return None
    status, created = Status.objects.get_or_create(
        name=name,
        content_type=content_type,
        defaults={
            'description': description or '',
            'color': color or '#000000',
            'created_by': admin_user,
            'icon': icon,
        },
    )
    if icon and (created or not status.icon or status.icon != icon):
        status.icon = icon
        status.save()
    return status


# ---------------------------------------------------------------------------
# HPO / notes
# ---------------------------------------------------------------------------

def get_hpo_terms(hpo_codes_str, stdout=None):
    """Parse newline-separated 'Description HP:NNNNN' strings and return matching Term objects."""
    from ontologies.models import Term, Ontology
    if not hpo_codes_str:
        return []
    hp_ontology = Ontology.objects.filter(type=1).first()
    if not hp_ontology:
        if stdout:
            stdout.write('HP ontology not found')
        return []
    terms = []
    for line in str(hpo_codes_str).split('\n'):
        line = line.strip()
        if not line or line == '+':
            continue
        hp_match = re.search(r'HP:(\d+)', line)
        if not hp_match:
            continue
        code = hp_match.group(1)
        description = line[:hp_match.start()].strip()
        term = Term.objects.filter(ontology=hp_ontology, identifier=code).first()
        if not term:
            term = Term.objects.filter(ontology=hp_ontology, label__icontains=description).first()
        if term:
            terms.append(term)
    return terms


def parse_and_add_notes(note_text, target_obj, admin_user):
    """Create one Note per non-empty line in *note_text*, optionally back-dating history."""
    from lab.models import Note
    if not note_text:
        return
    try:
        ct = ContentType.objects.get_for_model(target_obj)
    except Exception:
        return
    for raw_line in str(note_text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            note = Note.objects.create(
                content=line,
                user=admin_user,
                content_type=ct,
                object_id=getattr(target_obj, 'pk', None),
            )
        except Exception:
            continue
        m = re.match(r'^(\d{2}\.\d{2}\.\d{4})', line)
        if m:
            try:
                dt = datetime.strptime(m.group(1), '%d.%m.%Y')
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt, timezone.get_current_timezone())
                first_hist = note.history.earliest()
                if first_hist:
                    first_hist.history_date = dt
                    first_hist.save()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Variant utilities
# ---------------------------------------------------------------------------

def get_initials(full_name):
    """Return uppercase initials string from a full name."""
    parts = [p for p in (full_name or '').split() if p]
    return ''.join(part[0].upper() for part in parts)


def parse_variant_string(variant_str):
    """Parse 'chrX-12345 A>G' and return (chromosome, start_str, reference, alternate) or None."""
    if not variant_str:
        return None
    match = re.match(r'(chr[\w]+)-(\d+)\s+([ACGT]+)>([ACGT]+)', str(variant_str).strip())
    return match.groups() if match else None


def map_zygosity(zygosity_str):
    """Map free-text zygosity to a valid ZYGOSITY_CHOICES key. Defaults to 'het'."""
    if not zygosity_str:
        return 'het'
    z = str(zygosity_str).lower().strip()
    if 'hom' in z:
        return 'hom'
    if 'hemi' in z:
        return 'hemi'
    return 'het'


def map_classification(value):
    """Map an ACMG classification label to the internal choice key, or None if unrecognised."""
    if not value:
        return None
    v = str(value).strip().lower().replace(' ', '_').replace('-', '_')
    table = {
        'pathogenic': 'pathogenic',
        'p': 'pathogenic',
        'likely_pathogenic': 'likely_pathogenic',
        'lp': 'likely_pathogenic',
        'vus': 'vus',
        'variant_of_uncertain_significance': 'vus',
        'likely_benign': 'likely_benign',
        'lb': 'likely_benign',
        'benign': 'benign',
        'b': 'benign',
    }
    return table.get(v)


def map_inheritance(value):
    """Map an inheritance pattern label to the internal choice key. Defaults to 'unknown'."""
    if not value:
        return 'unknown'
    v = str(value).strip().lower()
    if v in {'ad', 'autosomal dominant', 'autosomal_dominant'}:
        return 'ad'
    if v in {'ar', 'autosomal recessive', 'autosomal_recessive'}:
        return 'ar'
    if v in {'x_linked', 'x-linked', 'x linked', 'xl'}:
        return 'x_linked'
    if v in {'mitochondrial', 'mt', 'mito'}:
        return 'mitochondrial'
    if v in {'de_novo', 'de novo', 'denovo'}:
        return 'de_novo'
    return 'unknown'


# ---------------------------------------------------------------------------
# Person / demographic helpers
# ---------------------------------------------------------------------------

def normalize_sex(value):
    """Map Turkish/English sex labels to 'male', 'female', or 'other'. Returns None if unknown."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {'m', 'male', 'erkek'}:
        return 'male'
    if text in {'f', 'female', 'kadin', 'kadın'}:
        return 'female'
    if text in {'other', 'o', 'diğer'}:
        return 'other'
    return None


def to_bool(value):
    """Convert common truthy/falsy representations to bool. Returns None for ambiguous inputs."""
    if value in (1, True, '1', 'True', 'true', 'Evet', 'evet', 'Yes', 'yes', 'E', 'e'):
        return True
    if value in (0, False, '0', 'False', 'false', 'Hayır', 'hayır', 'No', 'no', 'H', 'h'):
        return False
    return None
