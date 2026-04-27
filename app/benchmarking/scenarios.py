from __future__ import annotations

from email.message import EmailMessage

from app.benchmarking.attachments import (
    _add_attachment,
    _add_nested_eml_attachment,
    _compose_body,
    _csv_attachment,
    _docx_attachment,
    _eml_bytes,
    _expected_findings_from_pairs,
    _image_attachment_bytes,
    _negative_attachment,
    _pdf_attachment_bytes,
    _positive_attachment_content,
    _rtf_attachment,
    _text_attachment,
    _xlsx_attachment,
    _zip_attachment,
)
from app.benchmarking.fixtures import (
    ATTACHMENT_ROTATION,
    DEFAULT_BENCHMARK_PROFILE,
    ORG_NAMES,
    POSITIVE_BUNDLES,
    REALWORLD_V2_PROFILE,
    REALWORLD_V3_PROFILE,
    REALWORLD_V4_PROFILE,
    SUPPORT_EMAILS,
    SUPPORT_PHONES,
    TICKET_CODES,
    WORK_DOMAINS,
    AttachmentSpec,
    FixturePerson,
    _business_noise,
    _field_lines,
    _field_pairs_for_attachment,
    _make_person,
    _negative_lines,
    _negative_subject,
    _positive_intro,
    _positive_subject,
)
from app.benchmarking.ground_truth import BenchmarkFile


def _build_body_positive(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    person = _make_person(index, seed)
    bundle = POSITIVE_BUNDLES[index % len(POSITIVE_BUNDLES)]
    subject = _positive_subject(index, bundle)
    intro_lines = _positive_intro(index, person)
    field_lines, findings = _field_lines(person, bundle, index)
    body_lines = intro_lines + ["", "Record details:"] + field_lines
    message = _compose_body(subject, f"Hello {person.full_name},", body_lines, html_only=index % 7 == 0)

    source_ref = f"email_{index:03d}.eml (email body)"
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="body_record",
        subject=subject,
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(source_ref, findings, default_entity_name=person.full_name),
        expected_human_review=index % 11 == 0,
        notes="Direct record block embedded in email body.",
    )
    return message, benchmark_file


def _build_attachment_positive(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    person = _make_person(index, seed)
    bundle = POSITIVE_BUNDLES[index % len(POSITIVE_BUNDLES)]
    kind = ATTACHMENT_ROTATION[index % len(ATTACHMENT_ROTATION)]
    subject = _positive_subject(index, bundle)
    intro_lines = [
        f"Please review the attached document for {person.full_name}.",
        f"Reference ticket: {TICKET_CODES[index % len(TICKET_CODES)]}",
        f"Questions line: {SUPPORT_PHONES[index % len(SUPPORT_PHONES)]}",
    ]
    message = _compose_body(subject, "Compliance team,", intro_lines, html_only=index % 9 == 0)

    field_lines, findings = _field_lines(person, bundle, index)
    attachment_filename = f"record_{index:03d}.{kind}"
    attachment_source_ref = f"email_{index:03d}.eml > {attachment_filename}"

    if kind == "txt":
        data = _text_attachment(["Record Summary", *field_lines, * _business_noise(index)])
        mime_type = "text/plain"
    elif kind == "csv":
        field_pairs = _field_pairs_for_attachment(person, bundle, index)
        rows_out = [[header, value] for header, value in field_pairs]
        rows_out.append(["Record ID", TICKET_CODES[index % len(TICKET_CODES)]])
        data = _csv_attachment(["Field", "Value"], rows_out)
        mime_type = "text/csv"
    elif kind == "docx":
        data = _docx_attachment("Attached Record", intro_lines + field_lines)
        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif kind == "xlsx":
        headers = ["field", "value"]
        rows = []
        for line in field_lines:
            field, value = line.split(": ", 1)
            rows.append([field, value])
        data = _xlsx_attachment("Record", headers, rows)
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        data = _rtf_attachment(["Attached Record", *field_lines])
        mime_type = "text/rtf"

    attachment = AttachmentSpec(filename=attachment_filename, mime_type=mime_type, data=data)
    _add_attachment(message, attachment)
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id=f"attachment_{kind}",
        subject=subject,
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(
            attachment_source_ref,
            findings,
            attachment_filename=attachment_filename,
            location_kind="attachment",
            default_entity_name=person.full_name,
        ),
        attachments=[attachment_filename],
        expected_human_review=index % 8 == 0,
        notes=f"Structured record stored in {kind.upper()} attachment.",
    )
    return message, benchmark_file


def _build_zip_or_nested(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    person = _make_person(index, seed)
    bundle = POSITIVE_BUNDLES[index % len(POSITIVE_BUNDLES)]
    subject = "Escalated Record Package"
    body_lines = [
        f"The attached package contains source material for {person.full_name}.",
        f"Escalation ticket: {TICKET_CODES[index % len(TICKET_CODES)]}",
        "Please confirm whether manual review is required after scan completion.",
    ]
    message = _compose_body(subject, "Security review,", body_lines)
    field_lines, findings = _field_lines(person, bundle, index)

    if index % 2 == 0:
        member = AttachmentSpec(filename="nested_record.txt", mime_type="text/plain", data=_text_attachment(field_lines))
        zip_name = f"package_{index:03d}.zip"
        zip_attachment = AttachmentSpec(filename=zip_name, mime_type="application/zip", data=_zip_attachment([member]))
        _add_attachment(message, zip_attachment)
        source_ref = f"email_{index:03d}.eml > {zip_name}"
        notes = "ZIP attachment containing a text record."
        attachments = [zip_name]
    else:
        nested_name = f"forwarded_record_{index:03d}.eml"
        nested_bytes = _eml_bytes(
            "Forwarded Record Details",
            ["Forwarding the enclosed record.", *field_lines],
            html_only=index % 5 == 0,
        )
        _add_nested_eml_attachment(message, nested_name, nested_bytes)
        source_ref = f"email_{index:03d}.eml > {nested_name}"
        notes = "Nested EML attachment containing record details."
        attachments = [nested_name]

    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="archive_or_forward",
        subject=subject,
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(
            source_ref,
            findings,
            location_kind="attachment",
            default_entity_name=person.full_name,
        ),
        attachments=attachments,
        expected_human_review=True,
        notes=notes,
    )
    return message, benchmark_file


