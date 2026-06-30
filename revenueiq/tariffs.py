"""Country / land-use tariff bands for screening-grade revenue estimates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class TariffBand:
    """Annual revenue per MWh (local currency units). Screening band, not PPA quote."""

    currency: str
    revenue_lo: float  # €/MWh or $/MWh
    revenue_hi: float
    label: str
    notes: str = ""


def _norm_country(country: str) -> str:
    c = (country or "").strip().lower()
    if any(x in c for x in ("germany", "deutschland", "de")):
        return "germany"
    if any(x in c for x in ("united states", "usa", "america", "us")):
        return "usa"
    if any(x in c for x in ("spain", "españa")):
        return "spain"
    if any(x in c for x in ("france", "fr")):
        return "france"
    if any(x in c for x in ("italy", "italia")):
        return "italy"
    if "india" in c:
        return "india"
    if any(x in c for x in ("united kingdom", "uk", "britain")):
        return "uk"
    if "australia" in c:
        return "australia"
    return "global"


# EUR/MWh feed-in or merchant screening bands (2025–2026 order of magnitude).
_TARIFFS: dict[tuple[str, str], TariffBand] = {
    ("germany", "Standard"): TariffBand(
        "EUR", 52, 78, "DE EEG / market reference",
        "Screening band — auction and direct-marketing vary by year.",
    ),
    ("germany", "Agri-PV"): TariffBand(
        "EUR", 58, 88, "DE Agri-PV premium band",
        "Includes Agri-PV bonus assumption vs standard EEG category.",
    ),
    ("spain", "Standard"): TariffBand("EUR", 45, 65, "ES merchant / auction"),
    ("spain", "Agri-PV"): TariffBand("EUR", 48, 70, "ES Agri-PV screening"),
    ("france", "Standard"): TariffBand("EUR", 50, 72, "FR CRE / PPA screening"),
    ("france", "Agri-PV"): TariffBand("EUR", 55, 78, "FR Agrivoltaïque"),
    ("italy", "Standard"): TariffBand("EUR", 48, 68, "IT merchant / GSE"),
    ("italy", "Agri-PV"): TariffBand("EUR", 52, 75, "IT Agri-PV screening"),
    ("uk", "Standard"): TariffBand("GBP", 42, 62, "UK CfD / merchant screening"),
    ("uk", "Agri-PV"): TariffBand("GBP", 45, 68, "UK Agri-PV screening"),
    ("india", "Standard"): TariffBand("INR", 2800, 4200, "IN DISCOM / merchant INR/MWh"),
    ("india", "Agri-PV"): TariffBand("INR", 3000, 4500, "IN Agri-PV screening"),
    ("australia", "Standard"): TariffBand("AUD", 55, 85, "AU PPA / merchant AUD/MWh"),
    ("australia", "Agri-PV"): TariffBand("AUD", 58, 90, "AU Agri-PV screening"),
    ("global", "Standard"): TariffBand("EUR", 40, 70, "Global merchant screening"),
    ("global", "Agri-PV"): TariffBand("EUR", 45, 75, "Global Agri-PV screening"),
}

# USD/MWh for US — converted to EUR in engine when reporting unified EUR view.
_US_TARIFFS: dict[str, TariffBand] = {
    "Standard": TariffBand("USD", 28, 48, "US PPA / merchant screening"),
    "Agri-PV": TariffBand("USD", 30, 52, "US Agrivoltaics screening"),
}

# Rough FX to EUR for unified reporting (screening constants — not live FX).
_FX_TO_EUR = {"EUR": 1.0, "USD": 0.92, "GBP": 1.17, "INR": 0.011, "AUD": 0.61}


def resolve_tariff(country: str, land_use: str) -> TariffBand:
    """Return screening tariff band for country + land use."""
    key_country = _norm_country(country)
    lu = land_use if land_use in ("Standard", "Agri-PV") else "Standard"
    if key_country == "usa":
        return _US_TARIFFS.get(lu, _US_TARIFFS["Standard"])
    return _TARIFFS.get((key_country, lu), _TARIFFS[("global", lu)])


def tariff_eur_mwh(band: TariffBand) -> Tuple[float, float]:
    """Convert tariff band to EUR/MWh for unified output."""
    fx = _FX_TO_EUR.get(band.currency, 1.0)
    return band.revenue_lo * fx, band.revenue_hi * fx
