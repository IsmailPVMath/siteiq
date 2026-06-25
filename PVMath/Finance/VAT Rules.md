# VAT Rules (PVMath)

**Confirm with Steuerberater.** Summary for SaaS subscriptions from Germany.

---

## Current pricing (gross positioning)

| Plan | Price | Notes |
|------|-------|-------|
| Free | €0 | No invoice |
| Professional | €149/month | B2B SaaS |
| Developer | €499/month | B2B SaaS, team seats |
| Enterprise | Custom | Contract + invoice |

Website note: *“VAT (19%) added for EU customers”* — exact treatment depends on customer location and your VAT status.

---

## Path A — Kleinunternehmer (§19 UStG)

- No VAT charged on invoices
- Invoice must state exemption (e.g. *“Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.”*)
- No input VAT deduction on business expenses
- Threshold: €25,000 prior-year revenue and €100,000 current-year (2024+ rules — verify current limits with Steuerberater)
- **Good for:** very early revenue, Intersolar pilots, minimal admin

---

## Path B — Regular VAT (19% USt)

- Charge 19% German VAT on **domestic B2B and B2C** customers (unless exempt)
- Deduct Vorsteuer on eligible business expenses
- File **Umsatzsteuer-Voranmeldung** (monthly or quarterly)
- **Good for:** B2B customers who expect VAT invoices, reclaiming hosting/Stripe/software VAT

---

## EU B2B customers (other member states)

If customer provides valid **USt-IdNr** and you have **your DE USt-IdNr**:

- Often **reverse charge** (§13b) — invoice net, customer self-accounts VAT
- Invoice text example: *“Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge)”*
- See `../Taxes/Reverse Charge.md`

---

## Non-EU customers (e.g. US, IN, AU)

- Generally **outside German VAT scope** for electronic services (place of supply rules)
- Invoice net; no German 19% — document customer address
- Confirm per country with Steuerberater for first invoices

---

## Stripe

- Stripe Tax can calculate VAT if enabled — or Steuerberater + manual invoice wording until automated
- Stripe fees are a business expense (with VAT on Stripe’s fee invoice if you’re regular VAT)

---

## Invoice must-haves (Germany)

- Your name, address, Steuernummer and/or USt-IdNr when issued
- Customer name, address
- Invoice date, unique number, service description, period
- Net / VAT / gross (or §19 note)
- Payment terms

Template: `Invoice Templates.docx` in this folder.

---

## When entity changes to UG

Re-issue invoices in UG name, new Steuernummer/USt-IdNr, update Stripe account (typically new entity account).
