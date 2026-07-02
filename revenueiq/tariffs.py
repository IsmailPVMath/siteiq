"""Country-aware tariff bands — GOVT_AUCTION, PPA, or CUSTOM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from revenueiq.currency import country_iso, currency_code, eur_fx_rate, local_to_eur, to_local


@dataclass(frozen=True)
class TariffResult:
    tariff_mode: str  # GOVT_AUCTION | PPA | CUSTOM
    tariff_lo_eur_mwh: float
    tariff_hi_eur_mwh: float
    tariff_lo_local_mwh: float
    tariff_hi_local_mwh: float
    label: str
    notes: str = ""
    itc_applicable: bool = False


def _norm_land_use(land_use: str) -> str:
    return land_use if land_use in ("Standard", "Agri-PV") else "Standard"


# (mode, lo_local, hi_local, label, notes) — local currency per MWh unless EUR country.
_TARIFF_TABLE: dict[str, tuple[str, float, float, str, str]] = {
    "DE": ("GOVT_AUCTION", 46, 52, "DE EEG Ausschreibung (BNetzA)", "Indicative 2024–2025 tender rounds."),
    "AT": ("GOVT_AUCTION", 50, 70, "AT Ökostrom tender (OeMAG)", ""),
    "FR": ("GOVT_AUCTION", 45, 65, "FR CRE appel d'offres", ""),
    "IT": ("GOVT_AUCTION", 50, 75, "IT GSE Aste (FER2)", ""),
    "PL": ("GOVT_AUCTION", 180 / 4.25, 250 / 4.25, "PL URE auction", "PLN 180–250/MWh converted at static FX."),
    "CH": ("GOVT_AUCTION", 73, 104, "CH KEV / direct marketing", "CHF 70–100/MWh EUR equiv."),
    "GB": ("GOVT_AUCTION", 46, 70, "UK CfD Allocation Round", "£40–60/MWh EUR equiv."),
    "IN": ("PPA", 2200 / 90 * 1000 / 1000, 3500 / 90 * 1000 / 1000, "IN SECI / DISCOM PPA", "₹2.20–3.50/kWh screening band."),
    "AU": ("PPA", 44, 80, "AU LGC + wholesale", "Combined LGC + pool EUR equiv."),
    "ES": ("PPA", 38, 58, "ES corporate / utility PPA", "No active FIT — bilateral PPA market."),
    "US": ("PPA", 28 / 1.08 * 1.08, 50 / 1.08 * 1.08, "US utility PPA", "ITC applies to CAPEX, not revenue."),
}

_PPA_DEFAULTS: dict[str, tuple[float, float]] = {
    "ES": (38, 58),
    "IT": (48, 68),
    "FR": (42, 62),
    "DE": (48, 70),
    "IN": (24, 39),  # EUR/MWh equiv for PPA path
    "US": (26, 46),  # EUR/MWh equiv ($28–50/MWh)
    "AU": (44, 80),
}

_DEFAULT_PPA_EUR = (35, 55)


def resolve_tariff(
    country: str,
    land_use: str,
    *,
    tariff_override_local_mwh: Optional[float] = None,
) -> TariffResult:
    """Return tariff band with mode, EUR and local currency rates."""
    iso = country_iso(country)
    lu = _norm_land_use(land_use)
    code = currency_code(country)
    fx = eur_fx_rate(country)

    if tariff_override_local_mwh is not None and tariff_override_local_mwh > 0:
        local = float(tariff_override_local_mwh)
        eur = local_to_eur(local, country)
        return TariffResult(
            tariff_mode="CUSTOM",
            tariff_lo_eur_mwh=round(eur, 1),
            tariff_hi_eur_mwh=round(eur, 1),
            tariff_lo_local_mwh=round(local, 2),
            tariff_hi_local_mwh=round(local, 2),
            label="Custom rate (user-defined)",
            notes="User override in local currency per MWh.",
        )

    if iso == "US":
        lo_usd, hi_usd = 28.0, 50.0
        lo_eur = local_to_eur(lo_usd, country)
        hi_eur = local_to_eur(hi_usd, country)
        return TariffResult(
            tariff_mode="PPA",
            tariff_lo_eur_mwh=round(lo_eur, 1),
            tariff_hi_eur_mwh=round(hi_eur, 1),
            tariff_lo_local_mwh=lo_usd,
            tariff_hi_local_mwh=hi_usd,
            label="US utility PPA",
            notes="ITC is a CAPEX reduction — not modeled as €/MWh revenue.",
            itc_applicable=True,
        )

    if iso == "ES":
        lo_eur, hi_eur = 38.0, 58.0
        return TariffResult(
            tariff_mode="PPA",
            tariff_lo_eur_mwh=lo_eur,
            tariff_hi_eur_mwh=hi_eur,
            tariff_lo_local_mwh=round(to_local(lo_eur, country), 1),
            tariff_hi_local_mwh=round(to_local(hi_eur, country), 1),
            label="ES corporate / utility PPA",
            notes="Spain closed RECORE FIT — new projects use bilateral PPA.",
        )

    row = _TARIFF_TABLE.get(iso)
    if row:
        mode, lo_e, hi_e, label, notes = row
        if iso == "IN":
            lo_inr = 2200.0
            hi_inr = 3500.0
            if lu == "Agri-PV":
                lo_inr, hi_inr = 2400.0, 3800.0
            return TariffResult(
                tariff_mode=mode,
                tariff_lo_eur_mwh=round(local_to_eur(lo_inr, country), 1),
                tariff_hi_eur_mwh=round(local_to_eur(hi_inr, country), 1),
                tariff_lo_local_mwh=lo_inr,
                tariff_hi_local_mwh=hi_inr,
                label=label,
                notes=notes,
            )
        if iso == "PL":
            lo_pln = 180.0
            hi_pln = 250.0
            return TariffResult(
                tariff_mode=mode,
                tariff_lo_eur_mwh=round(local_to_eur(lo_pln, country), 1),
                tariff_hi_eur_mwh=round(local_to_eur(hi_pln, country), 1),
                tariff_lo_local_mwh=lo_pln,
                tariff_hi_local_mwh=hi_pln,
                label=label,
                notes=notes,
            )
        if iso == "GB":
            lo_gbp = 40.0
            hi_gbp = 60.0
            return TariffResult(
                tariff_mode=mode,
                tariff_lo_eur_mwh=round(local_to_eur(lo_gbp, country), 1),
                tariff_hi_eur_mwh=round(local_to_eur(hi_gbp, country), 1),
                tariff_lo_local_mwh=lo_gbp,
                tariff_hi_local_mwh=hi_gbp,
                label=label,
                notes=notes,
            )
        if iso == "CH":
            lo_chf = 70.0
            hi_chf = 100.0
            return TariffResult(
                tariff_mode=mode,
                tariff_lo_eur_mwh=round(local_to_eur(lo_chf, country), 1),
                tariff_hi_eur_mwh=round(local_to_eur(hi_chf, country), 1),
                tariff_lo_local_mwh=lo_chf,
                tariff_hi_local_mwh=hi_chf,
                label=label,
                notes=notes,
            )
        if iso == "AU":
            lo_aud = 55.0
            hi_aud = 90.0
            return TariffResult(
                tariff_mode=mode,
                tariff_lo_eur_mwh=round(local_to_eur(lo_aud, country), 1),
                tariff_hi_eur_mwh=round(local_to_eur(hi_aud, country), 1),
                tariff_lo_local_mwh=lo_aud,
                tariff_hi_local_mwh=hi_aud,
                label=label,
                notes=notes,
            )
        # EUR-denominated auction markets
        lo_eur, hi_eur = lo_e, hi_e
        if lu == "Agri-PV" and iso == "DE":
            lo_eur, hi_eur = 52.0, 78.0
        return TariffResult(
            tariff_mode=mode,
            tariff_lo_eur_mwh=lo_eur,
            tariff_hi_eur_mwh=hi_eur,
            tariff_lo_local_mwh=round(to_local(lo_eur, country), 1),
            tariff_hi_local_mwh=round(to_local(hi_eur, country), 1),
            label=label,
            notes=notes,
        )

    # Unknown country — conservative PPA band
    lo_eur, hi_eur = _DEFAULT_PPA_EUR
    return TariffResult(
        tariff_mode="PPA",
        tariff_lo_eur_mwh=lo_eur,
        tariff_hi_eur_mwh=hi_eur,
        tariff_lo_local_mwh=round(to_local(lo_eur, country), 1),
        tariff_hi_local_mwh=round(to_local(hi_eur, country), 1),
        label="Global PPA screening",
        notes="Conservative merchant / PPA benchmark for unmapped markets.",
    )


# Legacy helpers for backward compatibility
@dataclass(frozen=True)
class TariffBand:
    currency: str
    revenue_lo: float
    revenue_hi: float
    label: str
    notes: str = ""


def tariff_eur_mwh(band: TariffBand) -> tuple[float, float]:
    from revenueiq.currency import local_to_eur as _l2e

    if band.currency == "EUR":
        return band.revenue_lo, band.revenue_hi
    return _l2e(band.revenue_lo, band.currency), _l2e(band.revenue_hi, band.currency)
