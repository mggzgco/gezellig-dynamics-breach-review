# Benchmark Evaluation Summary

- Dataset: pii-breach-benchmark-realworld-v3
- Dataset dir: `benchmark_sets/realworld_v3_150`
- Evaluated at: 2026-04-22T13:45:58.290929+00:00
- Finding precision: 61.3%
- Finding recall: 63.5%
- Files with missed findings: 95
- Files with false positives: 95
- AI-reviewed files: 0
- AI-escalated files: 0
- Expected human-review files caught by AI: 0 / 111

## By Type

| PII Type | Expected | Detected | TP | FP | FN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| ADDRESS | 98 | 95 | 16 | 79 | 82 | 16.8% | 16.3% |
| BANK_ACCOUNT | 14 | 11 | 11 | 0 | 3 | 100.0% | 78.6% |
| CREDIT_CARD | 6 | 6 | 6 | 0 | 0 | 100.0% | 100.0% |
| DOB | 121 | 109 | 88 | 21 | 33 | 80.7% | 72.7% |
| DRIVERS_LICENSE | 13 | 18 | 8 | 10 | 5 | 44.4% | 61.5% |
| EIN | 7 | 6 | 4 | 2 | 3 | 66.7% | 57.1% |
| EMAIL | 37 | 39 | 20 | 19 | 17 | 51.3% | 54.1% |
| FULL_NAME | 141 | 193 | 118 | 75 | 23 | 61.1% | 83.7% |
| IBAN | 7 | 3 | 3 | 0 | 4 | 100.0% | 42.9% |
| ICD10 | 14 | 7 | 7 | 0 | 7 | 100.0% | 50.0% |
| MEDICARE | 13 | 3 | 3 | 0 | 10 | 100.0% | 23.1% |
| MRN | 45 | 26 | 20 | 6 | 25 | 76.9% | 44.4% |
| NDC | 7 | 4 | 4 | 0 | 3 | 100.0% | 57.1% |
| PASSPORT | 7 | 7 | 4 | 3 | 3 | 57.1% | 57.1% |
| PHONE | 80 | 102 | 72 | 30 | 8 | 70.6% | 90.0% |
| SSN | 31 | 35 | 23 | 12 | 8 | 65.7% | 74.2% |

## End-to-End Report Scoring

- Report file/type precision: 99.3%
- Report file/type recall: 78.1%
- Report owner-aware precision: 86.1%
- Report owner-aware recall: 69.1%
- Review-escalation precision: 0.0%
- Review-escalation recall: 0.0%
- Files with QA follow-up matches: 0

## Error Hotspots

- Missed findings present in: email_028.eml, email_029.eml, email_030.eml, email_031.eml, email_032.eml, email_034.eml, email_035.eml, email_036.eml, email_037.eml, email_038.eml, email_039.eml, email_040.eml, email_041.eml, email_042.eml, email_043.eml, email_044.eml, email_046.eml, email_047.eml, email_048.eml, email_049.eml ...
- False positives present in: email_028.eml, email_029.eml, email_030.eml, email_031.eml, email_032.eml, email_034.eml, email_036.eml, email_037.eml, email_038.eml, email_040.eml, email_041.eml, email_043.eml, email_044.eml, email_046.eml, email_047.eml, email_048.eml, email_049.eml, email_050.eml, email_052.eml, email_053.eml ...
