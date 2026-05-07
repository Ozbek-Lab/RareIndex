from django import template

register = template.Library()


ACMG_CRITERIA_INFO = {
    "PVS1": {
        "description": "Null variant in a gene where loss of function is a known disease mechanism.",
        "category": "pathogenic",
        "severity": "very_strong",
    },
    "PS1": {
        "description": "Same amino acid change as a previously established pathogenic variant.",
        "category": "pathogenic",
        "severity": "strong",
    },
    "PS2": {
        "description": "De novo variant with both parents confirmed and no family history.",
        "category": "pathogenic",
        "severity": "strong",
    },
    "PS3": {
        "description": "Functional studies support a damaging effect on the gene or gene product.",
        "category": "pathogenic",
        "severity": "strong",
    },
    "PS4": {
        "description": "The variant is more common in affected individuals than in controls.",
        "category": "pathogenic",
        "severity": "strong",
    },
    "PM1": {
        "description": "Located in a hot spot or critical functional domain without benign variation.",
        "category": "pathogenic",
        "severity": "moderate",
    },
    "PM2": {
        "description": "Absent from controls or extremely rare for a recessive disorder.",
        "category": "pathogenic",
        "severity": "moderate",
    },
    "PM3": {
        "description": "Detected in trans with a pathogenic variant in a recessive disorder.",
        "category": "pathogenic",
        "severity": "moderate",
    },
    "PM4": {
        "description": "Causes a protein length change through an in-frame indel or stop-loss.",
        "category": "pathogenic",
        "severity": "moderate",
    },
    "PM5": {
        "description": "Novel missense change at a residue with another known pathogenic missense.",
        "category": "pathogenic",
        "severity": "moderate",
    },
    "PM6": {
        "description": "Assumed de novo, but paternity and maternity are not confirmed.",
        "category": "pathogenic",
        "severity": "moderate",
    },
    "PP1": {
        "description": "Co-segregates with disease in multiple affected family members.",
        "category": "pathogenic",
        "severity": "supporting",
    },
    "PP2": {
        "description": "Missense variant in a gene where missense disease is common.",
        "category": "pathogenic",
        "severity": "supporting",
    },
    "PP3": {
        "description": "Multiple computational lines suggest a deleterious effect.",
        "category": "pathogenic",
        "severity": "supporting",
    },
    "PP4": {
        "description": "Phenotype or family history is highly specific for one disease.",
        "category": "pathogenic",
        "severity": "supporting",
    },
    "PP5": {
        "description": "A reputable source recently reported the variant as pathogenic.",
        "category": "pathogenic",
        "severity": "supporting",
    },
    "BA1": {
        "description": "Allele frequency above 5% in population databases.",
        "category": "benign",
        "severity": "standalone",
    },
    "BS1": {
        "description": "Allele frequency is greater than expected for the disorder.",
        "category": "benign",
        "severity": "strong",
    },
    "BS2": {
        "description": "Observed in a healthy adult for an early-onset fully penetrant disorder.",
        "category": "benign",
        "severity": "strong",
    },
    "BS3": {
        "description": "Well-established functional studies show no damaging effect.",
        "category": "benign",
        "severity": "strong",
    },
    "BS4": {
        "description": "Lack of segregation in affected family members.",
        "category": "benign",
        "severity": "strong",
    },
    "BP1": {
        "description": "Missense variant in a gene where truncating variants cause disease.",
        "category": "benign",
        "severity": "supporting",
    },
    "BP2": {
        "description": "Observed in trans or cis with a pathogenic variant.",
        "category": "benign",
        "severity": "supporting",
    },
    "BP3": {
        "description": "In-frame deletion or insertion in a repetitive region without a known function.",
        "category": "benign",
        "severity": "supporting",
    },
    "BP4": {
        "description": "Multiple computational lines suggest no impact.",
        "category": "benign",
        "severity": "supporting",
    },
    "BP5": {
        "description": "Variant found in a case with an alternate molecular basis.",
        "category": "benign",
        "severity": "supporting",
    },
    "BP6": {
        "description": "A reputable source recently reported the variant as benign.",
        "category": "benign",
        "severity": "supporting",
    },
    "BP7": {
        "description": "Synonymous variant predicted not to affect splicing and not highly conserved.",
        "category": "benign",
        "severity": "supporting",
    },
}


