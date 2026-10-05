# Demo script (5 minutes live, or 2-3 minutes as video)

The recorded video `docs/demo.mp4` follows this script with on-screen captions. Re-record any time with `python -m scripts.record_demo` (run it against a fresh `data/` folder so the duplicate check doesn't flag earlier runs), then add your voice-over.

| # | Time | Screen | Say |
|---|---|---|---|
| 1 | 20s | Login page | "How long does your team spend typing invoices each month?" |
| 2 | 20s | Home, drag 10 mixed files | "PDFs, a scanned copy, phone photos, even an Urdu-English bill. Drop them all in at once." |
| 3 | 20s | Processing | "Each file is read, then every value is checked. You can leave the page; it notifies you." |
| 4 | 60s | Review: scanned invoice | "Green means confident, orange means please check. Click a value and it shows exactly where it came from. The customer name was hard to read, so I type it and press Enter. The next one opens by itself." |
| 5 | 30s | Review: wrong totals, then duplicate | "This supplier's total is 1,000 too high, caught before it reaches your books. And this bill came twice by email: flagged as a duplicate." |
| 6 | 30s | Summary, then Download Excel | "Three sheets: Invoices, Line Items, and Needs Review with reasons. Your own column names." |
| 7 | 30s | Numbers | "On our test set: 100% of fields correct on readable documents, about 2 seconds per document." *(use your latest measured numbers)* |
| 8 | 20s | Close | "Send me 20 of your own invoices and I'll process them free." |

## Before any live demo
- [ ] Demo login works (`Try with sample invoices`)
- [ ] Open the sample batch once so previews are cached
- [ ] Phone ready to show a photo upload
- [ ] `sample_output.xlsx` open in Excel in another window
- [ ] Latest numbers from `docs/results.md`
