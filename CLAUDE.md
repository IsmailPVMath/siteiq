# PVMath / SiteIQ — Project Memory

## Owner
- **Name:** Mohammed Ismail Pasha
- **Role:** Solar Engineer / Product Owner at Ideematec GmbH, Regensburg, Germany
- **Email:** ismailpasha747@gmail.com
- **Company being built:** PVMath (solo founder, side project alongside Ideematec job)
- **Domains owned:** pvmath.com, pvmath.de, pvmath.eu

---

## Platform Overview
**Product:** SiteIQ by PVMath — Solar Site Intelligence Platform  
**Tagline:** "From site to system."  
**Focus:** Ground-mount solar ONLY — Fixed Tilt and Single-Axis Tracker, Standard and Agri-PV (dual use). No rooftop, carport, floating, or BIPV.  
**Target users:** Solar EPCs, project developers, engineering firms worldwide  
**Monetization:** Freemium — Free (5 analyses/month **per module**), Professional **€149/month** (75 pooled analyses/month across SiteIQ + TopoIQ + YieldIQ), Developer **€499/month** (300 pooled/month, team pool), Enterprise custom. Stripe not wired yet — manual billing via `contact@pvmath.com` (see `docs/PVMath_Manual_Billing_Runbook.md`).

---

## Live Assets
| Asset | URL / target |
|---|---|
| **Production app** (SiteIQ + TopoIQ) | https://siteiq.pvmath.com · https://topoiq.pvmath.com |
| **Production Railway project** | `exemplary-balance` — deploys **`main`** only |
| **Staging Railway project** | `cozy-enjoyment` — deploys **`staging`** branch |
| GitHub repo | https://github.com/IsmailPVMath/siteiq |
| Website (GitHub Pages) | https://pvmath.com → `index.html` on **`main`** |
| Local dev folder | ~/Desktop/solarscout/ |

**Production is frozen by default.** Only push to `main` when explicitly promoting a tested staging release. Day-to-day TopoIQ / app fixes go to **`staging`** first.

**Railway branch wiring** (Settings → Service → Source → Branch):
| Railway project | Branch | Role |
|---|---|---|
| `exemplary-balance` | `main` | Production — siteiq.pvmath.com / topoiq.pvmath.com |
| `cozy-enjoyment` | `staging` | Pre-production testing |

Copy production env vars (Supabase, Brevo, etc.) into staging; use the same Supabase project or a dedicated staging DB if you prefer isolation later.