ACMG_EVIDENCE_CATEGORY_ROWS = [
    {
        "title": "Population data",
        "determined": ["BA1", "BS1", "BS2", "PM2", "PS4"],
        "manual": [],
    },
    {
        "title": "Computational and predictive data",
        "determined": ["PVS1", "PS1", "PM4", "PM5", "PP3", "BP1", "BP3", "BP4", "BP7"],
        "manual": [],
    },
    {
        "title": "Functional data",
        "determined": ["PM1", "PP2"],
        "manual": ["PS3", "BS3"],
    },
    {
        "title": "Segregation data",
        "determined": [],
        "manual": ["PP1", "BS4"],
    },
    {
        "title": "De novo data",
        "determined": [],
        "manual": ["PS2", "PM6"],
    },
    {
        "title": "Allelic data",
        "determined": [],
        "manual": ["PM3", "BP2"],
    },
    {
        "title": "Other databases",
        "determined": ["PP5", "BP6"],
        "manual": [],
    },
    {
        "title": "Other data",
        "determined": [],
        "manual": ["PP4", "BP5"],
    },
]


ACMG_STRENGTH_OPTIONS = [
    {
        "value": "indeterminate",
        "label": "Indeterminate",
        "short_label": "I",
        "title": "Indeterminate",
    },
    {
        "value": "supporting",
        "label": "Supporting",
        "short_label": "Sp",
        "title": "Supporting",
    },
    {
        "value": "moderate",
        "label": "Moderate",
        "short_label": "M",
        "title": "Moderate",
    },
    {
        "value": "strong",
        "label": "Strong",
        "short_label": "St",
        "title": "Strong",
    },
    {
        "value": "very_strong",
        "label": "Very Strong",
        "short_label": "VS",
        "title": "Very Strong",
    },
]

ACMG_STRENGTH_LABELS = {
    option["value"]: option["label"]
    for option in ACMG_STRENGTH_OPTIONS
}

ACMG_STRENGTH_POINTS = {
    "indeterminate": 0,
    "supporting": 1,
    "moderate": 2,
    "strong": 4,
    "very_strong": 8,
}

ACMG_POINT_CLASSIFICATION_LABELS = {
    "pathogenic": "Pathogenic",
    "likely_pathogenic": "Likely_pathogenic",
    "uncertain_significance": "Uncertain_significance",
    "likely_benign": "Likely_benign",
    "benign": "Benign",
}


def _normalize_strength(value, default=""):
    if value is None:
        return default

    normalized = str(value).strip().replace("-", "_").replace(" ", "_").lower()
    aliases = {
        "": default,
        "not_applicable": "indeterminate",
        "na": "indeterminate",
        "none": "indeterminate",
        "stand_alone": "very_strong",
        "standalone": "very_strong",
        "verystrong": "very_strong",
        "very_strong": "very_strong",
        "support": "supporting",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in ACMG_STRENGTH_LABELS:
        return normalized
    return default


def _default_strength_for_info(info):
    return _normalize_strength(info.get("severity"), "supporting")


def _criterion_badge_class(code, category):
    if category == "benign":
        if code == "BA1":
            return "badge-success"
        if code.startswith("BS"):
            return "badge-info"
        return "badge-success badge-outline"

    if code == "PVS1":
        return "badge-error"
    if code.startswith("PS"):
        return "badge-error badge-outline"
    if code.startswith("PM"):
        return "badge-warning"
    if code.startswith("PP"):
        return "badge-primary badge-outline"
    return "badge-ghost"


def _normalize_criterion(raw):
    if raw is None:
        return None
    if isinstance(raw, str):
        value = raw.strip()
    else:
        value = str(raw).strip()

    if not value:
        return None

    value = value.replace(" ", "_")
    parts = value.split("_")
    code = parts[0].upper()
    suffix = " ".join(parts[1:]).strip()
    info = ACMG_CRITERIA_INFO.get(code, {})
    default_strength = _default_strength_for_info(info)
    strength = _normalize_strength(suffix, default_strength)
    suffix_label = ""
    if strength != default_strength and strength != "indeterminate":
        suffix_label = ACMG_STRENGTH_LABELS.get(strength, "")

    return {
        "code": code,
        "display": f"{code} {suffix_label}".strip() if suffix_label else code,
        "suffix": suffix,
        "description": info.get("description", "ACMG criterion description not available."),
        "category": info.get("category", "unknown"),
        "severity": info.get("severity", ""),
        "default_strength": default_strength,
        "strength": strength,
        "badge_class": _criterion_badge_class(code, info.get("category", "unknown")),
    }


@register.filter
def parse_acmg_criteria(value):
    """
    Normalize GeneBe ACMG criteria values into display-ready metadata.
    """
    if not value:
        return []

    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, (list, tuple, set)):
        raw_items = []
        for item in value:
            if isinstance(item, str) and "," in item:
                raw_items.extend(part.strip() for part in item.split(",") if part.strip())
            else:
                raw_items.append(item)
    else:
        raw_items = [value]

    parsed = []
    seen = set()
    for item in raw_items:
        meta = _normalize_criterion(item)
        if not meta:
            continue
        key = meta["display"]
        if key in seen:
            continue
        seen.add(key)
        parsed.append(meta)
    return parsed


