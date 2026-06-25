# PVMath — Current Status

**Last updated:** 21 June 2026  
**Read this first** when starting a new Cursor session. Then `CLAUDE.md` for technical detail.

---

## One-line summary

Live B2B solar screening SaaS (SiteIQ, TopoIQ, YieldIQ); **Einzelunternehmen registration in progress**; **Stripe not live**; **team invites deployed**; **Intersolar marketing** next.

---

## Business & legal

| Item | Status |
|------|--------|
| Legal form | **Einzelunternehmen** (Mohammed Ismail Pasha, trading as PVMath) — registering |
| Steuerberater | Approved sole prop + personal bank account for payments |
| UG (haftungsbeschränkt) | **Deferred** — new Stripe account when UG formed later |
| Gewerbe Regensburg | **TODO** — target Sat evening before Intersolar week |
| Steuernummer / USt-IdNr | **TODO** — after Finanzamt (USt-IdNr often 1–3 weeks) |
| Ideematec Nebentätigkeit | Confirm / disclose if contract requires |
| IHK | Automatic after Gewerbe — pay when billed |

**Docs:** `docs/PVMath_Einzelunternehmen_Launch_Plan.docx` · `PVMath/` Founder Handbook

---

## Product (what’s live)

| Module | URL | Status |
|--------|-----|--------|
| SiteIQ | siteiq.pvmath.com | ✅ Production |
| TopoIQ | topoiq.pvmath.com | ✅ Production |
| YieldIQ | siteiq.pvmath.com (nav) | ✅ Production |
| LayoutIQ | Admin only | 🔒 `_ADMIN` emails in `app.py` |
| Website | pvmath.com | ✅ GitHub Pages from `main` |

**Deploy:** Railway production `exemplary-balance` ← branch **`main`**. Staging `cozy-enjoyment` ← **`staging`**.

**Latest production commit (team invites):** `f4503ed` — *Add Developer team invites under Manage membership.*

---

## Pricing & billing

| Plan | Price | Limit |
|------|-------|-------|
| Free | €0 | 5 / module / month |
| Professional | €149/mo | 75 pooled / month (SiteIQ + TopoIQ + YieldIQ) |
| Developer | €499/mo | 300 pooled / month, **5 team seats** |
| Enterprise | Custom | Contact |

| Billing piece | Status |
|---------------|--------|
| Stripe account | **Not opened yet** |
| `STRIPE_LINK` in `pvmath_auth.py` | Placeholder `YOUR_LINK_HERE` |
| Website **Subscribe** button | Still → `#contact` (Formspree) — **fix with Stripe Payment Links** |
| Manual activation | Supabase SQL — `docs/PVMath_Manual_Billing_Runbook.md` |
| Stripe webhooks → auto `profiles.plan` | **Not built** — planned after Payment Links |
| Developer team invites UI | ✅ **Live** — sidebar **Manage membership → Team** |
| Supabase `team_invites` migration | ✅ **Applied** by owner in SQL Editor |

---

## App UX (recent)

- **Settings** — name + email only  
- **Manage membership** — plan, limits, team invites, upgrade link  
- **Team owner** — invite by email, copy link `?team_invite=TOKEN`, remove members  
- **Team member** — accept invite banner, leave team  
- **Seat math** — 5 seats = owner + up to 4 teammates (`team_occupied_seats()`)

---

## Immediate next steps (priority order)

### Before / during Intersolar

1. [ ] **Gewerbe** anmelden (Regensburg) + Fragebogen steuerliche Erfassung  
2. [ ] **Stripe** — Einzelunternehmer account + Payment Links (Pro €149, Dev €499)  
3. [ ] Wire **index.html** Subscribe → Stripe; **Manage membership** → same links  
4. [ ] Update **impressum.html** with Steuernummer / USt-IdNr when received  
5. [ ] QR + demo site ready for fair — pitch in launch plan docx  
6. [ ] (Optional) Supabase Edge Function **stripe-webhook** for auto plan activation  

### After first paying customers

- [ ] Webhook fully live (no manual Supabase for each payment)  
- [ ] Commit **Founder Handbook** + launch plan if still local-only  
- [ ] Evaluate UG timing with Steuerberater  

---

## Key files (quick index)

| Topic | Path |
|-------|------|
| **This file** | `PVMath/STATUS.md` |
| AI project memory | `CLAUDE.md` |
| Founder Handbook | `PVMath/README.md` |
| Team invites SQL | `supabase_migration_team_invites.sql` |
| Team UI | `pvmath_team.py`, `app.py` (Manage membership) |
| Auth / plans | `pvmath_auth.py` |
| Manual billing | `docs/PVMath_Manual_Billing_Runbook.md` |
| Launch checklist | `docs/PVMath_Einzelunternehmen_Launch_Plan.docx` |
| Folium draw guard | `pvmath_folium_draw.py` — never regress polygon drawing |

---

## Not committed / local only (check git)

- `PVMath/` Founder Handbook (may need commit)  
- `docs/PVMath_Einzelunternehmen_Launch_Plan.docx`  
- `scripts/generate_einzelunternehmen_launch_plan.py`  
- `PVMath/Company Formation/*.pdf` — **gitignored**, store Gewerbe PDFs locally  

---

## How to resume in Cursor

```
Continue PVMath. Read PVMath/STATUS.md and CLAUDE.md first.
```

Or reopen this chat thread.

---

## Update rule

When something material changes (Gewerbe done, Stripe live, first customer, UG formed), **edit this file first** — one paragraph + checkbox updates. Takes 2 minutes; saves re-explaining everything.