def _build_multi_entity_case(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    primary = _make_person(index, seed)
    dependent = _make_person(index + 501, seed)
    subject = "Dependent Eligibility Documentation"
    body_lines = [
        f"Attached are the primary and dependent records for {primary.full_name}.",
        "Please verify that each finding is attributed to the correct person before release.",
        "Primary contact information is included in the worksheet.",
        f"Benefits inbox: {SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)]}",
    ]
    message = _compose_body(subject, "Benefits review team,", body_lines)

    headers = ["role", "full_name", "dob", "relationship", "ssn", "mrn", "phone"]
    rows = [
        ["employee", primary.full_name, primary.dob_text, "self", primary.ssn, primary.mrn, primary.phone],
        ["dependent", dependent.full_name, dependent.dob_text, "child", dependent.ssn, dependent.mrn, dependent.phone],
    ]
    attachment_filename = f"dependents_{index:03d}.xlsx"
    attachment = AttachmentSpec(
        filename=attachment_filename,
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=_xlsx_attachment("Dependents", headers, rows),
    )
    _add_attachment(message, attachment)
    source_ref = f"email_{index:03d}.eml > {attachment_filename}"
    findings = [
        ("FULL_NAME", primary.full_name, primary.full_name),
        ("DOB", primary.dob_text, primary.full_name),
        ("SSN", primary.ssn, primary.full_name),
        ("MRN", primary.mrn, primary.full_name),
        ("PHONE", primary.phone, primary.full_name),
        ("FULL_NAME", dependent.full_name, dependent.full_name),
        ("DOB", dependent.dob_text, dependent.full_name),
        ("SSN", dependent.ssn, dependent.full_name),
        ("MRN", dependent.mrn, dependent.full_name),
        ("PHONE", dependent.phone, dependent.full_name),
    ]
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="multi_entity_attachment",
        subject=subject,
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(source_ref, findings, attachment_filename=attachment_filename, location_kind="attachment"),
        attachments=[attachment_filename],
        expected_human_review=True,
        notes="Two-entity spreadsheet intended to stress attribution and escalation.",
    )
    return message, benchmark_file


def _build_negative_email(index: int) -> tuple[EmailMessage, BenchmarkFile]:
    subject = _negative_subject(index)
    body_lines = _negative_lines(index)
    message = _compose_body(subject, "Operations team,", body_lines, html_only=index % 10 == 0)

    attachments: list[str] = []
    if index % 2 == 0:
        attachment = _negative_attachment(index)
        _add_attachment(message, attachment)
        attachments.append(attachment.filename)

    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="negative_operational",
        subject=subject,
        contains_pii=False,
        expected_findings=[],
        attachments=attachments,
        expected_human_review=False,
        notes="Operational traffic with dates, ticket numbers, service contacts, and IPs but no personal-data exposure.",
    )
    return message, benchmark_file


def _profile_dataset_metadata(profile: str) -> tuple[str, str]:
    if profile == REALWORLD_V2_PROFILE:
        return (
            "pii-breach-benchmark-realworld-v2",
            "Second-generation synthetic breach-review benchmark with quoted reply chains, mixed attachments, "
            "security/login alerts, multi-entity review packets, and stronger operational negatives.",
        )
    if profile == REALWORLD_V3_PROFILE:
        return (
            "pii-breach-benchmark-realworld-v3",
            "Third-generation synthetic breach-review benchmark with attachment-first traffic, scanned PDFs and images, "
            "mixed review packets, nested forwarding chains, and negative controls designed to look operationally real.",
        )
    if profile == REALWORLD_V4_PROFILE:
        return (
            "pii-breach-benchmark-realworld-v4",
            "Fourth-generation synthetic breach-review benchmark with OCR-hostile scanned packets, mixed ZIP archives, "
            "nested forwarded submissions, multi-entity household evidence, and operational decoys designed to resemble real review traffic.",
        )
    return (
        "pii-breach-benchmark",
        "Synthetic but realistic breach-review benchmark with real email containers, parseable attachments, "
        "machine-readable ground truth, and explicit human-review scenarios.",
    )


def _chunk_lines(lines: list[str], size: int) -> list[list[str]]:
    return [lines[i : i + size] for i in range(0, len(lines), size)] or [[]]


def _build_visual_attachment(
    *,
    filename: str,
    title: str,
    lines: list[str],
    kind: str,
    low_contrast: bool = False,
) -> AttachmentSpec:
    if kind == "pdf":
        data = _pdf_attachment_bytes(title, _chunk_lines(lines, 14), low_contrast=low_contrast)
        mime_type = "application/pdf"
    elif kind == "jpg":
        data = _image_attachment_bytes(title, lines, image_format="JPEG", low_contrast=low_contrast)
        mime_type = "image/jpeg"
    elif kind == "png":
        data = _image_attachment_bytes(title, lines, image_format="PNG", low_contrast=low_contrast)
        mime_type = "image/png"
    else:
        raise ValueError(f"Unsupported visual attachment kind: {kind}")
    return AttachmentSpec(filename=filename, mime_type=mime_type, data=data)


def _build_negative_attachment_case_v3(index: int) -> tuple[EmailMessage, BenchmarkFile]:
    subject = _negative_subject(index)
    kind = ["pdf", "png", "jpg"][index % 3]
    lines = [
        "Operational review packet attached.",
        *_negative_lines(index),
        f"Runbook owner: {ORG_NAMES[(index + 3) % len(ORG_NAMES)]}",
        f"Escalation mailbox: ops@{WORK_DOMAINS[index % len(WORK_DOMAINS)]}",
        "Do not notify any external party from this thread.",
    ]
    attachment = _build_visual_attachment(
        filename=f"ops_snapshot_{index:03d}.{kind}",
        title="Operations Runbook Snapshot",
        lines=lines,
        kind=kind,
        low_contrast=index % 4 == 0,
    )
    message = _compose_body(
        subject,
        "Operations review team,",
        [
            "Attached is the latest runbook capture for internal coordination.",
            f"Ticket reference: {TICKET_CODES[index % len(TICKET_CODES)]}",
            "This packet should not contain customer, patient, or employee record data.",
        ],
        html_only=index % 5 == 0,
    )
    _add_attachment(message, attachment)
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="negative_scanned_operational_packet",
        subject=subject,
        contains_pii=False,
        expected_findings=[],
        attachments=[attachment.filename],
        expected_human_review=False,
        notes="Attachment-backed operational traffic with OCR-friendly screenshots but no personal-data exposure.",
    )
    return message, benchmark_file