def _scope_value(value):
    return (value or "").strip()


def _gene_item_scope(gene_item):
    if not isinstance(gene_item, dict):
        return "", ""
    return _scope_value(gene_item.get("gene_symbol")), _scope_value(gene_item.get("transcript"))


def _manual_acmg_override_map(variant, gene_symbol="", transcript=""):
    if not variant or not hasattr(variant, "acmg_evidence_overrides"):
        return {}

    gene_symbol = _scope_value(gene_symbol)
    transcript = _scope_value(transcript)
    overrides = {}
    for record in variant.acmg_evidence_overrides.all():
        if _scope_value(record.gene_symbol) != gene_symbol or _scope_value(record.transcript) != transcript:
            continue
        criterion = (record.criterion or "").strip().replace(" ", "_").upper()
        if not criterion:
            continue
        if record.source == "manual":
            overrides[criterion] = record
    return overrides


def _record_acmg_map(variant, source, gene_symbol="", transcript=""):
    if not variant or not hasattr(variant, "acmg_evidence_overrides"):
        return {}

    gene_symbol = _scope_value(gene_symbol)
    transcript = _scope_value(transcript)
    records = {}
    for record in variant.acmg_evidence_overrides.all():
        if record.source != source:
            continue
        if _scope_value(record.gene_symbol) != gene_symbol or _scope_value(record.transcript) != transcript:
            continue
        criterion = (record.criterion or "").strip().replace(" ", "_").upper()
        if criterion:
            records[criterion] = record
    return records


def _imported_acmg_criteria_set(variant, gene_symbol="", transcript=""):
    if not variant:
        return set()

    gene_symbol = _scope_value(gene_symbol)
    transcript = _scope_value(transcript)

    if hasattr(variant, "acmg_evidence_overrides"):
        imported_from_records = {
            (record.criterion or "").strip().replace(" ", "_").upper()
            for record in variant.acmg_evidence_overrides.all()
            if (
                record.source == "genebe"
                and record.included
                and _scope_value(record.gene_symbol) == gene_symbol
                and _scope_value(record.transcript) == transcript
            )
        }
        if imported_from_records:
            return imported_from_records

    if not hasattr(variant, "annotations"):
        return set()

    genebe = get_annotation_by_source(variant, "genebe")
    if not genebe:
        return set()

    data = genebe.data if isinstance(genebe.data, dict) else {}
    variant_items = data.get("variants") if isinstance(data.get("variants"), list) else []
    if not variant_items and data:
        variant_items = [data]

    imported = set()
    for item in variant_items:
        if not isinstance(item, dict):
            continue
        if not gene_symbol and not transcript:
            for crit in parse_acmg_criteria(item.get("acmg_criteria")):
                imported.add(crit["code"])
            continue
        for gene_record in item.get("acmg_by_gene", []) or []:
            if not isinstance(gene_record, dict):
                continue
            if (
                _scope_value(gene_record.get("gene_symbol")) == gene_symbol
                and _scope_value(gene_record.get("transcript")) == transcript
            ):
                for crit in parse_acmg_criteria(gene_record.get("criteria")):
                    imported.add(crit["code"])
    return imported


def _strength_options_for(selected_strength, default_strength=""):
    selected_strength = _normalize_strength(selected_strength, "indeterminate")
    default_strength = _normalize_strength(default_strength, "")
    return [
        {
            **option,
            "selected": option["value"] == selected_strength,
            "is_default": option["value"] == default_strength,
        }
        for option in ACMG_STRENGTH_OPTIONS
    ]


