# OSS (One Stop Shop) — PVMath

**EU VAT OSS** = optional scheme for **B2C** digital services to consumers in other EU countries.

PVMath is **primarily B2B** (EPCs, developers) — OSS may **not** be needed at launch.

**Confirm with Steuerberater before registering for OSS.**

---

## B2B vs B2C for PVMath

| Customer | Typical VAT approach |
|----------|---------------------|
| GmbH / S.L. / S.r.l. with VAT ID | Reverse charge (`Reverse Charge.md`) |
| Individual signing up with work email | Often still B2B if invoiced to company |
| Individual consumer (personal use) | B2C — local EU VAT rate of **customer’s country** unless OSS |

---

## When OSS matters

If you sell subscriptions **directly to consumers** in EU countries (no business VAT ID):

- Without OSS: you might need to register for VAT in each country (bad)
- With **Union OSS** (registered in Germany): report all EU B2C VAT in one DE return

Threshold: **€10,000** cross-border B2C digital services per year (EU-wide) — above this, charge destination-country VAT.

---

## Early-stage PVMath (Intersolar / year 1)

Likely scenarios:

1. **Mostly B2B invoices to companies** → reverse charge or DE VAT — **OSS not urgent**
2. **Free tier only for individuals** → no payment, no OSS
3. **Stripe self-serve to unknown EU buyers** → discuss Stripe Tax + OSS with Steuerberater **before** enabling EU consumer checkout

---

## Practical recommendation

| Phase | Action |
|-------|--------|
| Launch | B2B proforma / Stripe with company name + VAT ID collection |
| Steuerberater call | Ask: “Any B2C EU revenue expected in 2026?” |
| If B2C EU > €10k | Register Union OSS in Germany |
| Stripe Tax | Can calculate destination VAT if OSS registered |

---

## Not the same as

- **Reverse charge** — B2B only
- **IOSS** — goods, not SaaS
- **German regular USt** — domestic 19%

---

## Links (official)

- BZSt OSS: https://www.bzst.de/EN/Home/home_node.html
- EU explanatory: search “VAT OSS digital services B2C”

Document OSS registration date here when/if registered:

```
OSS registration date: [—]
OSS ID: [—]
```
