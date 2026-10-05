# Measured results (2026-10-05)

Engine: **Offline reader (no AI)**. Test set: 19 fictitious sample documents in `sample_data/` (clean PDFs, a multi-page invoice, an Urdu-English bill, phone photos, a scanned PDF, a blurry photo, an invoice with wrong totals and a duplicate).

| Metric | Result |
|---|---|
| Field accuracy (all 19 documents) | **95.9%** |
| Field accuracy (excluding the deliberately blurry photo) | **100.0%** |
| Documents 100% correct with no edits | 18/19 |
| Line items fully correct | 18/19 documents |
| Average processing time | 1.91 s per document |
| Whole set | 36.4 s (vs about 95 min typing by hand at 5 min each) |
| Wrong totals caught | 1/1 |
| Blurry photo flagged for review | 1/1 |
| Duplicate detected | checked in the app on batch level (see summary screen) |
| Cost per invoice | 0 (offline) |

## Per-field accuracy

| Field | Accuracy |
|---|---|
| vendor | 100.0% |
| invoice_no | 94.7% |
| date | 94.7% |
| tax_id | 94.7% |
| customer | 94.7% |
| subtotal | 94.7% |
| tax | 94.7% |
| total | 94.7% |
| currency | 100.0% |

## Per document

| File | Type | Fields correct | Line items | Missed | Seconds |
|---|---|---|---|---|---|
| alnoor_INV-2041.pdf | pdf | 9/9 | 4/4 ✓ | - | 0.24 |
| alnoor_INV-2057.pdf | pdf | 9/9 | 6/6 ✓ | - | 0.08 |
| crescent_CP-26-0187.pdf | pdf | 9/9 | 5/5 ✓ | - | 0.07 |
| crescent_CP-26-0203.pdf | pdf | 9/9 | 3/3 ✓ | - | 0.07 |
| swift_courier_SC-88213.pdf | pdf | 9/9 | 3/3 ✓ | - | 0.06 |
| margalla_ME-5521.pdf | pdf | 9/9 | 5/5 ✓ | - | 0.07 |
| indus_office_IOS-1190.pdf | pdf | 9/9 | 5/5 ✓ | - | 0.09 |
| ravi_textiles_RT-3302.pdf | pdf | 9/9 | 4/4 ✓ | - | 0.07 |
| global_imports_GTI-7781.pdf | pdf | 9/9 | 3/3 ✓ | - | 0.06 |
| crescent_CP-26-0211_multipage.pdf | pdf | 9/9 | 32/32 ✓ | - | 0.17 |
| barkat_karyana_BK-0415_urdu.pdf | pdf | 9/9 | 5/5 ✓ | - | 0.08 |
| swift_courier_SC-88240.pdf | pdf | 9/9 | 4/4 ✓ | - | 0.07 |
| indus_office_IOS-1204_totals_wrong.pdf | pdf | 9/9 | 4/4 ✓ | - | 0.07 |
| photo_alnoor_INV-2063.jpg | photo | 9/9 | 4/4 ✓ | - | 10.96 |
| photo_swift_courier_SC-88257.jpg | photo | 9/9 | 3/3 ✓ | - | 3.93 |
| photo_ravi_textiles_RT-3318.jpg | photo | 9/9 | 3/3 ✓ | - | 8.65 |
| scan_margalla_ME-5544.pdf | scan | 9/9 | 3/3 ✓ | - | 9.67 |
| photo_blurry_margalla_ME-5560.jpg | photo | 2/9 | 0/3 ✗ | invoice_no, date, tax_id, customer, subtotal, tax, total | 1.84 |
| crescent_invoice_copy_from_email.pdf | pdf | 9/9 | 5/5 ✓ | - | 0.11 |

_Honest note: this is a small, synthetic test set. Before quoting numbers to a client, run the same script on 20-50 of their real documents (add them with correct answers to `ground_truth.json`)._