def _build_identity_scan_case_v3(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    person = _make_person(index + 3000, seed)
    bundle_options = [
        ["FULL_NAME", "DOB", "SSN", "ADDRESS"],
        ["FULL_NAME", "DOB", "DRIVERS_LICENSE", "ADDRESS"],
        ["FULL_NAME", "DOB", "PASSPORT", "ADDRESS"],
        ["FULL_NAME", "DOB", "PHONE", "EMAIL"],
    ]
    bundle = bundle_options[index % len(bundle_options)]
    kind = ["pdf", "png", "jpg"][index % 3]
    field_lines, findings = _field_lines(person, bundle, index)
    attachment = _build_visual_attachment(
        filename=f"identity_scan_{index:03d}.{kind}",
        title="Identity Verification Submission",
        lines=[
            "Uploaded identity-review snapshot.",
            *field_lines,
            *_business_noise(index),
            "Release only after validation is complete.",
        ],
        kind=kind,
        low_contrast=index % 6 == 0,
    )
    message = _compose_body(
        "Identity Verification Escalation",
        "Identity review desk,",
        [
            f"Attached is the submission packet for {person.full_name}.",
            "The source came from a manual intake workflow and may require visual review.",
            f"Escalation mailbox: {SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)]}",
        ],
        html_only=index % 4 == 0,
    )
    _add_attachment(message, attachment)
    source_ref = f"email_{index:03d}.eml > {attachment.filename}"
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="identity_scan_packet",
        subject="Identity Verification Escalation",
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(
            source_ref,
            findings,
            attachment_filename=attachment.filename,
            location_kind="attachment",
            default_entity_name=person.full_name,
        ),
        attachments=[attachment.filename],
        expected_human_review=kind != "pdf" or any(token in bundle for token in ("SSN", "DRIVERS_LICENSE", "PASSPORT")),
        notes="Single-subject scanned identity or intake artifact delivered as PDF/PNG/JPG.",
    )
    return message, benchmark_file


def _build_medical_statement_case_v3(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    person = _make_person(index + 3400, seed)
    bundle_options = [
        ["FULL_NAME", "DOB", "MRN", "MEDICARE", "ICD10", "NDC", "ADDRESS"],
        ["FULL_NAME", "DOB", "MRN", "PHONE", "ADDRESS"],
        ["FULL_NAME", "DOB", "MEDICARE", "EMAIL", "ADDRESS"],
        ["FULL_NAME", "DOB", "MRN", "ICD10", "PHONE"],
    ]
    bundle = bundle_options[index % len(bundle_options)]
    kind = ["pdf", "pdf", "jpg"][index % 3]
    field_lines, findings = _field_lines(person, bundle, index)
    attachment = _build_visual_attachment(
        filename=f"medical_statement_{index:03d}.{kind}",
        title="Patient Statement Summary",
        lines=[
            f"Facility: {ORG_NAMES[index % len(ORG_NAMES)]}",
            "Statement prepared for breach-review validation.",
            *field_lines,
            f"Questions line: {SUPPORT_PHONES[index % len(SUPPORT_PHONES)]}",
            f"Service contact: {SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)]}",
        ],
        kind=kind,
        low_contrast=index % 7 == 0,
    )
    message = _compose_body(
        "Clinical Statement Review Packet",
        "Clinical privacy desk,",
        [
            f"Attached is the member statement packet for {person.full_name}.",
            "Please confirm diagnosis, medication, and member identifiers before release.",
            f"Reference ticket: {TICKET_CODES[index % len(TICKET_CODES)]}",
        ],
    )
    _add_attachment(message, attachment)
    source_ref = f"email_{index:03d}.eml > {attachment.filename}"
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="medical_statement_scan",
        subject="Clinical Statement Review Packet",
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(
            source_ref,
            findings,
            attachment_filename=attachment.filename,
            location_kind="attachment",
            default_entity_name=person.full_name,
        ),
        attachments=[attachment.filename],
        expected_human_review=kind != "pdf" or any(token in bundle for token in ("MEDICARE", "NDC")),
        notes="Healthcare-style statement packet stored as scanned PDF/JPG.",
    )
    return message, benchmark_file


def _build_finance_packet_case_v3(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    person = _make_person(index + 3800, seed)
    bundle_options = [
        ["FULL_NAME", "BANK_ACCOUNT", "DOB", "ADDRESS"],
        ["FULL_NAME", "CREDIT_CARD", "ADDRESS", "PHONE"],
        ["FULL_NAME", "IBAN", "ADDRESS", "EMAIL"],
        ["FULL_NAME", "EIN", "ADDRESS"],
    ]
    bundle = bundle_options[index % len(bundle_options)]
    positive_kind = ["pdf", "png", "jpg", "xlsx", "docx"][index % 5]
    field_lines, findings = _field_lines(person, bundle, index)
    if positive_kind in {"pdf", "png", "jpg"}:
        positive_attachment = _build_visual_attachment(
            filename=f"finance_record_{index:03d}.{positive_kind}",
            title="Payment Exception Backup",
            lines=[
                "Sensitive payment backup enclosed.",
                *field_lines,
                *_business_noise(index),
            ],
            kind=positive_kind,
            low_contrast=index % 8 == 0,
        )
    else:
        positive_attachment, _ = _positive_attachment_content(index, person, bundle, positive_kind)
    noise_attachment = _negative_attachment(index + 900)
    zip_name = f"payment_packet_{index:03d}.zip"
    zip_attachment = AttachmentSpec(
        filename=zip_name,
        mime_type="application/zip",
        data=_zip_attachment([positive_attachment, noise_attachment]),
    )
    message = _compose_body(
        "Payment Exception Packet",
        "Finance incident review,",
        [
            f"The attached packet includes source material for {person.full_name}.",
            "One member is a true record, and one document is general operational noise.",
            f"Escalation mailbox: {SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)]}",
        ],
    )
    _add_attachment(message, zip_attachment)
    source_ref = f"email_{index:03d}.eml > {zip_name}"
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="finance_zip_packet",
        subject="Payment Exception Packet",
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(
            source_ref,
            findings,
            attachment_filename=zip_name,
            location_kind="attachment",
            default_entity_name=person.full_name,
        ),
        attachments=[zip_name],
        expected_human_review=True,
        notes="ZIP review packet mixing a financial record with an unrelated operational document.",
    )
    return message, benchmark_file


