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
**Monetization:** Freemium — Free (10 screenings/month per module), Pro €49/month, Enterprise custom

---

## Live Assets
| Asset | URL |
|---|---|
| Live app (SiteIQ) | https://siteiq.pvmath.com (Railway, custom domain) |
| Live app (TopoIQ) | https://topoiq.pvmath.com (same Railway deployment, second custom domain) |
| GitHub repo | https://github.com/IsmailPVMath/siteiq (branch: main) |
| Website | https://pvmath.com → GitHub Pages → index.html |
| Local dev folder | ~/Desktop/solarscout/ |

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
| 2 | **RevenueIQ** | 🔜 Coming Soon | EEG / feed-in tariff revenue calculator, Agri-PV bonus |
| 3 | **LayoutIQ** | 🔜 Coming Soon | Auto layout + BOM generation, delta BOM for revisions |
| 4 | **ProcureIQ** | 📋 Planned | Supplier lead time tracking, trade risk alerts |
| 5 | **FieldIQ** | 📋 Planned | BIM-based QA, post-install verification, after-sales |

---

## SiteIQ — Technical Stack
- **Framework:** Streamlit (Python)
- **Maps:** streamlit-folium + folium (interactive click-to-pin map)
- **Geocoding:** Nominatim/OSM — User-Agent: `"SiteIQ/1.0 (pvmath.com; contact@pvmath.com)"`
- **Solar data:** EU PVGIS API (JRC)
- **Terrain data:** OpenTopoData — eudem25m for Europe (34–72°N, −25–45°E), srtm30m globally
- **PDF:** ReportLab — use Paragraph objects for all table cells (plain strings don't wrap)
- **Deployment:** Railway (GitHub integration, auto-deploy on push to main), exposed via two custom domains (siteiq.pvmath.com, topoiq.pvmath.com) — see Hosting note above
- **Auth/DB:** Supabase (email/password auth, `user_projects` + `usage_tracking` tables, REST API via `pvmath_auth.py` — no supabase-py SDK)
- **Email (OTP/notifications):** Brevo HTTP API (`BREVO_API_KEY` Railway env var), SMTP fallback for local/Streamlit dev

---

## SiteIQ — Key Files
| File | Location |
|---|---|
| Main app | `~/Desktop/solarscout/app.py` |
| Dependencies | `~/Desktop/solarscout/requirements.txt` |
| Website | `~/Desktop/solarscout/index.html` (deploy to GitHub Pages root) |

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

### Map search
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
```bash
cd ~/Desktop/solarscout
git add -A
git commit -m "your message"
git push origin main
# Railway auto-deploys on push (GitHub integration)
```

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
- Every refresh logged the user out, on every browser, every time — not a DNS/redirect issue (confirmed via DNS check, real CNAME to Railway). Root cause: Streamlit's own multipage `st.navigation()` strips query params from the visible URL on page transitions, and the Supabase refresh token only ever lived in that URL param. Fix: refresh token now also kept in `st.session_state["pvm_refresh_token"]`, re-asserted into `st.query_params["s"]` as the last line of `app.py` on every run.

---

## User Preferences
- No dark theme — use light theme for all UI/websites
- Concise responses, no verbose explanations
- Professional solar engineering terminology (not "Freifläche" — use "Standard Ground Mount" or "Agri-PV")
- App must work globally, not just DACH/Germany
