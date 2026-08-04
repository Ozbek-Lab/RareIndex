import re
import uuid
from datetime import date, datetime, timezone as datetime_timezone

from django.utils import timezone


FHIR_IDENTIFIER_SYSTEM = "https://rareindex.local/fhir/identifier-type"
FHIR_HPO_SYSTEM = "http://purl.obolibrary.org/obo/hp.owl"
FHIR_ICD11_SYSTEM = "http://id.who.int/icd/release/11/mms"

PHENOPACKET_SCHEMA_VERSION = "2.0"


def build_fhir_bundle(individual, user, created_at=None):
    """Build a compact FHIR JSON Bundle for a RareIndex individual."""
    created_at = created_at or timezone.now()
    patient_ref = _fhir_full_url("Patient", individual.pk)

    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": _datetime_to_instant(created_at),
        "entry": [
            {
                "fullUrl": patient_ref,
                "resource": _build_fhir_patient(individual, user),
            }
        ],
    }

    condition_ref = None
    condition = _build_fhir_condition(individual, patient_ref)
    if condition:
        condition_ref = _fhir_full_url("Condition", individual.pk)
        bundle["entry"].append({"fullUrl": condition_ref, "resource": condition})

    for term in individual.hpo_terms.all():
        observation_ref = _fhir_full_url("Observation", f"{individual.pk}-{term.pk}")
        bundle["entry"].append(
            {
                "fullUrl": observation_ref,
                "resource": _build_fhir_phenotype_observation(
                    individual,
                    term,
                    patient_ref,
                    condition_ref,
                ),
            }
        )

    for sample in individual.samples.all():
        specimen_ref = _fhir_full_url("Specimen", sample.pk)
        bundle["entry"].append(
            {
                "fullUrl": specimen_ref,
                "resource": _build_fhir_specimen(sample, patient_ref),
            }
        )

    return _compact(bundle)


def build_phenopacket(individual, user, created_at=None):
    """Build a Phenopacket v2 JSON object for a RareIndex individual."""
    created_at = created_at or timezone.now()
    subject_id = _phenopacket_subject_id(individual)
    resources = [_phenopacket_rareindex_resource()]

    hpo_terms = list(individual.hpo_terms.all())
    if hpo_terms:
        resources.append(_phenopacket_hpo_resource(hpo_terms[0].ontology))

    if individual.icd11_code:
        resources.append(_phenopacket_icd11_resource())

    packet = {
        "id": f"phenopacket-{individual.pk}",
        "subject": _build_phenopacket_subject(individual, user, subject_id),
        "phenotypicFeatures": [
            {"type": _phenopacket_ontology_class(term)}
            for term in hpo_terms
        ],
        "diseases": _build_phenopacket_diseases(individual),
        "biosamples": [
            _build_phenopacket_biosample(sample, subject_id)
            for sample in individual.samples.all()
        ],
        "metaData": {
            "created": _datetime_to_instant(created_at),
            "createdBy": _created_by(user),
            "resources": resources,
            "phenopacketSchemaVersion": PHENOPACKET_SCHEMA_VERSION,
        },
    }
    return _compact(packet)


def _build_fhir_patient(individual, user):
    include_sensitive = _can_view_sensitive(user)
    identifiers = [
        _build_fhir_identifier(cross_id)
        for cross_id in individual.cross_ids.all()
        if cross_id.id_value
    ]

    if include_sensitive and individual.tc_identity:
        identifiers.append(
            {
                "type": {"text": "TC Identity"},
                "value": str(individual.tc_identity),
            }
        )

    patient = {
        "resourceType": "Patient",
        "id": _fhir_id("individual", individual.pk),
        "identifier": identifiers,
        "gender": _fhir_gender(individual.sex),
        "birthDate": individual.birth_date.isoformat()
        if include_sensitive and individual.birth_date
        else None,
        "deceasedBoolean": True if not individual.is_alive else None,
        "name": [{"text": individual.full_name}]
        if include_sensitive and individual.full_name
        else None,
    }
    return _compact(patient)