def _display_with_strength(code, strength, default_strength):
    strength = _normalize_strength(strength, default_strength)
    if strength in {"", "indeterminate", default_strength}:
        return code
    return f"{code} {ACMG_STRENGTH_LABELS.get(strength, '').strip()}".strip()


def _annotate_strength(item, strength=None, included=True):
    default_strength = _normalize_strength(item.get("default_strength") or item.get("severity"), "supporting")
    resolved_strength = _normalize_strength(strength or item.get("strength"), default_strength)
    if not included:
        resolved_strength = "indeterminate"
    item["default_strength"] = default_strength
    item["strength"] = resolved_strength
    item["strength_label"] = ACMG_STRENGTH_LABELS.get(resolved_strength, "")
    item["strength_options"] = _strength_options_for(resolved_strength, default_strength)
    item["display"] = _display_with_strength(item["code"], resolved_strength, default_strength)
    return item


class PointClassification:
    """
    ACMG point classification adapted to the stored evidence catalog.
    """

    def __init__(self, evidence_items):
        self.evidence_items = evidence_items

    def score(self):
        result = 0
        for evidence in self.evidence_items:
            if not evidence.get("is_active"):
                continue

            strength = _normalize_strength(evidence.get("strength"), "indeterminate")
            point = ACMG_STRENGTH_POINTS.get(strength, 0)
            code = evidence.get("code", "")
            if code.startswith("P"):
                result += point
            elif code.startswith("B"):
                result -= point
        return result

    def classify_variant(self):
        score = self.score()
        if score >= 10:
            key = "pathogenic"
        elif score >= 6:
            key = "likely_pathogenic"
        elif score >= 0:
            key = "uncertain_significance"
        elif score > -7:
            key = "likely_benign"
        else:
            key = "benign"

        return {
            "key": key,
            "label": ACMG_POINT_CLASSIFICATION_LABELS[key],
            "score": score,
        }


@register.filter
def parse_acmg_criteria_with_variant(value, variant):
    """
    Parse ACMG criteria and overlay manual overrides from a variant.
    """
    parsed = parse_acmg_criteria(value)
    manual_overrides = _manual_acmg_override_map(variant)

    parsed_by_code = {item["code"]: item for item in parsed}
    order = {item["code"]: idx for idx, item in enumerate(parsed)}

    for code, record in manual_overrides.items():
        item = parsed_by_code.get(code)
        if item is None:
            item = _normalize_criterion(code)
            if not item:
                continue
            parsed_by_code[code] = item
            parsed.append(item)

        item["is_manual_override"] = True
        item["manual_included"] = bool(record.included)
        item["manual_note"] = record.note or ""
        item["manual_state_label"] = "Manual included" if record.included else "Manual excluded"
        item["tooltip"] = f"{item['description']} {item['manual_state_label']}."
        if record.note:
            item["tooltip"] = f"{item['tooltip']} Manual note: {record.note}"
        _annotate_strength(item, record.strength, record.included)

        if record.included:
            item["badge_class"] = f"{item['badge_class']} ring-2 ring-primary/40 font-semibold"
        else:
            item["badge_class"] = "badge-ghost badge-outline opacity-60 line-through"

    for item in parsed:
        _annotate_strength(item, item.get("strength"), True)

    parsed.sort(key=lambda item: order.get(item["code"], 10_000))
    return parsed


@register.filter
def acmg_criteria_with_gene(gene_item, variant):
    """
    Parse one GeneBe gene row and overlay manual changes for that row only.
    """
    if not isinstance(gene_item, dict):
        return []

    gene_symbol, transcript = _gene_item_scope(gene_item)
    parsed = parse_acmg_criteria(gene_item.get("criteria"))
    manual_overrides = _manual_acmg_override_map(variant, gene_symbol, transcript)

    parsed_by_code = {item["code"]: item for item in parsed}
    order = {item["code"]: idx for idx, item in enumerate(parsed)}

    for code, record in manual_overrides.items():
        item = parsed_by_code.get(code)
        if item is None:
            item = _normalize_criterion(code)
            if not item:
                continue
            parsed_by_code[code] = item
            parsed.append(item)

        item["is_manual_override"] = True
        item["manual_included"] = bool(record.included)
        item["manual_note"] = record.note or ""
        item["manual_state_label"] = "Manual included" if record.included else "Manual excluded"
        item["tooltip"] = f"{item['description']} {item['manual_state_label']}."
        _annotate_strength(item, record.strength, record.included)

        if record.included:
            item["badge_class"] = f"{item['badge_class']} ring-2 ring-primary/40 font-semibold"
        else:
            item["badge_class"] = "badge-ghost badge-outline opacity-60 line-through"

    imported_map = _record_acmg_map(variant, "genebe", gene_symbol, transcript)
    for item in parsed:
        imported = imported_map.get(item["code"])
        if imported and item["code"] not in manual_overrides:
            _annotate_strength(item, imported.strength or item.get("strength"), imported.included)
        else:
            _annotate_strength(item, item.get("strength"), item.get("manual_included", True))

    parsed.sort(key=lambda item: order.get(item["code"], 10_000))
    return parsed


