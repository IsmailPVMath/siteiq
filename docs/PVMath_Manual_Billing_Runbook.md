# PVMath — Manual billing runbook (until Stripe + UG)

## Customer flow

1. User hits upgrade in app → `contact@pvmath.com` (already wired).
2. You reply with **Pilot Subscription Agreement** + **Proforma invoice** (docs folder).
3. Customer signs + pays by bank transfer.
4. You activate plan in Supabase (below).
5. Customer refreshes app — new limits apply immediately.

## Activate plan in Supabase

1. Supabase → Authentication → find user email → copy **User UID**.
2. SQL Editor:

```sql
-- Professional (75 analyses/month pooled across modules)
update profiles set plan = 'professional' where id = '<user-uuid>';

-- Developer (150/month pooled — team shares usage_key; owner uuid = team_id for members)
update profiles set plan = 'developer' where id = '<owner-uuid>';
-- teammates:
update profiles set plan = 'developer', team_id = '<owner-uuid>' where id = '<teammate-uuid>';
```

3. Ask customer to log out/in if plan badge does not update.

## How limits work (Professional & Developer)

- **Professional:** **75 total runs/month** across SiteIQ + TopoIQ + YieldIQ.
- **Developer:** **150 total runs/month** — **entire team shares one pool** (up to 5 seats).
- Example: 60 TopoIQ + 15 SiteIQ = 75 → Professional paywall until next month.
- Enforced in app via `is_over_limit()` — no manual tracking needed.
- Customer sees **X / limit** on **Overview** dashboard.

## Free tier (unchanged)

- 5 runs **per module** per month.

## Verify usage

```sql
select app, count, period from usage_tracking
where usage_key = '<user-uuid>' and period = to_char(now(), 'YYYY-MM');
```

Sum `count` across apps for pooled Professional total.

## Documents

- `PVMath_Pilot_Subscription_Agreement.docx`
- `PVMath_Proforma_Invoice_Template.docx`

Regenerate: `python3 scripts/generate_sales_docs.py`
