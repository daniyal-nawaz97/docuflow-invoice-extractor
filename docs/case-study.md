# Case study: 19 supplier documents to Excel in under 30 seconds

> Built on a realistic test set of fictitious documents. When you finish your first pilot, copy this page and replace the numbers with the client's measured results (template at the bottom).

## Problem
A distributor's accounts team receives supplier bills in every format: emailed PDFs, scanned copies and WhatsApp photos of paper invoices. Each one is typed into Excel by hand (invoice number, date, vendor, tax ID, every line item and the totals), at roughly 5 minutes per document. Mistakes (a wrong total, the same bill entered twice) are found weeks later, if at all.

## Solution
DocuFlow, a web app where staff drop in a whole month of bills at once. It reads each document (PDF text, offline OCR for scans and photos, optional AI for unusual layouts), extracts header fields and line items, and checks every value: totals re-added, duplicates detected, blurry photos flagged. A reviewer only looks at what's flagged, with the exact spot highlighted on the original, then downloads Excel in the team's own column layout.

## Result (measured with `scripts/evaluate.py`)

| | Before (manual) | With DocuFlow |
|---|---|---|
| Time for 19 documents | ~95 minutes of typing | **27 seconds** processing + a few minutes reviewing flagged files |
| Field accuracy (readable documents) | depends on the typist | **99.4%** of fields correct |
| Documents correct with zero edits | n/a | **17 of 19** |
| Invoice with wrong printed total | easily missed | **caught** (red flag, reason shown) |
| Same invoice received twice | easily missed | **caught** (duplicate warning) |
| Blurry phone photo | typed with guesses | **flagged** for a clearer copy |
| Cost per invoice | staff time | 0 in offline mode; Groq free tier for AI mode |

Test set: clean PDFs in 5 layouts, a 2-page invoice with 32 line items, an Urdu-English bill, 3 phone photos, a scanned PDF, a deliberately blurry photo, an invoice with a wrong total and a duplicate.

## Screenshot
![Review screen catching a totals mismatch](screenshots/review.png)

## Link
Live demo: *(your deployed URL)*, then click **Try with sample invoices**.

---

### Template for a real client case study
- **Client:** (type of business, city; name only with permission)
- **Problem:** what they did manually, how many documents per month, how long it took
- **Solution:** (2-3 lines) what you set up: fields, template, team access
- **Result:** documents processed in the pilot · field accuracy on their documents · minutes per batch vs manual · errors caught
- **Quote:** one sentence from the client
- **Screenshot:** their Excel output (blur sensitive numbers)
