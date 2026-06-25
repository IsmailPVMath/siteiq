"""Shared product facts — sourced from PVMath docs; no invented statistics."""

from __future__ import annotations

MODULES = {
    "siteiq": {
        "name": "SiteIQ",
        "tagline": "Know if a site is buildable within minutes.",
        "purpose": "Rapid ground-mount site screening at pin or boundary.",
        "inputs": "Project setup · land use · mounting type · area (ha) · coordinates/boundary",
        "outputs": "GHI, slope (indicative), flood flag, capacity band, suitability score, screening PDF",
        "users": "Developers, EPC pre-sales, independent engineers",
        "time": "≤ 4 minutes typical",
        "data": "PVGIS JRC · OpenTopoData (EU-DEM / SRTM) · OpenStreetMap",
    },
    "topoiq": {
        "name": "TopoIQ",
        "tagline": "Screen terrain before you order the topo survey.",
        "purpose": "Copernicus GLO-30 terrain screening inside project boundary.",
        "inputs": "Boundary from Project Setup (draw or KMZ/KML) · analysis grid (default 5 m)",
        "outputs": "Slope maps, cross-row grades, engineering verdicts, terrain PDF, LandXML, DXF",
        "users": "Civil/structural engineers, EPC design teams, layout engineers",
        "time": "~20–60 s depending on site size",
        "data": "Copernicus GLO-30 DEM (~30 m native, resampled to grid)",
    },
    "yieldiq": {
        "name": "YieldIQ",
        "tagline": "Compare tracker vs fixed yield before you open PVsyst.",
        "purpose": "Four-configuration yield comparison for early feasibility.",
        "inputs": "Location from Project Setup · DC capacity · GCR · system losses",
        "outputs": "Specific yield, PR, capacity factor, tracker gain, comparison PDF",
        "users": "Energy analysts, developers, EPC engineers",
        "time": "≤ 4 minutes typical",
        "data": "PVGIS JRC (screening-grade — not bankable)",
    },
}

DISCLAIMER = (
    "Early Access · screening-grade outputs only. Not bankable yield, not survey-grade "
    "terrain, not a substitute for LiDAR, PVsyst, or lender sign-off."
)

PRICING = (
    "Free: 5 runs per module/month (separate caps) · Professional: €149/mo, 75 pooled analyses · "
    "Developer: €499/mo, 300 pooled, 5 seats · Enterprise: custom"
)

ROADMAP = [
    ("Live", "SiteIQ · TopoIQ · YieldIQ"),
    ("Next", "RevenueIQ (EEG / tariff revenue) · LayoutIQ (auto layout + BOM)"),
    ("Future", "ProcureIQ · FieldIQ"),
]

PROBLEMS = [
    "Weeks lost on sites that fail on slope, flood, or grid reality",
    "Repeated manual GIS + PVGIS + spreadsheet work per iteration",
    "Terrain surprises discovered after layout and civil budget are fixed",
    "Inconsistent screening quality across project managers",
]

MANUAL_WORKFLOW = [
    "Desktop GIS + manual coordinate handling",
    "Separate PVGIS / spreadsheet yield checks",
    "Topo survey or LiDAR deferred until late stage",
    "PDF reports assembled by hand for each gate meeting",
]

PVMATH_WORKFLOW = [
    "One project setup — location, boundary, country",
    "SiteIQ → TopoIQ → YieldIQ share the same site context",
    "Screening PDFs and CAD starter kit in minutes",
    "Consistent methodology and disclaimers built in",
]

BENEFITS = [
    "Time: collapse weeks of ad-hoc screening into same-day iterations",
    "Cost: fewer dead-end sites advanced to expensive survey/design",
    "Quality: tracker-aware terrain metrics and cross-module consistency",
    "Risk: explicit Early Access disclaimers — honest screening, not false precision",
    "Scale: pooled team plans for high-volume pipelines (Developer tier)",
]

ARCHITECTURE = [
    ("User", "Browser — siteiq.pvmath.com"),
    ("App", "Streamlit on Railway · auth via Supabase"),
    ("Data", "PVGIS · Copernicus GLO-30 · OpenTopoData · OSM"),
    ("Storage", "Supabase — projects, usage, team invites"),
    ("Exports", "PDF (ReportLab) · LandXML · DXF · CSV"),
]

TOPO_DEMO_STEPS = [
    {
        "title": "Project Setup (Full Mode)",
        "bullets": [
            "Create project name + country",
            "Upload KMZ or draw boundary on map",
            "Confirm area (ha) — inherited by TopoIQ",
        ],
        "visual": "Screenshot: Project Setup boundary on map",
        "talk": "Emphasise one setup for all modules — no re-entry.",
    },
    {
        "title": "Confirm grid & land context",
        "bullets": [
            "Default 5 m analysis grid (layout-friendly)",
            "GLO-30 native ~30 m — honest resampling",
            "Select enabled parcels from KMZ layers",
        ],
        "visual": "Screenshot: TopoIQ boundary manager + layer toggles",
        "talk": "Explain screening grid vs survey-grade LiDAR.",
    },
    {
        "title": "Run terrain screening",
        "bullets": [
            "Slope heatmap + cross-row statistics",
            "Fixed tilt vs tracker engineering verdicts",
            "Review zones when cross-row grades exceed thresholds",
        ],
        "visual": "Screenshot: TopoIQ slope map + metrics panel",
        "talk": "Focus on tracker cross-row p95 — not just mean slope.",
    },
    {
        "title": "Export PDF + CAD starter kit",
        "bullets": [
            "Terrain PDF for client / internal gate",
            "LandXML TIN (UTM) for Civil 3D import",
            "DXF contours + parcel linework from boundary",
        ],
        "visual": "Screenshot: PDF cover + Civil 3D import (placeholder)",
        "talk": "Conceptual surface — not survey replacement.",
    },
]

TOPO_QA = [
    ("Is this LiDAR accuracy?", "No — Copernicus GLO-30 screening (~30 m native). Use for go/no-go and layout direction, then commission survey."),
    ("Why 5 m grid if DEM is 30 m?", "Finer grid for contours/CAD workflow; underlying detail limit unchanged — we state this on reports."),
    ("Will LandXML open in Civil 3D?", "Yes as UTM TIN starter surface — verify CRS and add survey control later."),
    ("Agri-PV / trackers?", "Ground-mount only — tracker cross-row metrics included; Agri-PV density handled in SiteIQ/YieldIQ."),
]

SALES_DEMO_STEPS = [
    {
        "title": "SiteIQ — first gate in minutes",
        "bullets": ["Pin or paste coordinates", "Land use + mounting + area", "Download screening PDF"],
        "visual": "Screenshot: SiteIQ suitability score + PDF",
    },
    {
        "title": "TopoIQ — when boundary exists",
        "bullets": ["Full Mode boundary/KMZ", "Terrain verdict + exports", "CAD starter kit"],
        "visual": "Screenshot: TopoIQ slope heatmap",
    },
    {
        "title": "YieldIQ — configuration compare",
        "bullets": ["Four configs: SAT/Fixed × 1P/2P", "Tracker gain vs fixed", "Feasibility PDF"],
        "visual": "Screenshot: YieldIQ bar comparison",
    },
]