def _build_nested_review_case_v3(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    person = _make_person(index + 4200, seed)
    bundle_options = [
        ["FULL_NAME", "DOB", "PHONE", "ADDRESS"],
        ["FULL_NAME", "DOB", "SSN", "ADDRESS"],
        ["FULL_NAME", "MRN", "DOB", "PHONE"],
        ["FULL_NAME", "DRIVERS_LICENSE", "DOB", "PHONE"],
    ]
    bundle = bundle_options[index % len(bundle_options)]
    kind = ["pdf", "png", "docx", "xlsx"][index % 4]
    field_lines, findings = _field_lines(person, bundle, index)
    if kind in {"pdf", "png"}:
        positive_attachment = _build_visual_attachment(
            filename=f"review_scan_{index:03d}.{kind}",
            title="Forwarded Review Attachment",
            lines=["Forwarded source artifact.", *field_lines, *_business_noise(index)],
            kind=kind,
            low_contrast=index % 5 == 0,
        )
    else:
        positive_attachment, _ = _positive_attachment_content(index, person, bundle, kind)
    noise_attachment = AttachmentSpec(
        filename=f"forward_note_{index:03d}.txt",
        mime_type="text/plain",
        data=_text_attachment(_negative_lines(index)),
    )
    nested_name = f"forwarded_review_{index:03d}.eml"
    nested_bytes = _eml_bytes(
        "Forwarded Review Source",
        [
            f"Forwarding the attached source artifact for {person.full_name}.",
            "Please keep the original context intact for review.",
            f"Ticket reference: {TICKET_CODES[index % len(TICKET_CODES)]}",
        ],
        attachments=[positive_attachment, noise_attachment],
        html_only=index % 4 == 0,
    )
    message = _compose_body(
        "Forwarded Submission Package",
        "Escalation intake,",
        [
            "See the attached forwarded message from the source team.",
            "Nested forwarding should still preserve the underlying record data.",
        ],
    )
    _add_nested_eml_attachment(message, nested_name, nested_bytes)
    source_ref = f"email_{index:03d}.eml > {nested_name}"
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="nested_forwarded_packet",
        subject="Forwarded Submission Package",
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(
            source_ref,
            findings,
            attachment_filename=nested_name,
            location_kind="attachment",
            default_entity_name=person.full_name,
        ),
        attachments=[nested_name],
        expected_human_review=True,
        notes="Nested EML with embedded record attachment and unrelated noise attachment.",
    )
    return message, benchmark_file


def _build_household_packet_case_v3(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    primary = _make_person(index + 4600, seed)
    dependent = _make_person(index + 5100, seed)
    primary_bundle = ["FULL_NAME", "DOB", "SSN", "ADDRESS", "PHONE"]
    dependent_bundle = ["FULL_NAME", "DOB", "MRN", "PHONE", "EMAIL"]
    primary_lines, primary_findings = _field_lines(primary, primary_bundle, index)
    dependent_lines, dependent_findings = _field_lines(dependent, dependent_bundle, index + 1)

    primary_attachment = _build_visual_attachment(
        filename=f"primary_applicant_{index:03d}.pdf",
        title="Primary Applicant Summary",
        lines=["Primary applicant data", *primary_lines],
        kind="pdf",
        low_contrast=index % 6 == 0,
    )
    dependent_attachment = _build_visual_attachment(
        filename=f"dependent_record_{index:03d}.png",
        title="Dependent Summary",
        lines=["Dependent data", *dependent_lines],
        kind="png",
    )
    worksheet_headers = ["role", "full name", "dob", "relationship", "phone", "personal email"]
    worksheet_rows = [
        ["primary", primary.full_name, primary.dob_text, "self", primary.phone, primary.personal_email],
        ["dependent", dependent.full_name, dependent.dob_text, "child", dependent.phone, dependent.personal_email],
    ]
    worksheet = AttachmentSpec(
        filename=f"household_roster_{index:03d}.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=_xlsx_attachment("Household", worksheet_headers, worksheet_rows),
    )
    zip_name = f"household_packet_{index:03d}.zip"
    zip_attachment = AttachmentSpec(
        filename=zip_name,
        mime_type="application/zip",
        data=_zip_attachment([primary_attachment, dependent_attachment, worksheet]),
    )
    message = _compose_body(
        "Household Packet Review",
        "Eligibility review team,",
        [
            f"Attached is the combined packet for {primary.full_name} and related household members.",
            "Keep primary and dependent findings attributed separately.",
            f"Benefits inbox: {SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)]}",
        ],
    )
    _add_attachment(message, zip_attachment)
    source_ref = f"email_{index:03d}.eml > {zip_name}"
    findings = [
        *[(pii_type, raw_value, primary.full_name) for pii_type, raw_value in primary_findings],
        *[(pii_type, raw_value, dependent.full_name) for pii_type, raw_value in dependent_findings],
    ]
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="household_zip_packet",
        subject="Household Packet Review",
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(
            source_ref,
            findings,
            attachment_filename=zip_name,
            location_kind="attachment",
        ),
        attachments=[zip_name],
        expected_human_review=True,
        notes="Attachment-first household packet with primary and dependent data spread across multiple members.",
    )
    return message, benchmark_file


def _build_negative_packet_case_v4(index: int) -> tuple[EmailMessage, BenchmarkFile]:
    subject = _negative_subject(index)
    visual_kind = ["pdf", "png", "jpg"][index % 3]
    visual_attachment = _build_visual_attachment(
        filename=f"ops_packet_{index:03d}.{visual_kind}",
        title="Internal Change-Control Snapshot",
        lines=[
            "Internal change-control evidence attached for review.",
            *_negative_lines(index),
            f"Runbook owner: {ORG_NAMES[(index + 2) % len(ORG_NAMES)]}",
            f"Escalation mailbox: ops@{WORK_DOMAINS[index % len(WORK_DOMAINS)]}",
            "This packet should not contain customer, employee, patient, or vendor record data.",
        ],
        kind=visual_kind,
        low_contrast=index % 4 == 0,
    )
    checklist_headers = ["ticket", "owner_team", "support_mailbox", "change_window", "source_ip"]
    checklist_rows = [[
        TICKET_CODES[index % len(TICKET_CODES)],
        ORG_NAMES[index % len(ORG_NAMES)],
        SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)],
        f"2026-0{(index % 9) + 1}-2{index % 8}",
        f"203.{(index * 7) % 180}.{(index * 5) % 200}.{(index * 3) % 200 + 1}",
    ]]
    checklist_attachment = AttachmentSpec(
        filename=f"ops_checklist_{index:03d}.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=_xlsx_attachment("OpsChecklist", checklist_headers, checklist_rows),
    )
    message = _compose_body(
        subject,
        "Operations review team,",
        [
            "Attached is the latest internal evidence bundle for maintenance-window review.",
            "The attachments contain service contacts, ticket references, and source IPs only.",
            "No breach notification work should be opened from this thread.",
        ],
        html_only=index % 5 == 0,
    )
    _add_attachment(message, visual_attachment)
    _add_attachment(message, checklist_attachment)
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="negative_mixed_operations_packet",
        subject=subject,
        contains_pii=False,
        expected_findings=[],
        attachments=[visual_attachment.filename, checklist_attachment.filename],
        expected_human_review=False,
        notes="Operational packet with scanned evidence and structured checklist data but no exposed personal-data record.",
    )
    return message, benchmark_file


