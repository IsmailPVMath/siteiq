# USt-IdNr (VAT ID) — PVMath

German **Umsatzsteuer-Identifikationsnummer** (format `DE123456789`) — not the same as Steuernummer.

---

## Do you need one?

| Situation | USt-IdNr |
|-----------|----------|
| Kleinunternehmer §19 only, DE customers | Often **not** required initially |
| Invoicing **EU B2B** with reverse charge | **Yes** — you and customer both need valid IDs |
| Stripe B2B EU | Recommended |
| Domestic DE B2B only | Steuernummer may suffice; Steuerberater decides |

---

## How to get it

1. Register Gewerbe + submit **Fragebogen zur steuerlichen Erfassung**
2. Finanzamt assigns **Steuernummer** first (days to ~2 weeks)
3. Apply for USt-IdNr via Finanzamt or ELSTER (often same questionnaire)
4. Issued by **Bundeszentralamt für Steuern** — can take **1–3 weeks**

---

## Verify EU customer VAT ID

Before reverse-charge invoice:

- EU VIES check: https://ec.europa.eu/taxation_customs/vies/
- Save screenshot / date of validation on invoice file

---

## Where to display

- Impressum (optional but standard for B2B)
- All invoices to EU business customers
- Stripe business profile

---

## PVMath placeholders to fill

```
Steuernummer: [Finanzamt Regensburg — when received]
USt-IdNr.: DE[…]
```

Update: `impressum.html`, `Invoice Templates.docx`, Stripe Dashboard.

---

## If not yet issued at Intersolar

- Invoice DE customers per Steuerberater (§19 note or 19% USt)
- For EU B2B: wait for USt-IdNr **or** use proforma and activate after ID issued
- Do not invent a VAT ID

---

## UG later

New USt-IdNr for the UG entity — close/update sole prop IDs with Steuerberater.
