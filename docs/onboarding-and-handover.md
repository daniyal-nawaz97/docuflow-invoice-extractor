# Client onboarding and handover guide

## Onboarding (after they say yes)
1. **Collect 20-30 real documents**, covering every supplier and format they receive (PDF, scan, photo).
2. **Agree fields and layout.** Get a copy of the Excel they fill today; create a matching template in **Templates** (column names, order, date format).
3. **Label the pilot set.** Add the correct answers to `sample_data/ground_truth.json` (same shape as the samples) so accuracy is measured, not guessed.
4. **Run the pilot batch** and review mistakes together on the review screen.
5. **Tune.** Turn on AI reading (Groq key) if layouts are unusual; re-run `python -m scripts.evaluate`.
6. **Go live**: set branding, add their team, set the privacy retention they want.
7. **Agree support:** response time for issues, and who to contact.

## Handover checklist
- [ ] Live URL and admin login shared securely
- [ ] Their logo, colour and company name set
- [ ] Templates match their Excel
- [ ] Team members added with the right roles
- [ ] Retention period agreed and set
- [ ] 5-minute walkthrough video recorded for their staff (upload → review → export)
- [ ] Measured pilot results shared (field accuracy, time per batch)
- [ ] Support period and contact agreed in writing

## Quick guide for their staff (paste into an email)
1. Open the link and sign in.
2. **Home:** drag in invoices (or a ZIP, or take a photo on your phone), choose the document type and template, press **Start processing**.
3. Wait for the progress bar, or leave the page; you'll get a notification.
4. **Review flagged files:** orange = please check, red = problem. Click a value to see where it came from, fix it, press **Enter** to approve.
5. **Download Excel.** The *Needs Review* sheet lists anything still flagged.
6. **History:** find any past batch by vendor, invoice number or file name.
