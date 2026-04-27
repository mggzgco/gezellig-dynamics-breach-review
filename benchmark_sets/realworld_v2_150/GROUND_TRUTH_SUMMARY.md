# Benchmark Ground Truth Summary

- Dataset: pii-breach-benchmark-realworld-v2
- Seed: 20260421
- Total files: 150
- Files with PII: 116
- Files without PII: 34
- Total expected findings: 636
- Files expected to need human review: 37

## Type Coverage

| PII Type | Findings | Files |
|---|---:|---:|
| ADDRESS | 33 | 33 |
| BANK_ACCOUNT | 8 | 4 |
| CREDIT_CARD | 4 | 4 |
| DOB | 90 | 66 |
| DRIVERS_LICENSE | 4 | 4 |
| EIN | 4 | 4 |
| EMAIL | 91 | 67 |
| FULL_NAME | 140 | 116 |
| IBAN | 4 | 4 |
| ICD10 | 4 | 4 |
| IPV4 | 30 | 30 |
| MEDICARE | 4 | 4 |
| MRN | 52 | 28 |
| NDC | 4 | 4 |
| NPI | 4 | 4 |
| PASSPORT | 4 | 4 |
| PHONE | 95 | 71 |
| SIN | 4 | 4 |
| SSN | 53 | 29 |
| VIN | 4 | 4 |

## Notes

- This corpus is synthetic but formatted as realistic operational email and attachment traffic.
- Ground truth is stored in `ground_truth.json`; this markdown file is only a readable summary.
- Attachments are real parseable files and include TXT, CSV, DOCX, XLSX, RTF, ZIP, and nested EML examples.
- Negative controls intentionally include dates, service contacts, ticket IDs, and infrastructure IPs to measure false positives.
