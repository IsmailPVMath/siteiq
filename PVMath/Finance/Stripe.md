# Stripe (PVMath)

Internal runbook for payments. **Status:** not live until account + links configured.

---

## Account setup (Einzelunternehmen)

| Field | Value |
|-------|-------|
| Type | Individual / Einzelunternehmen |
| Legal name | Mohammed Ismail Pasha |
| Trading name | PVMath |
| Website | https://pvmath.com |
| Product | B2B SaaS — solar site screening |
| Payout IBAN | As approved by Steuerberater |

---

## Products to create

| Product | Price | Plan key in Supabase |
|---------|-------|----------------------|
| PVMath Professional | €149/month recurring | `professional` |
| PVMath Developer | €499/month recurring | `developer` |

Enable: card, SEPA Direct Debit (DE), Customer Portal (cancel, invoices).

---

## Where links go in codebase

| Location | Constant / element |
|----------|---------------------|
| App sidebar | `Manage membership` → `pvmath_team.py` / `UPGRADE_CONTACT` |
| App constant | `STRIPE_LINK` in `pvmath_auth.py` (Customer Portal URL) |
| Website | `index.html` — Professional **Subscribe** button |
| Legacy | `usage_tracker.py` — keep in sync or remove duplicate |

**Target:** replace `UPGRADE_CONTACT` mailto with Payment Links for self-serve Professional.

---

## Activation flow

### Phase 1 — Manual (current)

1. Customer pays via Stripe Payment Link or bank transfer
2. You receive Stripe email or see payment in Dashboard
3. Activate in Supabase:

```sql
update profiles set plan = 'professional' where id = '<user-uuid>';
-- Developer owner:
update profiles set plan = 'developer' where id = '<owner-uuid>';
```

See `../docs/PVMath_Manual_Billing_Runbook.md`

### Phase 2 — Webhook (planned)

- Supabase Edge Function: `stripe-webhook`
- Events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`
- Metadata: `user_id` = Supabase auth UUID from Checkout
- Updates `profiles.plan` automatically

Env vars: `STRIPE_WEBHOOK_SECRET`, `STRIPE_SECRET_KEY`, `SUPABASE_SERVICE_ROLE_KEY`

---

## Developer team seats

After webhook sets owner to `developer`, owner invites via **Manage membership → Team** (see `supabase_migration_team_invites.sql`).

---

## Intersolar / pilot fallback

- Proforma + bank transfer still valid (`Invoice Templates.docx`, pilot agreement)
- Stripe Payment Link on phone for instant subscribe

---

## UG migration (future)

New Stripe account under PVMath UG → migrate customers → update all links in app + website.
