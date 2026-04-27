# Benchmark Ground Truth Summary

- Dataset: pii-breach-benchmark-realworld-v3
- Seed: 20260421
- Total files: 150
- Files with PII: 123
- Files without PII: 27
- Total expected findings: 641
- Files expected to need human review: 111

## Type Coverage

| PII Type | Findings | Files |
|---|---:|---:|
| ADDRESS | 98 | 98 |
| BANK_ACCOUNT | 14 | 7 |
| CREDIT_CARD | 6 | 6 |
| DOB | 121 | 103 |
| DRIVERS_LICENSE | 13 | 13 |
| EIN | 7 | 7 |
| EMAIL | 37 | 37 |
| FULL_NAME | 141 | 123 |
| IBAN | 7 | 7 |
| ICD10 | 14 | 14 |
| MEDICARE | 13 | 13 |
| MRN | 45 | 45 |
| NDC | 7 | 7 |
| PASSPORT | 7 | 7 |
| PHONE | 80 | 62 |
| SSN | 31 | 31 |

## Notes

- This corpus is synthetic but formatted as realistic operational email and attachment traffic.
- Ground truth is stored in `ground_truth.json`; this markdown file is only a readable summary.
- Attachments are real parseable files and include TXT, CSV, DOCX, XLSX, RTF, ZIP, and nested EML examples.
- Negative controls intentionally include dates, service contacts, ticket IDs, and infrastructure IPs to measure false positives.
