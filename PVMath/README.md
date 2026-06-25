# PVMath — Founder Handbook

Internal operating manual for Mohammed Ismail Pasha (Einzelunternehmen, trading as **PVMath**).

**Not legal or tax advice.** Confirm all filings, VAT treatment, and invoicing with your Steuerberater.

**→ [STATUS.md](STATUS.md)** — current priorities, what’s live, what’s next (update after each milestone).

---

## Folder map

| Folder | Purpose |
|--------|---------|
| [Company Formation](Company%20Formation/) | Gewerbe, Finanzamt, IHK — store official PDFs here |
| [Finance](Finance/) | VAT, Stripe, invoices, pricing |
| [Legal](Legal/) | Terms, privacy, impressum — mirrors public site |
| [Accounting](Accounting/) | Expenses, monthly bookkeeping rhythm |
| [Taxes](Taxes/) | USt-IdNr, reverse charge, OSS (EU B2C) |

---

## Canonical public legal pages (deployed)

These HTML files in the repo root are what customers see — update them first, then sync summaries here:

| Page | File | Live URL |
|------|------|----------|
| Impressum | `../impressum.html` | https://pvmath.com/impressum.html |
| Privacy | `../privacy.html` | https://pvmath.com/privacy.html |
| Terms | `../terms.html` | https://pvmath.com/terms.html |

---

## Related docs (repo)

| Doc | Location |
|-----|----------|
| Einzelunternehmen launch plan | `../docs/PVMath_Einzelunternehmen_Launch_Plan.docx` |
| Manual billing runbook | `../docs/PVMath_Manual_Billing_Runbook.md` |
| UG formation (future) | `../docs/PVMath_UG_Formation_Guide.docx` |
| Pilot agreement | `../docs/PVMath_Pilot_Subscription_Agreement.docx` |

---

## Regenerate handbook markdown

```bash
python3 scripts/generate_founder_handbook.py
```

---

## Sensitive files — do not commit

Official Gewerbe / Finanzamt PDFs may contain personal tax IDs. They live in `Company Formation/` locally; `*.pdf` in that folder is gitignored.