def _build_identity_archive_case_v4(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    person = _make_person(index + 5600, seed)
    bundle_options = [
        ["FULL_NAME", "DOB", "SSN", "ADDRESS", "PHONE"],
        ["FULL_NAME", "DOB", "DRIVERS_LICENSE", "ADDRESS", "EMAIL"],
        ["FULL_NAME", "DOB", "PASSPORT", "ADDRESS", "PHONE"],
        ["FULL_NAME", "DOB", "ADDRESS", "EMAIL", "PHONE"],
    ]
    bundle = bundle_options[index % len(bundle_options)]
    field_lines, findings = _field_lines(person, bundle, index)
    scan_kind = ["pdf", "png", "jpg"][index % 3]
    scan_attachment = _build_visual_attachment(
        filename=f"identity_capture_{index:03d}.{scan_kind}",
        title="Identity Archive Capture",
        lines=[
            "Archive intake captured the following personal record.",
            *field_lines,
            *_business_noise(index),
            "Release only after the scanned evidence is validated.",
        ],
        kind=scan_kind,
        low_contrast=index % 5 == 0,
    )
    cover_attachment = AttachmentSpec(
        filename=f"archive_cover_{index:03d}.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        data=_docx_attachment(
            "Archive Intake Note",
            [
                "This archive packet contains one scanned identity artifact and one internal cover note.",
                f"Escalation mailbox: {SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)]}",
                f"Coordinator alias: privacy@{WORK_DOMAINS[index % len(WORK_DOMAINS)]}",
                f"Reference ticket: {TICKET_CODES[index % len(TICKET_CODES)]}",
                "Do not infer the coordinator mailbox as the subject owner of any detected data.",
            ],
        ),
    )
    ops_note = AttachmentSpec(
        filename=f"archive_ops_note_{index:03d}.txt",
        mime_type="text/plain",
        data=_text_attachment(_negative_lines(index)),
    )
    zip_name = f"identity_archive_{index:03d}.zip"
    zip_attachment = AttachmentSpec(
        filename=zip_name,
        mime_type="application/zip",
        data=_zip_attachment([scan_attachment, cover_attachment, ops_note]),
    )
    message = _compose_body(
        "Archive Identity Evidence Review",
        "Archive review desk,",
        [
            f"Attached is the recovered archive packet for {person.full_name}.",
            "It contains one scanned identity artifact plus internal coordination material.",
            f"Service mailbox: {SUPPORT_EMAILS[(index + 1) % len(SUPPORT_EMAILS)]}",
        ],
        html_only=index % 4 == 0,
    )
    _add_attachment(message, zip_attachment)
    source_ref = f"email_{index:03d}.eml > {zip_name}"
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="identity_archive_packet_v4",
        subject="Archive Identity Evidence Review",
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(
            source_ref,
            findings,
            attachment_filename=zip_name,
            location_kind="attachment",
            default_entity_name=person.full_name,
        ),
        attachments=[zip_name],
        expected_human_review=True,
        notes="Identity archive ZIP containing one scanned record artifact and multiple non-record decoy attachments.",
    )
    return message, benchmark_file


def _build_medical_forward_case_v4(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    person = _make_person(index + 6000, seed)
    bundle_options = [
        ["FULL_NAME", "DOB", "MRN", "MEDICARE", "ICD10", "ADDRESS"],
        ["FULL_NAME", "DOB", "MRN", "NDC", "PHONE", "ADDRESS"],
        ["FULL_NAME", "DOB", "MEDICARE", "ICD10", "EMAIL", "ADDRESS"],
        ["FULL_NAME", "DOB", "MRN", "PHONE", "EMAIL"],
    ]
    bundle = bundle_options[index % len(bundle_options)]
    field_lines, findings = _field_lines(person, bundle, index)
    scan_kind = ["pdf", "jpg", "png"][index % 3]
    scan_attachment = _build_visual_attachment(
        filename=f"clinical_capture_{index:03d}.{scan_kind}",
        title="Clinical Intake Snapshot",
        lines=[
            f"Facility: {ORG_NAMES[index % len(ORG_NAMES)]}",
            "Forwarded clinical intake evidence.",
            *field_lines,
            f"Questions line: {SUPPORT_PHONES[index % len(SUPPORT_PHONES)]}",
            f"Coordination mailbox: {SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)]}",
        ],
        kind=scan_kind,
        low_contrast=index % 6 == 0,
    )
    nested_name = f"clinical_forward_{index:03d}.eml"
    nested_bytes = _eml_bytes(
        "Forwarded Clinical Evidence",
        [
            f"Forwarding the scanned intake packet for {person.full_name}.",
            "Keep the original evidence intact for review.",
            f"Escalation ticket: {TICKET_CODES[index % len(TICKET_CODES)]}",
        ],
        attachments=[scan_attachment, _negative_attachment(index + 1400)],
        html_only=index % 3 == 0,
    )
    message = _compose_body(
        "Forwarded Clinical Review Packet",
        "Clinical privacy desk,",
        [
            "The source team forwarded a nested message with scanned evidence and one operational attachment.",
            "The clinical identifiers belong to the member in the forwarded evidence, not to the routing mailbox.",
        ],
    )
    _add_nested_eml_attachment(message, nested_name, nested_bytes)
    source_ref = f"email_{index:03d}.eml > {nested_name}"
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="medical_forward_chain_v4",
        subject="Forwarded Clinical Review Packet",
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(
            source_ref,
            findings,
            attachment_filename=nested_name,
            location_kind="attachment",
            default_entity_name=person.full_name,
        ),
        attachments=[nested_name],
        expected_human_review=True,
        notes="Nested forwarded clinical packet with scanned evidence and operational decoys.",
    )
    return message, benchmark_file


