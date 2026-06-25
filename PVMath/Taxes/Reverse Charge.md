# Reverse Charge (EU B2B) — PVMath

When you sell SaaS to a **business customer in another EU country** (not Germany).

**Confirm every invoice with Steuerberater.**

---

## When it applies

- You have a valid **DE USt-IdNr**
- Customer provides valid **EU USt-IdNr** (VIES-valid)
- Customer is a **business** (B2B), not consumer
- Service = electronic / SaaS (B2B rules)

→ German VAT (19%) is **not** charged on the invoice. Customer self-assesses VAT in their country.

---

## Invoice wording (examples)

**DE:**  
*“Steuerfreie innergemeinschaftliche Lieferung bzw. Leistung. Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge).”*

**EN:**  
*“Reverse charge — VAT to be accounted for by the recipient pursuant to Article 196 EU VAT Directive.”*

Show:

- Your DE USt-IdNr
- Customer’s USt-IdNr
- Net amount only (no German 19% line)

---

## PVMath typical customers

| Region | Likely treatment |
|--------|------------------|
| DE EPC | 19% USt (regular) or §19 if Kleinunternehmer |
| ES / IT / FR / NL developer | Reverse charge if B2B + valid IDs |
| UK post-Brexit | UK VAT rules — not EU reverse charge |
| US / IN / AU | Usually outside EU VAT — net invoice |

---

## Stripe

- Set customer tax ID in Stripe Customer object
- Enable Stripe Tax or manual tax behavior per Steuerberater
- Payment Link may need “collect tax ID” for EU B2B

---

## Record keeping

- VIES validation proof (date + result)
- Customer USt-IdNr on invoice PDF
- Copy in `Finance/` or accounting tool

---

## Common mistakes

- Reverse charge to consumer (B2C) — wrong; use OSS or local VAT rules
- Invalid customer VAT ID — you may become liable for VAT
- Missing your DE USt-IdNr on invoice

See also: `OSS.md` (B2C digital services in EU)