def _build_fhir_condition(individual, patient_ref):
    if not individual.diagnosis and not individual.icd11_code:
        return None

    code = {
        "coding": [
            {
                "system": FHIR_ICD11_SYSTEM,
                "code": individual.icd11_code,
                "display": individual.diagnosis or None,
            }
        ]
        if individual.icd11_code
        else [],
        "text": individual.diagnosis or individual.icd11_code,
    }

    condition = {
        "resourceType": "Condition",
        "id": _fhir_id("condition", individual.pk),
        "clinicalStatus": _fhir_codeable_concept(
            "http://terminology.hl7.org/CodeSystem/condition-clinical",
            "active" if individual.is_affected else "unknown",
            "Active" if individual.is_affected else "Unknown",
        ),
        "verificationStatus": _fhir_codeable_concept(
            "http://terminology.hl7.org/CodeSystem/condition-ver-status",
            "confirmed" if individual.diagnosis_date else "provisional",
            "Confirmed" if individual.diagnosis_date else "Provisional",
        ),
        "code": code,
        "subject": {"reference": patient_ref},
        "recordedDate": individual.diagnosis_date.isoformat()
        if individual.diagnosis_date
        else None,
    }

    onset_age = _fhir_onset_age(individual.age_of_onset_in_months)
    if onset_age:
        condition["onsetAge"] = onset_age
    elif individual.age_of_onset:
        condition["onsetString"] = individual.age_of_onset

    return _compact(condition)


def _build_fhir_phenotype_observation(individual, term, patient_ref, condition_ref):
    observation = {
        "resourceType": "Observation",
        "id": _fhir_id("phenotype", f"{individual.pk}-{term.pk}"),
        "status": "final",
        "category": [
            _fhir_codeable_concept(
                "http://terminology.hl7.org/CodeSystem/observation-category",
                "exam",
                "Exam",
            )
        ],
        "code": _fhir_ontology_codeable_concept(term),
        "subject": {"reference": patient_ref},
        "focus": [{"reference": condition_ref}] if condition_ref else None,
        "dataAbsentReason": _fhir_codeable_concept(
            "http://terminology.hl7.org/CodeSystem/data-absent-reason",
            "clinical-finding",
            "Clinical Finding",
        ),
        "note": [{"text": term.description}] if term.description else None,
    }
    return _compact(observation)


def _build_fhir_specimen(sample, patient_ref):
    notes = []
    if sample.sample_measurements:
        notes.append({"text": sample.sample_measurements})

    specimen = {
        "resourceType": "Specimen",
        "id": _fhir_id("sample", sample.pk),
        "subject": {"reference": patient_ref},
        "type": {"text": sample.sample_type.name if sample.sample_type else None},
        "receivedTime": sample.receipt_date.isoformat()
        if sample.receipt_date
        else None,
        "note": notes,
    }
    return _compact(specimen)


def _build_fhir_identifier(cross_id):
    identifier = {
        "system": f"{FHIR_IDENTIFIER_SYSTEM}/{cross_id.id_type_id}",
        "value": cross_id.id_value,
        "type": {"text": cross_id.id_type.name},
        "assigner": {"display": cross_id.id_type.name},
    }
    if cross_id.id_type.use_priority == 1:
        identifier["use"] = "usual"
    elif cross_id.id_type.use_priority > 1:
        identifier["use"] = "secondary"
    return _compact(identifier)


def _build_phenopacket_subject(individual, user, subject_id):
    include_sensitive = _can_view_sensitive(user)
    subject = {
        "id": subject_id,
        "sex": _phenopacket_sex(individual.sex),
        "dateOfBirth": _date_to_phenopacket_timestamp(individual.birth_date)
        if include_sensitive and individual.birth_date
        else None,
        "vitalStatus": {
            "status": "ALIVE" if individual.is_alive else "DECEASED",
        },
    }
    return _compact(subject)


def _build_phenopacket_diseases(individual):
    if not individual.diagnosis and not individual.icd11_code:
        return []

    if individual.icd11_code:
        disease_term = {
            "id": f"ICD11:{individual.icd11_code}",
            "label": individual.diagnosis or individual.icd11_code,
        }
    else:
        disease_term = {
            "id": f"RI:diagnosis-{individual.pk}",
            "label": individual.diagnosis,
        }

    disease = {
        "term": disease_term,
        "onset": _phenopacket_age(individual.age_of_onset_in_months),
    }
    return [_compact(disease)]


def _build_phenopacket_biosample(sample, subject_id):
    sample_type = None
    if sample.sample_type:
        sample_type = {
            "id": f"RI:sample-type-{sample.sample_type_id}",
            "label": sample.sample_type.name,
        }

    biosample = {
        "id": f"sample-{sample.pk}",
        "individualId": subject_id,
        "description": sample.sample_measurements,
        "sampleType": sample_type,
        "timeOfCollection": {
            "timestamp": _date_to_phenopacket_timestamp(sample.receipt_date)
        }
        if sample.receipt_date
        else None,
    }
    return _compact(biosample)