def _build_finance_archive_case_v4(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    person = _make_person(index + 6400, seed)
    bundle_options = [
        ["FULL_NAME", "BANK_ACCOUNT", "DOB", "ADDRESS", "PHONE"],
        ["FULL_NAME", "CREDIT_CARD", "ADDRESS", "EMAIL"],
        ["FULL_NAME", "IBAN", "ADDRESS", "PHONE"],
        ["FULL_NAME", "EIN", "ADDRESS", "EMAIL"],
    ]
    bundle = bundle_options[index % len(bundle_options)]
    field_lines, findings = _field_lines(person, bundle, index)
    positive_kind = ["pdf", "png", "xlsx", "docx"][index % 4]
    if positive_kind in {"pdf", "png"}:
        positive_attachment = _build_visual_attachment(
            filename=f"finance_capture_{index:03d}.{positive_kind}",
            title="Finance Exception Backup",
            lines=[
                "Sensitive payment evidence enclosed.",
                *field_lines,
                *_business_noise(index),
            ],
            kind=positive_kind,
            low_contrast=index % 7 == 0,
        )
    else:
        positive_attachment, _ = _positive_attachment_content(index, person, bundle, positive_kind)
    review_sheet = AttachmentSpec(
        filename=f"finance_review_{index:03d}.csv",
        mime_type="text/csv",
        data=_csv_attachment(
            ["ticket", "routing_mailbox", "callback", "status"],
            [[
                TICKET_CODES[index % len(TICKET_CODES)],
                SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)],
                SUPPORT_PHONES[index % len(SUPPORT_PHONES)],
                "Escalated",
            ]],
        ),
    )
    zip_name = f"finance_archive_{index:03d}.zip"
    zip_attachment = AttachmentSpec(
        filename=zip_name,
        mime_type="application/zip",
        data=_zip_attachment([positive_attachment, review_sheet, _negative_attachment(index + 1700)]),
    )
    message = _compose_body(
        "Finance Archive Review Packet",
        "Finance breach desk,",
        [
            f"The attached archive contains a payment-review artifact for {person.full_name}.",
            "The same archive also includes routing paperwork and one unrelated operations note.",
            f"Coordinator inbox: accounting@{WORK_DOMAINS[index % len(WORK_DOMAINS)]}",
        ],
    )
    _add_attachment(message, zip_attachment)
    source_ref = f"email_{index:03d}.eml > {zip_name}"
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="finance_archive_packet_v4",
        subject="Finance Archive Review Packet",
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(
            source_ref,
            findings,
            attachment_filename=zip_name,
            location_kind="attachment",
            default_entity_name=person.full_name,
        ),
        attachments=[zip_name],
        expected_human_review=True,
        notes="Finance archive ZIP mixing one true payment artifact with review metadata and unrelated noise.",
    )
    return message, benchmark_file


def _build_household_crosspacket_case_v4(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    primary = _make_person(index + 6900, seed)
    dependent = _make_person(index + 7423, seed)
    if dependent.full_name == primary.full_name:
        dependent = _make_person(index + 7499, seed)
    primary_lines, primary_findings = _field_lines(primary, ["FULL_NAME", "DOB", "SSN", "ADDRESS", "PHONE"], index)
    dependent_lines, dependent_findings = _field_lines(dependent, ["FULL_NAME", "DOB", "MRN", "EMAIL", "PHONE"], index + 1)
    primary_scan = _build_visual_attachment(
        filename=f"primary_capture_{index:03d}.pdf",
        title="Primary Applicant Snapshot",
        lines=["Primary applicant evidence", *primary_lines],
        kind="pdf",
        low_contrast=index % 6 == 0,
    )
    dependent_scan = _build_visual_attachment(
        filename=f"dependent_capture_{index:03d}.jpg",
        title="Dependent Snapshot",
        lines=["Dependent evidence", *dependent_lines],
        kind="jpg",
        low_contrast=index % 5 == 0,
    )
    roster_headers = ["role", "full_name", "relationship", "dob", "phone", "personal_email"]
    roster_rows = [
        ["primary", primary.full_name, "self", primary.dob_text, primary.phone, primary.personal_email],
        ["dependent", dependent.full_name, "child", dependent.dob_text, dependent.phone, dependent.personal_email],
    ]
    roster_attachment = AttachmentSpec(
        filename=f"household_roster_{index:03d}.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=_xlsx_attachment("HouseholdRoster", roster_headers, roster_rows),
    )
    zip_name = f"household_crosspacket_{index:03d}.zip"
    zip_attachment = AttachmentSpec(
        filename=zip_name,
        mime_type="application/zip",
        data=_zip_attachment([primary_scan, dependent_scan, roster_attachment, _negative_attachment(index + 2000)]),
    )
    message = _compose_body(
        "Household Evidence Packet",
        "Eligibility review team,",
        [
            f"Attached is the combined evidence packet for {primary.full_name} and related household members.",
            "Keep the primary and dependent findings attributed to the correct person.",
            f"Benefits inbox: {SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)]}",
        ],
    )
    _add_attachment(message, zip_attachment)
    source_ref = f"email_{index:03d}.eml > {zip_name}"
    findings = [
        *[(pii_type, raw_value, primary.full_name) for pii_type, raw_value in primary_findings],
        *[(pii_type, raw_value, dependent.full_name) for pii_type, raw_value in dependent_findings],
    ]
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="household_crosspacket_v4",
        subject="Household Evidence Packet",
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(
            source_ref,
            findings,
            attachment_filename=zip_name,
            location_kind="attachment",
        ),
        attachments=[zip_name],
        expected_human_review=True,
        notes="Household ZIP packet with separate primary/dependent scans plus a roster worksheet and operational decoy.",
    )
    return message, benchmark_file


