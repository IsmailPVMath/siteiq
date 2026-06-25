# Monthly Checklist (PVMath)

Repeat on the **1st business day** of each month (15 min + Steuerberater handoff if applicable).

---

## Revenue & customers

- [ ] Export Stripe Dashboard → payments, MRR, failed charges
- [ ] List new paying customers vs Supabase `profiles.plan` (manual until webhook)
- [ ] Chase failed SEPA/card retries via Stripe
- [ ] Log Enterprise / pilot invoices sent and paid

---

## Usage & product

- [ ] Spot-check `usage_tracking` for abnormal spikes (support / abuse)
- [ ] Note any paywall support emails → FAQ or copy fix
- [ ] Check Railway + Supabase dashboards (uptime, errors)

---

## Expenses

- [ ] Download Stripe fee invoice
- [ ] Railway, Supabase, Brevo, Namecheap receipts
- [ ] Forward to Steuerberater / upload to accounting tool
- [ ] Tag new expenses per `Expense Categories.md`

---

## VAT (if regular USt, not Kleinunternehmer)

- [ ] Steuerberater files USt-Voranmeldung (or you via ELSTER if DIY)
- [ ] EU B2B invoices: reverse charge applied correctly?
- [ ] Archive issued invoices (number sequence unbroken)

---

## Legal & compliance

- [ ] Impressum / terms still match operator details?
- [ ] Any new subprocessors → privacy policy update?

---

## Founder metrics (optional)

| Metric | Where |
|--------|-------|
| Paying accounts | Supabase `profiles` where plan ≠ free |
| MRR | Stripe |
| Free → paid | Manual / Stripe later |
| Analyses run | Sum `usage_tracking` for period |

---

## Quarterly (every 3 months)

- [ ] Review pricing vs costs (hosting per active user)
- [ ] Backup Supabase schema + note migration files run
- [ ] LinkedIn / marketing calendar (`marketing/` folder)
- [ ] Steuerberater sync — USt, EÜR preview, tax reserve

---

## Year-end

- [ ] All invoices numbered and stored
- [ ] Steuerberater: Jahresabschluss / EÜR / income tax prep
- [ ] Renew domains (pvmath.com, .de, .eu)
- [ ] Review UG timing with Steuerberater if revenue justifies
