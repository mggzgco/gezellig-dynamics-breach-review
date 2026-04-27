#!/usr/bin/env python3
"""
Quick test script to verify the application works correctly
"""
import sys
import json
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.processing.eml_parser import parse_eml_file
from app.processing.attachment_handler import extract_text_from_attachment
from app.processing.pii_engine import scan_text
from app.processing.person_resolver import resolve_persons
from app.processing.risk_scorer import update_person_risk
from app.models import EmailAnalysisResult

def test_eml_parsing():
    """Test EML file parsing"""
    print("=" * 60)
    print("TEST 1: EML Parsing")
    print("=" * 60)

    test_file = Path("test_data/employee_records_001.eml")
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        return False

    result = parse_eml_file(str(test_file))

    print(f"✓ From: {result['from_address']}")
    print(f"✓ To: {', '.join(result['to_addresses'])}")
    print(f"✓ Subject: {result['subject']}")
    print(f"✓ Body length: {len(result['body_text'])} chars")
    print(f"✓ Attachments: {len(result['attachments'])}")

    return True


def test_pii_scanning():
    """Test PII detection"""
    print("\n" + "=" * 60)
    print("TEST 2: PII Detection")
    print("=" * 60)

    test_file = Path("test_data/employee_records_001.eml")
    result = parse_eml_file(str(test_file))
    body_text = result['body_text']

    matches = scan_text(body_text, "employee_records_001.eml (email body)")

    print(f"✓ Found {len(matches)} PII matches:")
    for match in matches[:10]:  # Show first 10
        print(f"  - {match.pii_type} ({match.risk_level}): {match.redacted_value}")
        print(f"    Source: {match.source_ref}")

    return len(matches) > 0


def test_person_resolution():
    """Test person resolution and risk scoring"""
    print("\n" + "=" * 60)
    print("TEST 3: Person Resolution & Risk Scoring")
    print("=" * 60)

    test_files = list(Path("test_data").glob("*.eml"))

    if not test_files:
        print("❌ No test files found")
        return False

    # Process all test files
    email_results = []
    for test_file in sorted(test_files)[:3]:
        eml_data = parse_eml_file(str(test_file))

        result = EmailAnalysisResult(
            eml_filename=test_file.name,
            from_address=eml_data.get("from_address"),
            to_addresses=eml_data.get("to_addresses", []),
            cc_addresses=eml_data.get("cc_addresses", []),
            bcc_addresses=eml_data.get("bcc_addresses", []),
            subject=eml_data.get("subject", ""),
        )

        # Scan body
        body_text = eml_data.get("body_text", "")
        if body_text:
            matches = scan_text(body_text, f"{test_file.name} (body)")
            result.pii_matches.extend(matches)

        email_results.append(result)

    # Resolve persons
    persons = resolve_persons(email_results)

    print(f"✓ Processed {len(email_results)} emails")
    print(f"✓ Identified {len(persons)} persons:")

    for person in persons[:5]:
        print(f"  - {person.canonical_name or person.canonical_email or 'UNATTRIBUTED'}")
        print(f"    Email: {person.canonical_email}")
        print(f"    PII count: {len(person.pii_matches)}")

        # Score risk
        update_person_risk(person)
        print(f"    Risk: {person.highest_risk_level} (score: {person.risk_score:.1f})")
        print(f"    Regulations: {[k for k,v in person.regulations_triggered.items() if v]}")

    return len(persons) > 0


def test_report_generation():
    """Test HTML and CSV report generation"""
    print("\n" + "=" * 60)
    print("TEST 4: Report Generation")
    print("=" * 60)

    from app.reporting.html_report import generate_html_report
    from app.reporting.csv_report import generate_csv_report

    # Create test persons data
    test_files = list(Path("test_data").glob("*.eml"))
    email_results = []

    for test_file in sorted(test_files)[:3]:
        eml_data = parse_eml_file(str(test_file))
        result = EmailAnalysisResult(
            eml_filename=test_file.name,
            from_address=eml_data.get("from_address"),
            to_addresses=eml_data.get("to_addresses", []),
            cc_addresses=eml_data.get("cc_addresses", []),
            bcc_addresses=eml_data.get("bcc_addresses", []),
            subject=eml_data.get("subject", ""),
        )
        body_text = eml_data.get("body_text", "")
        if body_text:
            matches = scan_text(body_text, f"{test_file.name} (body)")
            result.pii_matches.extend(matches)
        email_results.append(result)

    persons = resolve_persons(email_results)
    for person in persons:
        update_person_risk(person)

    # Create test output directory
    test_output = Path("test_data/test_job")
    test_output.mkdir(exist_ok=True)

    # Generate reports
    html_path = generate_html_report("test_job", persons, email_results, test_output.parent)
    csv_path = generate_csv_report("test_job", persons, test_output.parent)

    print(f"✓ HTML report: {html_path}")
    print(f"  Size: {html_path.stat().st_size:,} bytes")

    print(f"✓ CSV report: {csv_path}")
    print(f"  Size: {csv_path.stat().st_size:,} bytes")

    # Verify files exist
    return html_path.exists() and csv_path.exists()


if __name__ == "__main__":
    print("\n🧪 PII Breach Analyzer - Test Suite\n")

    tests = [
        ("EML Parsing", test_eml_parsing),
        ("PII Scanning", test_pii_scanning),
        ("Person Resolution", test_person_resolution),
        ("Report Generation", test_report_generation),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, p in results if p)
    total = len(results)
    print(f"✓ Passed: {passed}/{total}")

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")

    sys.exit(0 if passed == total else 1)