def _build_access_capture_case_v4(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    person = _make_person(index + 7800, seed)
    findings = [
        ("FULL_NAME", person.full_name),
        ("EMAIL", person.personal_email),
        ("PHONE", person.phone),
        ("IPV4", person.ipv4),
    ]
    screenshot_kind = ["png", "jpg"][index % 2]
    screenshot_attachment = _build_visual_attachment(
        filename=f"access_capture_{index:03d}.{screenshot_kind}",
        title="Portal Access Screenshot",
        lines=[
            "Captured profile from portal review.",
            f"Full Name: {person.full_name}",
            f"Personal Email: {person.personal_email}",
            f"Mobile Phone: {person.phone}",
            f"Login IP Address: {person.ipv4}",
            f"Service mailbox: {SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)]}",
        ],
        kind=screenshot_kind,
        low_contrast=index % 4 == 0,
    )
    note_attachment = AttachmentSpec(
        filename=f"access_review_{index:03d}.txt",
        mime_type="text/plain",
        data=_text_attachment(
            [
                "Profile capture attached for access-review validation.",
                f"Routing mailbox: security@{WORK_DOMAINS[index % len(WORK_DOMAINS)]}",
                f"Ticket reference: {TICKET_CODES[index % len(TICKET_CODES)]}",
            ]
        ),
    )
    message = _compose_body(
        "Portal Access Review Capture",
        "Security review desk,",
        [
            "The attached profile screenshot should be reviewed for user-level data exposure.",
            "Do not confuse the security mailbox with the record owner.",
        ],
    )
    _add_attachment(message, screenshot_attachment)
    _add_attachment(message, note_attachment)
    source_ref = f"email_{index:03d}.eml > {screenshot_attachment.filename}"
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="access_capture_v4",
        subject="Portal Access Review Capture",
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(
            source_ref,
            findings,
            attachment_filename=screenshot_attachment.filename,
            location_kind="attachment",
            default_entity_name=person.full_name,
        ),
        attachments=[screenshot_attachment.filename, note_attachment.filename],
        expected_human_review=screenshot_kind == "jpg",
        notes="Scanned or screenshot-style access capture with user contact and login IP details plus routing-note decoys.",
    )
    return message, benchmark_file


def _build_negative_email_v2(index: int) -> tuple[EmailMessage, BenchmarkFile]:
    subject = _negative_subject(index)
    org = ORG_NAMES[index % len(ORG_NAMES)]
    forwarded_lines = _negative_lines(index)
    body_lines = [
        f"{org} circulated the operational thread below for internal coordination only.",
        "No customer or employee record should be present in the quoted content.",
        "",
        "----- Forwarded message -----",
        f"From: ops@{WORK_DOMAINS[index % len(WORK_DOMAINS)]}",
        f"Subject: {subject}",
        *[f"> {line}" for line in forwarded_lines],
    ]
    message = _compose_body(subject, "Operations review team,", body_lines, html_only=index % 4 == 0)

    attachments: list[str] = []
    if index % 2 == 0:
        attachment = _negative_attachment(index)
        _add_attachment(message, attachment)
        attachments.append(attachment.filename)

    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="negative_operational_thread",
        subject=subject,
        contains_pii=False,
        expected_findings=[],
        attachments=attachments,
        expected_human_review=False,
        notes="Quoted operational mail with dates, service contacts, and IPs but no person-level data.",
    )
    return message, benchmark_file


def _build_security_alert_case(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    person = _make_person(index + 1200, seed)
    subject = "Suspicious Login Validation"
    findings = [("FULL_NAME", person.full_name), ("IPV4", person.ipv4), ("EMAIL", person.personal_email), ("PHONE", person.phone)]
    body_lines = [
        f"We detected a portal sign-in associated with {person.personal_email}.",
        f"Security mailbox: {SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)]}",
        f"Case reference: {TICKET_CODES[index % len(TICKET_CODES)]}",
        "User profile snapshot:",
        f"Full Name: {person.full_name}",
        f"Login IP Address: {person.ipv4}",
        f"Personal Email: {person.personal_email}",
        f"Mobile Phone: {person.phone}",
    ]
    message = _compose_body(subject, "Security operations,", body_lines, html_only=index % 5 == 0)
    source_ref = f"email_{index:03d}.eml (email body)"
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="security_login_alert",
        subject=subject,
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(source_ref, findings, default_entity_name=person.full_name),
        expected_human_review=index % 10 == 0,
        notes="Account-security alert with user-level login IP, personal email, and callback contact.",
    )
    return message, benchmark_file


def _build_threaded_body_case(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    person = _make_person(index + 1500, seed)
    bundle = POSITIVE_BUNDLES[(index * 5) % len(POSITIVE_BUNDLES)]
    subject = f"Fwd: {_positive_subject(index, bundle)}"
    field_lines, findings = _field_lines(person, bundle, index)
    body_lines = [
        f"Forwarding the quoted intake excerpt for {person.full_name}.",
        f"Reply mailbox: {SUPPORT_EMAILS[(index + 1) % len(SUPPORT_EMAILS)]}",
        "Only the quoted record block should be treated as candidate personal data.",
        "",
        "----- Original Message -----",
        f"From: intake@{WORK_DOMAINS[index % len(WORK_DOMAINS)]}",
        f"Subject: {_positive_subject(index, bundle)}",
        *[f"> {line}" for line in field_lines],
        f"> Ticket reference: {TICKET_CODES[index % len(TICKET_CODES)]}",
        f"> Questions line: {SUPPORT_PHONES[index % len(SUPPORT_PHONES)]}",
    ]
    message = _compose_body(subject, "Review desk,", body_lines, html_only=index % 3 == 0)
    source_ref = f"email_{index:03d}.eml (email body)"
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="quoted_reply_chain",
        subject=subject,
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(source_ref, findings, default_entity_name=person.full_name),
        expected_human_review=index % 9 == 0,
        notes="Quoted reply chain with the record embedded in forwarded text.",
    )
    return message, benchmark_file