def _phenopacket_ontology_class(term):
    return _compact({"id": term.term, "label": term.label})


def _phenopacket_rareindex_resource():
    return {
        "id": "rareindex",
        "name": "RareIndex",
        "url": "https://rareindex.local",
        "version": "local",
        "namespacePrefix": "RI",
        "iriPrefix": "https://rareindex.local/",
    }


def _phenopacket_hpo_resource(ontology):
    return {
        "id": "hp",
        "name": "Human Phenotype Ontology",
        "url": "http://purl.obolibrary.org/obo/hp.owl",
        "version": ontology.label or "unknown",
        "namespacePrefix": "HP",
        "iriPrefix": "http://purl.obolibrary.org/obo/HP_",
    }


def _phenopacket_icd11_resource():
    return {
        "id": "icd11",
        "name": "International Classification of Diseases 11th Revision",
        "url": "https://icd.who.int/browse11",
        "version": "11",
        "namespacePrefix": "ICD11",
        "iriPrefix": "https://icd.who.int/browse11/l-m/en#/http://id.who.int/icd/entity/",
    }


def _fhir_ontology_codeable_concept(term):
    system_by_source = {
        "HP": FHIR_HPO_SYSTEM,
        "MONDO": "http://purl.obolibrary.org/obo/mondo.owl",
        "ONCOTREE": "http://purl.obolibrary.org/obo/ncit/ncit-oncotree.owl",
    }
    return _compact(
        {
            "coding": [
                {
                    "system": system_by_source.get(term.source),
                    "code": term.term,
                    "display": term.label,
                }
            ],
            "text": term.label or term.term,
        }
    )


def _fhir_codeable_concept(system, code, display):
    return _compact(
        {
            "coding": [
                {
                    "system": system,
                    "code": code,
                    "display": display,
                }
            ],
            "text": display,
        }
    )


def _fhir_gender(sex):
    if sex in {"male", "female", "other"}:
        return sex
    return "unknown"


def _phenopacket_sex(sex):
    return {
        "male": "MALE",
        "female": "FEMALE",
        "other": "OTHER_SEX",
    }.get(sex, "UNKNOWN_SEX")


def _fhir_onset_age(months):
    if months is None:
        return None
    return {
        "value": months,
        "unit": "months",
        "system": "http://unitsofmeasure.org",
        "code": "mo",
    }


def _phenopacket_age(months):
    if months is None:
        return None
    return {"age": {"iso8601duration": _months_to_iso8601_duration(months)}}


def _months_to_iso8601_duration(months):
    years, remaining_months = divmod(months, 12)
    duration = "P"
    if years:
        duration += f"{years}Y"
    if remaining_months:
        duration += f"{remaining_months}M"
    return duration if duration != "P" else "P0M"


def _fhir_full_url(resource_type, identifier):
    stable_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"rareindex:{resource_type}:{identifier}")
    return f"urn:uuid:{stable_uuid}"


def _fhir_id(prefix, identifier):
    value = re.sub(r"[^A-Za-z0-9.-]+", "-", f"{prefix}-{identifier}").strip("-")
    return value[:64] or prefix


def _phenopacket_subject_id(individual):
    return f"individual-{individual.pk}"


def _created_by(user):
    if user and getattr(user, "is_authenticated", False):
        return user.get_username()
    return "RareIndex"


def _can_view_sensitive(user):
    return bool(user and user.has_perm("lab.view_sensitive_data"))


def _datetime_to_instant(value):
    if timezone.is_naive(value):
        value = timezone.make_aware(value, datetime_timezone.utc)
    return value.astimezone(datetime_timezone.utc).isoformat().replace("+00:00", "Z")


def _date_to_phenopacket_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return _datetime_to_instant(value)
    if isinstance(value, date):
        return f"{value.isoformat()}T00:00:00Z"
    return None


def _compact(value):
    if isinstance(value, dict):
        compacted = {}
        for key, item in value.items():
            compact_item = _compact(item)
            if compact_item in (None, "", [], {}):
                continue
            compacted[key] = compact_item
        return compacted
    if isinstance(value, list):
        return [
            compact_item
            for item in value
            if (compact_item := _compact(item)) not in (None, "", [], {})
        ]
    return value
