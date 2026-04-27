from __future__ import annotations

from typing import Optional

from app.models import EmailAnalysisResult, PersonRecord
from app.processing.entity_resolution_attribution import attribute_match, build_source_blocks
from app.processing.entity_resolution_merge import merge_similar_person_records
from app.processing.entity_resolution_models import ResolverRuntimeState
from app.processing.entity_resolution_utils import (
    build_header_participants,
    extract_name_from_email,
    stable_person_id,
)
from app.processing.local_llm_attribution import LocalLLMAttributionHelper


def resolve_entities(
    email_results: list[EmailAnalysisResult],
    llm_helper: Optional[LocalLLMAttributionHelper] = None,
) -> list[PersonRecord]:
    records_by_key: dict[str, PersonRecord] = {}
    llm_helper = llm_helper or LocalLLMAttributionHelper()

    for result in email_results:
        participants = build_header_participants(result)
        runtime_state = ResolverRuntimeState()
        source_blocks = build_source_blocks(result)

        for match in result.pii_matches:
            decision = attribute_match(match, result, participants, source_blocks, llm_helper, runtime_state)
            record = records_by_key.get(decision.entity_key)
            if record is None:
                record = PersonRecord(
                    person_id="",
                    canonical_email=decision.canonical_email,
                    canonical_name=decision.canonical_name,
                    entity_type=decision.entity_type,
                    attribution_confidence=decision.confidence,
                    attribution_methods=[decision.method],
                    attribution_evidence=list(decision.evidence),
                )
                records_by_key[decision.entity_key] = record

            if decision.canonical_email:
                record.all_emails.add(decision.canonical_email)
                if not record.canonical_email:
                    record.canonical_email = decision.canonical_email

            if decision.canonical_name:
                record.all_names.add(decision.canonical_name)
                if not record.canonical_name or record.canonical_name == "UNATTRIBUTED":
                    record.canonical_name = decision.canonical_name

            if match not in record.pii_matches:
                record.pii_matches.append(match)

            if result.eml_filename not in record.source_emails:
                record.source_emails.append(result.eml_filename)

            if decision.method and decision.method not in record.attribution_methods:
                record.attribution_methods.append(decision.method)

            for evidence in decision.evidence:
                if evidence not in record.attribution_evidence:
                    record.attribution_evidence.append(evidence)

            record.attribution_confidence = round(
                (
                    (record.attribution_confidence * (len(record.pii_matches) - 1))
                    + decision.confidence
                )
                / len(record.pii_matches),
                2,
            )

            if decision.entity_type != "PERSON" or not record.entity_type:
                record.entity_type = decision.entity_type

    persons = merge_similar_person_records(list(records_by_key.values()))
    for person in persons:
        person.person_id = stable_person_id(person)
        if not person.canonical_name and person.canonical_email:
            person.canonical_name = extract_name_from_email(person.canonical_email)
        if not person.canonical_name:
            person.canonical_name = "UNATTRIBUTED"

    return sorted(
        persons,
        key=lambda person: (person.canonical_name or "", person.canonical_email or "", person.person_id),
    )
