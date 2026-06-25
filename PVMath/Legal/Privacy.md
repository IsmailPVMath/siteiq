# Privacy Policy (internal reference)

**Canonical public version:** [`../../privacy.html`](../../privacy.html) → https://pvmath.com/privacy.html

Last updated on site: June 2025 — **refresh date when Gewerbe/entity details change.**

---

## Data controller

Mohammed Ismail Pasha — PVMath  
Straubinger Strasse 1, 93055 Regensburg, Germany  
contact@pvmath.com · +49 15 901 482 999

---

## What we process

| Category | Examples | Purpose |
|----------|----------|---------|
| Account | Email, password hash, name | Auth (Supabase) |
| Usage | Module runs per month | Plan limits |
| Projects | Site name, coordinates, boundaries/KMZ | Core product |
| Billing | Stripe customer ID (when live) | Subscriptions |
| Contact form | Name, email, message | Formspree → contact@pvmath.com |

---

## Processors / sub-processors

| Service | Role | Location |
|---------|------|----------|
| Supabase | Auth, DB | EU / configurable |
| Railway | App hosting | EU/US — check DPA |
| Stripe | Payments | EU entity when DE account |
| Brevo | OTP / email | EU |
| Formspree | Contact form | US — mention in policy |
| PVGIS, OpenTopoData, Nominatim | Open data APIs | No PII sent beyond coordinates |

---

## AVV / DPA

Enterprise customers may request AVV (Auftragsverarbeitungsvertrag). Template: ask Steuerberater/lawyer when first EPC requires it.

---

## User rights (GDPR)

Access, rectification, deletion, portability, objection — contact@pvmath.com within 30 days.

Account deletion: manual today (Supabase admin); document process for support.

---

## Internal rules

- Do not export customer project data for marketing without consent
- Do not commit secrets or user emails to git
- Admin access: ismailpasha747@gmail.com only (`_ADMIN` in app.py)

---

## When to update public policy

- New subprocessors (e.g. analytics)
- Stripe live + billing data
- Entity / address change
- New data types (LayoutIQ uploads, etc.)
