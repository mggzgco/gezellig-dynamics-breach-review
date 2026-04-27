# Benchmark Ground Truth Summary

- Dataset: pii-breach-benchmark-realworld-v4
- Seed: 20260421
- Total files: 150
- Files with PII: 126
- Files without PII: 24
- Total expected findings: 755
- Files expected to need human review: 117

## Type Coverage

| PII Type | Findings | Files |
|---|---:|---:|
| ADDRESS | 102 | 102 |
| BANK_ACCOUNT | 14 | 7 |
| CREDIT_CARD | 7 | 7 |
| DOB | 115 | 88 |
| DRIVERS_LICENSE | 7 | 7 |
| EIN | 7 | 7 |
| EMAIL | 86 | 86 |
| FULL_NAME | 153 | 126 |
| IBAN | 6 | 6 |
| ICD10 | 14 | 14 |
| IPV4 | 18 | 18 |
| MEDICARE | 14 | 14 |
| MRN | 47 | 47 |
| NDC | 7 | 7 |
| PASSPORT | 7 | 7 |
| PHONE | 118 | 91 |
| SSN | 33 | 33 |

## Notes

- This corpus is synthetic but formatted as realistic operational email and attachment traffic.
- Ground truth is stored in `ground_truth.json`; this markdown file is only a readable summary.
- Attachments are real parseable files and include TXT, CSV, DOCX, XLSX, RTF, ZIP, and nested EML examples.
- Negative controls intentionally include dates, service contacts, ticket IDs, and infrastructure IPs to measure false positives.
