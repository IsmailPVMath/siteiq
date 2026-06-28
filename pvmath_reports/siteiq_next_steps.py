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


def get_next_steps(project_country, land_use="Standard", lat=None, lon=None):
    c = (project_country or "").lower().strip()
    agri = land_use == "Agri-PV"

    if any(x in c for x in ["germany", "deutschland", "de"]):
        steps = [
            "Verify land classification (Nutzungsart) with local Katasteramt",
            "Grid connection: contact local DSO (e.g. Bayernwerk, E.ON, Netze BW)",
            "Planning permission: consult local Bauamt / Gemeindeverwaltung",
            "EEG 2023 feed-in tariff: register via Bundesnetzagentur (Marktstammdatenregister)",
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