@register.filter
def acmg_criteria_catalog(variant, gene_symbol="", transcript=""):
    """
    Return the full ACMG evidence catalog annotated with imported/manual state.
    """
    imported = _imported_acmg_criteria_set(variant, gene_symbol, transcript)
    imported_map = _record_acmg_map(variant, "genebe", gene_symbol, transcript)
    manual_map = _manual_acmg_override_map(variant, gene_symbol, transcript)

    catalog = []
    for code, info in ACMG_CRITERIA_INFO.items():
        manual = manual_map.get(code)
        imported_record = imported_map.get(code)
        is_imported = code in imported
        manual_state = ""
        manual_state_label = ""
        is_active = is_imported
        default_strength = _default_strength_for_info(info)
        active_strength = default_strength

        if imported_record:
            active_strength = _normalize_strength(imported_record.strength, default_strength)

        if manual:
            active_strength = _normalize_strength(manual.strength, default_strength)
            if not manual.included:
                active_strength = "indeterminate"

        if manual and (manual.included != is_imported or _normalize_strength(manual.strength, default_strength) != _normalize_strength(imported_record.strength if imported_record else default_strength, default_strength)):
            manual_state = "manual-include" if manual.included else "manual-exclude"
            manual_state_label = "Manual Include" if manual.included else "Manual Exclude"
            is_active = bool(manual.included)

        displayed_strength = active_strength if is_active else default_strength

        catalog.append({
            "code": code,
            "display": code,
            "description": info.get("description", "ACMG criterion description not available."),
            "category": info.get("category", "unknown"),
            "severity": info.get("severity", ""),
            "default_strength": default_strength,
            "strength": active_strength if is_active else "indeterminate",
            "strength_label": ACMG_STRENGTH_LABELS.get(displayed_strength, ""),
            "strength_options": _strength_options_for(displayed_strength, default_strength),
            "is_imported": is_imported,
            "manual_state": manual_state,
            "manual_state_label": manual_state_label,
            "is_active": is_active,
        })

    return catalog


@register.filter
def acmg_criteria_catalog_sections(variant):
    """
    Split the ACMG catalog into pathogenic and benign sections.
    """
    catalog = acmg_criteria_catalog(variant)
    return [
        {
            "key": "benign",
            "title": "Benign evidence",
            "items": [item for item in catalog if item["category"] == "benign"],
        },
        {
            "key": "pathogenic",
            "title": "Pathogenic evidence",
            "items": [item for item in catalog if item["category"] == "pathogenic"],
        },
    ]


@register.filter
def acmg_criteria_catalog_sections_for_gene(gene_item, variant):
    """
    Split the ACMG catalog for one GeneBe gene row.
    """
    gene_symbol, transcript = _gene_item_scope(gene_item)
    catalog = acmg_criteria_catalog(variant, gene_symbol, transcript)
    return [
        {
            "key": "benign",
            "title": "Benign evidence",
            "items": [item for item in catalog if item["category"] == "benign"],
        },
        {
            "key": "pathogenic",
            "title": "Pathogenic evidence",
            "items": [item for item in catalog if item["category"] == "pathogenic"],
        },
    ]


