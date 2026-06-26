# PVMath — Manual billing runbook (until Stripe + UG)

## Customer flow

1. User hits upgrade in app → `contact@pvmath.com` (already wired).
2. You reply with **Pilot Subscription Agreement** + **Proforma invoice** (docs folder).
3. Customer signs + pays by bank transfer.
4. You activate plan in Supabase (below), **or** use **Manage membership → Team** if the account is on Developer (after `supabase_migration_team_invites.sql` is applied).
5. Customer refreshes app — new limits apply immediately.

## Activate plan in Supabase

1. Supabase → Authentication → find user email → copy **User UID**.
2. SQL Editor:

```sql
-- Professional (50 project analyses/month)
update profiles set plan = 'professional' where id = '<user-uuid>';

-- Developer (250/month pooled — team shares usage_key; owner uuid = team_id for members)
update profiles set plan = 'developer' where id = '<owner-uuid>';
-- teammates:
update profiles set plan = 'developer', team_id = '<owner-uuid>' where id = '<teammate-uuid>';
```

3. Ask customer to log out/in if plan badge does not update.

## How limits work

- **One project analysis** = SiteIQ screening run for a project. TopoIQ, LayoutIQ, and YieldIQ on the same project in the same month do **not** use extra credits.
- **Free:** 10 project analyses/month.
- **Professional:** 50 project analyses/month.
- **Developer:** 250 project analyses/month — **entire team shares one pool** (up to 5 seats).
- **Enterprise:** unlimited.
- Limits reset on the 1st of each calendar month (UTC). Unused analyses do not roll over.
- Enforced via `usage_tracking` app=`platform` — no manual tracking needed.
- Customer sees **X / limit** in the app header and account sidebar.

## Verify usage

```sql
select app, count, period from usage_tracking
where usage_key = '<user-uuid>' and period = to_char(now(), 'YYYY-MM');
```

Look for `app = 'platform'` row — that is the billed project analysis count.

## Documents

- `PVMath_Pilot_Subscription_Agreement.docx`
- `PVMath_Proforma_Invoice_Template.docx`

Regenerate: `python3 scripts/generate_sales_docs.py`
