"""Country-aware next steps for SiteIQ PDF sections (ported from pages/siteiq.py)."""

from __future__ import annotations


def _us_grid_operator(lat, lon):
    if 25.8 <= lat <= 36.5 and -106.6 <= lon <= -93.5:
        return "ERCOT"
    if 36.0 <= lat <= 49.0 and -125.0 <= lon <= -66.0:
        if lon >= -104.0:
            return "PJM / MISO / SPP"
        return "WECC / CAISO"
    return "Regional ISO/RTO"


def get_next_steps(project_country, land_use="Standard", lat=None, lon=None, area_ha=None):
    c = (project_country or "").lower().strip()
    agri = land_use == "Agri-PV"
    # German ground-mount above ~1 MWp (≈2.5 ha) must win a BNetzA competitive
    # tender (EEG-Ausschreibung); the fixed feed-in tariff path is for small arrays.
    utility_scale = area_ha is not None and area_ha >= 2.5

    if any(x in c for x in ["germany", "deutschland", "de"]):
        if utility_scale:
            tariff_step = (
                "EEG 2023: ground-mount >1 MWp must bid in the BNetzA Ausschreibung "
                "(competitive tender, Solar-Freifläche) — register the project in the "
                "Marktstammdatenregister and track tender rounds at bundesnetzagentur.de"
            )
        else:
            tariff_step = "EEG 2023 feed-in tariff: register via Bundesnetzagentur (Marktstammdatenregister)"
        steps = [
            "Verify land classification (Nutzungsart) with local Katasteramt",
            "Grid connection: contact local DSO (e.g. Bayernwerk, E.ON, Netze BW)",
            "Planning permission: consult local Bauamt / Gemeindeverwaltung",
            tariff_step,
            "Flood risk: www.hochwasserportal.de — verify HQ100 flood zone",
        ]
        if agri:
            steps.append("Agronomic study required for DIN SPEC 91434 Agri-PV compliance")
    elif any(x in c for x in ["usa", "united states", "america"]):
        iso = _us_grid_operator(lat, lon) if lat is not None and lon is not None else "your regional ISO/RTO"
        steps = [
            f"Interconnection: submit LGIA / queue application with your transmission owner in {iso}",
            "Environmental: wetlands (USACE), threatened species (USFWS), and cultural-resource screening",
            "Planning: county zoning permit + conditional use permit (CUP)",
            "Incentives: ITC (Investment Tax Credit) 30% + IRA bonus credits",
            "Land use: verify zoning classification with county assessor" if not agri else
            "Land use: Agri-PV — verify agricultural zoning and dual-use approval with county",
        ]
    else:
        steps = [
            f"Grid connection: contact the national grid operator / local DSO in {project_country or 'the project country'}",
            f"Planning permission: local municipality / regional planning authority",
            "Environmental impact assessment: check national threshold requirements for solar",
            "Feed-in tariff / incentive scheme: contact national energy regulatory authority",
            "Land use: verify zoning and land classification with local authority",
        ]
        if agri:
            steps.append("Agri-PV dual-use: verify national / regional agricultural dual-use regulations")

    return [f"{i + 1}. {s}" for i, s in enumerate(steps)]