def _build_mixed_attachment_case(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    person = _make_person(index + 1800, seed)
    bundle = POSITIVE_BUNDLES[(index * 7) % len(POSITIVE_BUNDLES)]
    subject = _positive_subject(index, bundle)
    body_lines = [
        f"Attached is the case packet for {person.full_name}.",
        "The packet includes one customer record and one operations note.",
        f"Internal ticket: {TICKET_CODES[index % len(TICKET_CODES)]}",
        f"Support mailbox: {SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)]}",
    ]
    message = _compose_body(subject, "Case preparation team,", body_lines)

    attachment_kind_rotation = ["txt", "csv", "xlsx", "docx", "rtf", "zip", "nested"]
    positive_kind = attachment_kind_rotation[index % len(attachment_kind_rotation)]
    positive_attachment, findings = _positive_attachment_content(index, person, bundle, positive_kind)
    noise_attachment = _negative_attachment(index + 400)

    if positive_attachment.mime_type == "message/rfc822":
        _add_nested_eml_attachment(message, positive_attachment.filename, positive_attachment.data)
    else:
        _add_attachment(message, positive_attachment)
    _add_attachment(message, noise_attachment)

    attachment_source_ref = f"email_{index:03d}.eml > {positive_attachment.filename}"
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="mixed_attachment_packet",
        subject=subject,
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(
            attachment_source_ref,
            findings,
            attachment_filename=positive_attachment.filename,
            location_kind="attachment",
            default_entity_name=person.full_name,
        ),
        attachments=[positive_attachment.filename, noise_attachment.filename],
        expected_human_review=index % 6 == 0,
        notes="Mixed packet containing one real record attachment and one operational-noise attachment.",
    )
    return message, benchmark_file


def _build_multi_entity_case_v2(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    primary = _make_person(index + 2000, seed)
    secondary = _make_person(index + 2500, seed)
    subject = "Household Coverage Review"
    body_lines = [
        f"Attached are the related applicant records for {primary.full_name}.",
        "Review the primary and co-applicant entries separately before disclosure.",
        f"Benefits inbox: {SUPPORT_EMAILS[index % len(SUPPORT_EMAILS)]}",
    ]
    message = _compose_body(subject, "Eligibility review team,", body_lines)

    kind = ["xlsx", "csv", "docx"][index % 3]
    headers = ["role", "full name", "relationship", "dob", "ssn", "mrn", "phone", "personal email"]
    rows = [
        ["primary", primary.full_name, "self", primary.dob_text, primary.ssn, primary.mrn, primary.phone, primary.personal_email],
        ["co-applicant", secondary.full_name, "spouse", secondary.dob_text, secondary.ssn, secondary.mrn, secondary.phone, secondary.personal_email],
    ]
    if kind == "xlsx":
        attachment = AttachmentSpec(
            filename=f"household_{index:03d}.xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            data=_xlsx_attachment("Household", headers, rows),
        )
    elif kind == "csv":
        attachment = AttachmentSpec(
            filename=f"household_{index:03d}.csv",
            mime_type="text/csv",
            data=_csv_attachment(headers, rows),
        )
    else:
        attachment = AttachmentSpec(
            filename=f"household_{index:03d}.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            data=_docx_attachment("Household Coverage", ["Two related applicants are listed below."], headers=headers, rows=rows),
        )
    _add_attachment(message, attachment)

    source_ref = f"email_{index:03d}.eml > {attachment.filename}"
    findings = [
        ("FULL_NAME", primary.full_name, primary.full_name),
        ("DOB", primary.dob_text, primary.full_name),
        ("SSN", primary.ssn, primary.full_name),
        ("MRN", primary.mrn, primary.full_name),
        ("PHONE", primary.phone, primary.full_name),
        ("EMAIL", primary.personal_email, primary.full_name),
        ("FULL_NAME", secondary.full_name, secondary.full_name),
        ("DOB", secondary.dob_text, secondary.full_name),
        ("SSN", secondary.ssn, secondary.full_name),
        ("MRN", secondary.mrn, secondary.full_name),
        ("PHONE", secondary.phone, secondary.full_name),
        ("EMAIL", secondary.personal_email, secondary.full_name),
    ]
    benchmark_file = BenchmarkFile(
        eml_filename=f"email_{index:03d}.eml",
        scenario_id="household_multi_entity",
        subject=subject,
        contains_pii=True,
        expected_findings=_expected_findings_from_pairs(source_ref, findings, attachment_filename=attachment.filename, location_kind="attachment"),
        attachments=[attachment.filename],
        expected_human_review=True,
        notes="Household or co-applicant attachment intended to stress multi-entity review handling.",
    )
    return message, benchmark_file


def _scenario_for_index(index: int, seed: int) -> tuple[EmailMessage, BenchmarkFile]:
    if index <= 100:
        return _build_negative_email(index)
    if index <= 170:
        return _build_body_positive(index, seed)
    if index <= 255:
        return _build_attachment_positive(index, seed)
    if index <= 280:
        return _build_zip_or_nested(index, seed)
    return _build_multi_entity_case(index, seed)


def _scenario_for_profile(profile: str, index: int, seed: int, *, relative_index: int, total_files: int) -> tuple[EmailMessage, BenchmarkFile]:
    if profile == DEFAULT_BENCHMARK_PROFILE:
        return _scenario_for_index(index, seed)

    if profile == REALWORLD_V4_PROFILE:
        ratio = relative_index / max(total_files, 1)
        if ratio <= 0.16:
            return _build_negative_packet_case_v4(index)
        if ratio <= 0.34:
            return _build_identity_archive_case_v4(index, seed)
        if ratio <= 0.52:
            return _build_medical_forward_case_v4(index, seed)
        if ratio <= 0.70:
            return _build_finance_archive_case_v4(index, seed)
        if ratio <= 0.88:
            return _build_household_crosspacket_case_v4(index, seed)
        return _build_access_capture_case_v4(index, seed)

    if profile == REALWORLD_V3_PROFILE:
        ratio = relative_index / max(total_files, 1)
        if ratio <= 0.18:
            return _build_negative_attachment_case_v3(index)
        if ratio <= 0.36:
            return _build_identity_scan_case_v3(index, seed)
        if ratio <= 0.54:
            return _build_medical_statement_case_v3(index, seed)
        if ratio <= 0.72:
            return _build_finance_packet_case_v3(index, seed)
        if ratio <= 0.88:
            return _build_nested_review_case_v3(index, seed)
        return _build_household_packet_case_v3(index, seed)

    if profile != REALWORLD_V2_PROFILE:
        raise ValueError(f"Unsupported benchmark profile: {profile}")

    ratio = relative_index / max(total_files, 1)
    if ratio <= 0.23:
        return _build_negative_email_v2(index)
    if ratio <= 0.4:
        return _build_security_alert_case(index, seed)
    if ratio <= 0.62:
        return _build_threaded_body_case(index, seed)
    if ratio <= 0.84:
        return _build_mixed_attachment_case(index, seed)
    return _build_multi_entity_case_v2(index, seed)