**Hosting note:** the app moved from Streamlit Community Cloud to **Railway** (Streamlit Cloud doesn't support a true custom top-level domain — only a `*.streamlit.app` subdomain rename — which is why Railway is used now). Domain registrar is **Namecheap**; DNS records for `pvmath.com`:
| Type | Host | Value |
|---|---|---|
| A | @ | 185.199.111.153 (+ the other 3 GitHub Pages IPs — website) |
| CNAME | siteiq | `<railway-generated>.up.railway.app` |
| CNAME | topoiq | `<railway-generated>.up.railway.app` (different generated host, same underlying deployment) |
| CNAME | www | ismailpvmath.github.io |
| TXT | _railway-verify.siteiq / _railway-verify.topoiq | Railway domain-verification tokens |

These `siteiq`/`topoiq` CNAMEs are true reverse-proxy records (Railway terminates the connection directly) — no redirect, no stripped query strings.

---

## Platform Modules (Roadmap)
| # | Name | Status | Description |
|---|---|---|---|
| 1 | **SiteIQ** | ✅ Live | Rapid site screening — solar, terrain, flood, regulatory, capacity, PDF |
| 2 | **TopoIQ** | ✅ Live | Terrain/slope analysis, CAD export (DXF/LandXML), PDF |
| 3 | **YieldIQ** | ✅ Live | Pre-layout yield estimation, PVGIS-based, PDF |
| 4 | **RevenueIQ** | 🔜 Coming Soon | EEG / feed-in tariff revenue calculator, Agri-PV bonus |
| 5 | **LayoutIQ** | 🔜 Admin-only | Auto layout + BOM generation — not public yet |
| 6 | **ProcureIQ** | 📋 Planned | Supplier lead time tracking, trade risk alerts |
| 7 | **FieldIQ** | 📋 Planned | BIM-based QA, post-install verification, after-sales |

---

## SiteIQ — Technical Stack
- **Framework:** Streamlit (Python)
- **Maps:** streamlit-folium + folium (interactive click-to-pin map)
- **Geocoding:** Nominatim/OSM — User-Agent: `"SiteIQ/1.0 (pvmath.com; contact@pvmath.com)"`
- **Solar data:** EU PVGIS API (JRC)
- **Terrain data:** OpenTopoData — eudem25m for Europe (34–72°N, −25–45°E), srtm30m globally
- **PDF:** ReportLab — use Paragraph objects for all table cells (plain strings don't wrap)
- **Deployment:** Railway — **production** (`exemplary-balance`) tracks `main`; **staging** (`cozy-enjoyment`) tracks `staging`. Custom domains on production only.
- **Auth/DB:** Supabase (email/password auth, `user_projects` + `usage_tracking` tables, REST API via `pvmath_auth.py` — no supabase-py SDK)
- **Email (OTP/notifications):** Brevo HTTP API (`BREVO_API_KEY` Railway env var), SMTP fallback for local/Streamlit dev

---

## SiteIQ — Key Files
| File | Location |
|---|---|
| Main app | `~/Desktop/solarscout/app.py` |
| Project Setup | `~/Desktop/solarscout/pages/project.py` |
| Auth / plans / usage | `~/Desktop/solarscout/pvmath_auth.py` |
| Geocoding | `~/Desktop/solarscout/pvmath_geocode.py` |
| Dependencies | `~/Desktop/solarscout/requirements.txt` |
| Website | `~/Desktop/solarscout/index.html` (deploy to GitHub Pages root) |
| Billing runbook | `~/Desktop/solarscout/docs/PVMath_Manual_Billing_Runbook.md` |
| Project context (short) | `~/Desktop/solarscout/PVMath_Project_Context.md` |

### requirements.txt
```
streamlit
requests
pandas
reportlab
pillow
folium
streamlit-folium
```

---

## SiteIQ — Feature Logic

### Project Types
- **Land Use:** Standard | Agri-PV (Dual Use)
- **Mounting:** Fixed Tilt | Single-Axis Tracker

### Capacity Density (MW/ha)
| | Fixed Tilt | Tracker |
|---|---|---|
| Standard | 0.40 | 0.35 |
| Agri-PV | 0.20 | 0.18 |

### Slope Limits
- **Fixed Tilt:** ≤5% Excellent / ≤10% Acceptable / ≤15% Challenging / >15% Critical
- **Tracker:** ≤3% Excellent / ≤6% Acceptable / ≤10% Challenging / >10% Critical

### Terrain API — dataset switching
```python
in_europe = 34 <= lat <= 72 and -25 <= lon <= 45
dataset = "eudem25m" if in_europe else "srtm30m"
```

### Country-aware regulatory guidance
`assess_eeg(lat, lon, land_use, project_country)` — uses `project_country` text string first (priority), lat/lon bounding box as fallback. Covers 14+ countries including DE, AT, CH, IT, ES, FR, PL, NL, US, IN, AU.

### `get_next_steps()` — country-aware PDF next steps
5 steps per country; step 5 wording changes for Agri-PV vs Standard.

### `parse_google_maps_url()` — handles:
1. Plain coordinate paste: `"17.14, 78.48"` (Google Maps right-click format)
2. Google Maps URL patterns: `@lat,lon`, `q=lat,lon`, `ll=lat,lon`, `place/.../@lat,lon`

### Map search / Project Setup pin
```python
# pages/project.py — search sets pin + st.rerun(); map click uses _set_proj_pin() + st.rerun()
st.session_state["proj_pin_lat"] / ["proj_pin_lon"] / ["proj_pin_label"]
reverse_geocode(lat, lon)  # status bar + saved as location_label on Save Project
```
- **Quick Mode:** single-click pin — SiteIQ + YieldIQ only
- **Full Mode:** draw polygon — enables TopoIQ; map in `@st.fragment` to avoid full-page dim while drawing

### Auth forms
- Register + login wrapped in `st.form` — Enter submits
- Multi-word given/family names allowed (`normalize_name_part()`)
- JS in `render_auth_page()` skips password visibility button in tab order

### Usage limits (`pvmath_auth.py`)
- Free: 5 per module · Professional: 75 pooled/month · Developer: 300 pooled/month (team)

### Map search (SiteIQ legacy)
```python
st.session_state["last_map_search"]  # tracks last search to avoid re-run loop
st.rerun()  # force map to redraw after geocoding
```

### PDF — important rules
- **No emojis** in ReportLab — renders as black squares. Use colored `Paragraph` objects.
- Use `lp()` helper for all table cells (ensures text wrapping).
- Footer text: `"Generated by SiteIQ — Solar Site Intelligence Platform by PVMath | For professional use only. Data sources: PVGIS (JRC), OpenTopoData, OpenStreetMap."`

---

## Website (pvmath.com)
- **File:** `index.html` — single-page, light theme, green accent
- **Theme:** Light grey (#f5f7f5) background, white cards, dark green (#1d9e52) accent
- **Sections:** Nav → Hero → About → Products (5 modules) → How It Works → Pricing → Contact form → Footer
- **Contact form:** Formspree — replace `YOUR_FORM_ID` with real ID from formspree.io
- **Hosting:** GitHub Pages from `IsmailPVMath/siteiq` repo root
- **Custom domain:** pvmath.com → CNAME `www → ismailpvmath.github.io` + A records to GitHub IPs

### GitHub Pages A records
```
185.199.108.153
185.199.109.153
185.199.110.153
185.199.111.153
```

---

## App Access Control
- Implemented: Supabase email/password auth (`pvmath_auth.py`, `render_auth_page()`), gates the whole app — no anonymous access.
- Admin allowlist is hardcoded in `app.py` (`_ADMIN = {"ismailpasha747@gmail.com"}`) — controls visibility of the in-progress LayoutIQ page.
- Session persistence across hard refresh works via a `?s=<refresh_token>` URL param, exchanged for a fresh Supabase session on load. Streamlit's own multipage navigation can strip this param from the visible URL on page transitions — `app.py` re-asserts it from `st.session_state["pvm_refresh_token"]` as the last step of every script run to compensate.

---

## Git Workflow

### Day-to-day (staging first)
```bash
cd ~/Desktop/solarscout
git checkout staging
git pull origin staging
# … fix TopoIQ / app issues …
git add -A && git commit -m "your message"
git push origin staging
# → Railway staging (cozy-enjoyment) auto-deploys
# Test on staging *.up.railway.app URL before promoting
```

### Promote to production (only when staging is verified)
```bash
git checkout main
git pull origin main
git merge staging   # or cherry-pick specific commits
git push origin main
# → Railway production (exemplary-balance) auto-deploys siteiq / topoiq
```

### Website (pvmath.com)
GitHub Pages still builds from **`main`** only. Marketing copy changes can go with a production promote, or directly to `main` if app-agnostic.

### One-time note (Mar 2026)
Remote `staging` was ~60 commits behind `main`. Before the next fix, run **`sync staging`** (merge `main` → `staging`) so staging matches current production baseline.

---

## Key Bugs Fixed (history)
- `"Optimal Tilt: True°"` — PVGIS returns `{"value": 35, "optimal": true}`, was reading `.get("optimal")` (boolean). Fix: `.get("value")`.
- Verdict showed "Agri-PV" for Standard projects — `overall_verdict()` had hardcoded text. Fix: pass `land_use` and `mount_type` dynamically.
- `NameError` on download — UI renamed `site_name` → `project_name` but download button still used old variable.
- PDF emojis as black squares — ReportLab can't render Unicode emoji. Fix: use colored `Paragraph` objects.
- PDF table text overflow — plain strings don't wrap. Fix: wrap every cell in `Paragraph`.
- Indian/non-DACH projects showing German authorities — `assess_eeg()` only used lat/lon. Fix: added `project_country` text priority.
- Terrain API failing for India — eudem25m is Europe-only. Fix: global dataset switch logic.
- Map search not moving map — `st.rerun()` added after updating `session_state["map_center"]`.
- Geocoding blocked by Nominatim — old User-Agent `"SolarScout/1.0"`. Fix: updated to `"SiteIQ/1.0 (pvmath.com; contact@pvmath.com)"`.
- Google Maps coordinate paste failing — only handled URLs. Fix: added plain coord regex `r'^(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)'`.
- Agricultural zoning shown for Standard projects — `get_next_steps()` was not conditional. Fix: added `agri` flag check.
- Every refresh logged the user out — fix: `pvm_refresh_token` in session + `?s=` re-asserted last line of `app.py`.
- Auth: multi-word names rejected / Enter didn't login / Tab hit password eye — fix: `st.form` + JS tab order (Jun 2026).
- Project Setup: double-click for pin, coords-only status bar, Quick vs Full unclear — fix: rerun on pin change, `reverse_geocode` in status bar, copy updates (Jun 2026).

---

## User Preferences
- No dark theme — use light theme for all UI/websites
- Concise responses, no verbose explanations
- Professional solar engineering terminology (not "Freifläche" — use "Standard Ground Mount" or "Agri-PV")
- App must work globally, not just DACH/Germany