@register.filter
def acmg_evidence_matrix_for_gene(gene_item, variant):
    """
    Return a four-column evidence matrix for one GeneBe gene row.
    """
    gene_symbol, transcript = _gene_item_scope(gene_item)
    catalog_by_code = {
        item["code"]: item
        for item in acmg_criteria_catalog(variant, gene_symbol, transcript)
    }

    columns = [
        {
            "key": "benign_determined",
            "category": "benign",
            "group": "determined",
            "title": "Benign",
            "subtitle": "Determined",
            "accent": "info",
        },
        {
            "key": "benign_manual",
            "category": "benign",
            "group": "manual",
            "title": "Benign",
            "subtitle": "Manual",
            "accent": "info",
        },
        {
            "key": "pathogenic_determined",
            "category": "pathogenic",
            "group": "determined",
            "title": "Pathogenic",
            "subtitle": "Determined",
            "accent": "error",
        },
        {
            "key": "pathogenic_manual",
            "category": "pathogenic",
            "group": "manual",
            "title": "Pathogenic",
            "subtitle": "Manual",
            "accent": "error",
        },
    ]

    for column in columns:
        items = []
        for row in ACMG_EVIDENCE_CATEGORY_ROWS:
            items.extend([
                catalog_by_code[code]
                for code in row[column["group"]]
                if (
                    code in catalog_by_code
                    and catalog_by_code[code]["category"] == column["category"]
                )
            ])
        column["items"] = items
        column["count"] = len(items)

    return columns


@register.filter
def acmg_classification_for_gene(gene_item, variant):
    """
    Calculate the ACMG classification for one GeneBe gene row from stored evidence.
    """
    gene_symbol, transcript = _gene_item_scope(gene_item)
    catalog = acmg_criteria_catalog(variant, gene_symbol, transcript)
    active_evidence = [
        item
        for item in catalog
        if item.get("is_active") and item.get("strength") != "indeterminate"
    ]
    result = PointClassification(active_evidence).classify_variant()
    result["evidence"] = active_evidence
    return result

@register.filter
def get_annotation_data(variant, key):
    """
    Safely get data from the first annotation of a variant.
    Supports dot notation for nested keys (e.g. 'clinvar.hgvs.coding').
    Also supports 'smart' keys like 'hgvsc', 'hgvsp', 'gene' that try multiple sources.
    """
    if not variant:
        return None
    
    # Try to get from prefetch cache or DB
    annotations = None
    if hasattr(variant, 'annotations'):
        # If prefetch_related was used, .all() uses cache
        annotations = variant.annotations.all()
    
    if not annotations:
        return None
        
    # Helper to traverse nested dictionary with dot notation
    def get_nested(data, path):
        parts = path.split('.')
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                # If it's a list, try to find the key in any of the items
                # We prioritize the first non-None match
                found = None
                for item in current:
                    if isinstance(item, dict):
                        val = item.get(part)
                        if val:
                            found = val
                            break
                current = found
            else:
                return None
            
            if current is None:
                return None
        return current

    # Define smart lookup paths for common fields
    smart_paths = {
        'hgvsc': [
            'clinvar.hgvs.coding',
            'snpeff.ann.hgvs_c', 
            'hgvsc', # VEP top level
            'transcript_consequences.hgvsc', # VEP nested
            'myvariant.hgvs.coding'
        ],
        'hgvsp': [
            'clinvar.hgvs.protein',
            'snpeff.ann.hgvs_p',
            'hgvsp', # VEP top level
            'transcript_consequences.hgvsp', # VEP nested
            'myvariant.hgvs.protein'
        ],
        'gene': [
            'clinvar.gene.symbol',
            'snpeff.ann.genename',
            'symbol', # VEP top level
            'transcript_consequences.gene_symbol', # VEP nested
            'transcript_consequences.hgnc_id', # VEP nested fallback
            'transcript_consequences.gene_id', # VEP nested fallback (Ensembl ID)
            'myvariant.gene.symbol'
        ]
    }

    # Determine paths to check
    paths_to_check = smart_paths.get(key, [key])

    # Iterate through annotations and paths
    for annotation in annotations:
        data_items = annotation.data
        if isinstance(data_items, dict):
            data_items = [data_items]
        elif not isinstance(data_items, list):
            continue
            
        for data in data_items:
            if not isinstance(data, dict):
                continue
                
            for path in paths_to_check:
                value = get_nested(data, path)
                if value:
                    return value

    return None


@register.filter
def get_annotation_by_source(variant, source):
    """
    Return the latest annotation for a given source, if present.
    """
    if not variant or not hasattr(variant, "annotations"):
        return None

    source = (source or "").lower()
    for annotation in variant.annotations.all():
        if (annotation.source or "").lower() == source:
            return annotation
    return None
