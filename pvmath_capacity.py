"""Unified DC capacity screening — single source of truth for SiteIQ, TopoIQ, YieldIQ."""
from __future__ import annotations

GCR_REF = 0.30
GCR_SCREEN_LO = 0.30
GCR_SCREEN_HI = 0.42

_BASE_DENSITY = {
    ("Standard", "Fixed Tilt"): 0.40,
    ("Standard", "Single-Axis Tracker"): 0.35,
    ("Agri-PV", "Fixed Tilt"): 0.20,
    ("Agri-PV", "Single-Axis Tracker"): 0.18,
}
_BASE_DENSITY_2P = {
    ("Standard", "Fixed Tilt"): 0.74,
    ("Standard", "Single-Axis Tracker"): 0.65,
    ("Agri-PV", "Fixed Tilt"): 0.37,
    ("Agri-PV", "Single-Axis Tracker"): 0.33,
}
_SCREENING_GCR = {
    "Fixed Tilt": (GCR_SCREEN_LO, GCR_SCREEN_HI),
    "Single-Axis Tracker": (GCR_SCREEN_LO, GCR_SCREEN_HI),
}

_CONFIG_TO_MOUNT_PORTRAIT = {
    "1P Fixed": ("Fixed Tilt", "1P"),
    "2P Fixed": ("Fixed Tilt", "2P"),
    "1P Tracker": ("Single-Axis Tracker", "1P"),
    "2P Tracker": ("Single-Axis Tracker", "2P"),
}


def config_mwp_screen(
    area_ha: float,
    land_use: str,
    mount_type: str,
    gcr: float,
) -> float:
    """Installable DC capacity (MWp) from area and GCR — 1P portrait baseline."""
    if not area_ha or area_ha <= 0:
        return 0.0
    base = _BASE_DENSITY.get((land_use, mount_type), 0.35)
    return round(area_ha * base * (gcr / GCR_REF), 0)


def config_mwp_screen_2p(
    area_ha: float,
    land_use: str,
    mount_type: str,
    gcr: float,
) -> float:
    """Installable DC capacity (MWp) for 2P portrait — area × 2P density × GCR scale."""
    if not area_ha or area_ha <= 0:
        return 0.0
    base = _BASE_DENSITY_2P.get((land_use, mount_type), 0.65)
    return round(area_ha * base * (gcr / GCR_REF), 0)


def site_capacity_screen(
    area_ha: float,
    land_use: str = "Standard",
    mount_type: str = "Fixed Tilt",
) -> tuple[float, float, float, float]:
    """Return (mwp_lo, mwp_hi, dens_lo, dens_hi) for 1P portrait screening band."""
    gcr_lo, gcr_hi = _SCREENING_GCR.get(mount_type, (GCR_REF, GCR_REF))
    base = _BASE_DENSITY.get((land_use, mount_type), 0.35)
    mwp_lo = config_mwp_screen(area_ha, land_use, mount_type, gcr_lo)
    mwp_hi = config_mwp_screen(area_ha, land_use, mount_type, gcr_hi)
    dens_lo = round(base * (gcr_lo / GCR_REF), 2)
    dens_hi = round(base * (gcr_hi / GCR_REF), 2)
    return mwp_lo, mwp_hi, dens_lo, dens_hi


def site_capacity_screen_2p(
    area_ha: float,
    land_use: str = "Standard",
    mount_type: str = "Fixed Tilt",
) -> tuple[float, float, float, float]:
    """Return (mwp_lo, mwp_hi, dens_lo, dens_hi) for 2P portrait screening band."""
    gcr_lo, gcr_hi = _SCREENING_GCR.get(mount_type, (GCR_REF, GCR_REF))
    base = _BASE_DENSITY_2P.get((land_use, mount_type), 0.65)
    mwp_lo = config_mwp_screen_2p(area_ha, land_use, mount_type, gcr_lo)
    mwp_hi = config_mwp_screen_2p(area_ha, land_use, mount_type, gcr_hi)
    dens_lo = round(base * (gcr_lo / GCR_REF), 2)
    dens_hi = round(base * (gcr_hi / GCR_REF), 2)
    return mwp_lo, mwp_hi, dens_lo, dens_hi


def site_capacity_mwp(
    area_ha: float,
    land_use: str = "Standard",
    mount_type: str = "Fixed Tilt",
    gcr: float = GCR_REF,
) -> tuple[float, str]:
    """Indicative DC capacity (MWp) and density note for screening."""
    mwp = config_mwp_screen(area_ha, land_use, mount_type, gcr)
    density = _BASE_DENSITY.get((land_use, mount_type), 0.35) * (gcr / GCR_REF)
    note = (
        f"{density:.2f} MWp/ha · {land_use} · {mount_type} · 1P @ GCR {gcr:.2f} "
        f"(screening — not layout-optimised)"
    )
    return mwp, note


site_capacity_mw = site_capacity_mwp


def capacity_band(
    area_ha: float,
    land_use: str,
    mount_type: str,
    portrait: str = "1P",
) -> dict:
    """Return screening capacity band for one mount/portrait combination."""
    gcr_lo, gcr_hi = _SCREENING_GCR.get(mount_type, (GCR_REF, GCR_REF))
    if not area_ha or area_ha <= 0:
        return {
            "mwp_lo": 0.0,
            "mwp_hi": 0.0,
            "dens_lo": 0.0,
            "dens_hi": 0.0,
            "gcr_lo": gcr_lo,
            "gcr_hi": gcr_hi,
            "portrait": portrait,
            "mount_type": mount_type,
            "land_use": land_use,
            "area_ha": area_ha or 0.0,
        }
    if portrait == "2P":
        mwp_lo, mwp_hi, dens_lo, dens_hi = site_capacity_screen_2p(area_ha, land_use, mount_type)
    else:
        mwp_lo, mwp_hi, dens_lo, dens_hi = site_capacity_screen(area_ha, land_use, mount_type)
    return {
        "mwp_lo": mwp_lo,
        "mwp_hi": mwp_hi,
        "dens_lo": dens_lo,
        "dens_hi": dens_hi,
        "gcr_lo": gcr_lo,
        "gcr_hi": gcr_hi,
        "portrait": portrait,
        "mount_type": mount_type,
        "land_use": land_use,
        "area_ha": area_ha,
    }


def capacity_band_for_config(area_ha: float, land_use: str, config_name: str) -> dict:
    """Map YieldIQ config label to capacity_band."""
    mount_type, portrait = _CONFIG_TO_MOUNT_PORTRAIT.get(
        config_name, ("Fixed Tilt", "1P"),
    )
    return capacity_band(area_ha, land_use, mount_type, portrait)


def capacity_with_yield(band: dict, annual_yield_kwh_kwp: float | None) -> dict:
    """Extend band dict with mwh_lo / mwh_hi from specific yield."""
    out = dict(band)
    mwh_lo = mwh_hi = None
    if annual_yield_kwh_kwp and annual_yield_kwh_kwp > 0:
        mwh_lo = round(band["mwp_lo"] * annual_yield_kwh_kwp, 0)
        mwh_hi = round(band["mwp_hi"] * annual_yield_kwh_kwp, 0)
    out["mwh_lo"] = mwh_lo
    out["mwh_hi"] = mwh_hi
    return out


def format_mwp_range(mwp_lo: float, mwp_hi: float) -> str:
    if mwp_lo == mwp_hi:
        return f"~{mwp_lo:,.0f} MWp DC"
    return f"~{mwp_lo:,.0f}–{mwp_hi:,.0f} MWp DC"


def format_mwh_range(mwh_lo: float | None, mwh_hi: float | None) -> str | None:
    if mwh_lo is None:
        return None
    if mwh_lo == mwh_hi:
        return f"{mwh_lo:,.0f} MWh/yr"
    return f"{mwh_lo:,.0f}–{mwh_hi:,.0f} MWh/yr"


def format_density_range(
    dens_lo: float, dens_hi: float, gcr_lo: float, gcr_hi: float,
) -> str:
    if dens_lo == dens_hi:
        return f"{dens_lo:.2f} MWp DC/ha @ GCR {gcr_lo:.2f}"
    return f"{dens_lo:.2f}–{dens_hi:.2f} MWp DC/ha · GCR {gcr_lo:.2f}–{gcr_hi:.2f}"


def format_capacity_rating(band: dict) -> str:
    return format_density_range(
        band["dens_lo"], band["dens_hi"], band["gcr_lo"], band["gcr_hi"],
    )


def _mount_screen_label(mount_type: str) -> str:
    return "tracker" if mount_type == "Single-Axis Tracker" else "fixed tilt"


def capacity_basis_sentence(band: dict) -> str:
    portrait = band.get("portrait", "1P")
    mount = _mount_screen_label(band.get("mount_type", "Fixed Tilt"))
    return (
        f"Indicative DC capacity at GCR {band['gcr_lo']:.2f}–{band['gcr_hi']:.2f} "
        f"({portrait} {mount} screening): "
        f"{format_mwp_range(band['mwp_lo'], band['mwp_hi'])}"
    )


def capacity_footnote_global() -> str:
    return (
        "Capacity estimates use area × screening density (MWp/ha @ GCR 0.30) "
        f"scaled by GCR {GCR_SCREEN_LO:.2f}–{GCR_SCREEN_HI:.2f}. "
        "Values are indicative pre-layout screening bands, not layout-optimised DC."
    )


def capacity_all_configs_summary(area_ha: float, land_use: str) -> str:
    if not area_ha or area_ha <= 0:
        return ""
    parts = []
    for cfg in ("1P Fixed", "2P Fixed", "1P Tracker", "2P Tracker"):
        b = capacity_band_for_config(area_ha, land_use, cfg)
        parts.append(f"{cfg} {format_mwp_range(b['mwp_lo'], b['mwp_hi'])}")
    return (
        f"Indicative DC capacity at GCR {GCR_SCREEN_LO:.2f}–{GCR_SCREEN_HI:.2f}: "
        + " · ".join(parts)
    )


def screening_capacity(
    area_ha: float,
    land_use: str = "Standard",
    mount_type: str = "Fixed Tilt",
    annual_yield_kwh_kwp: float | None = None,
) -> dict:
    """SiteIQ screening band — 1P portrait at GCR 0.30–0.42."""
    band = capacity_band(area_ha, land_use, mount_type, portrait="1P")
    if annual_yield_kwh_kwp:
        return capacity_with_yield(band, annual_yield_kwh_kwp)
    return band


def capacity_range_mw(area_ha: float, land_use: str = "Standard") -> str:
    """Fixed-tilt and tracker DC screening bands — 1P portrait."""
    ft = capacity_band(area_ha, land_use, "Fixed Tilt")
    tr = capacity_band(area_ha, land_use, "Single-Axis Tracker")
    return (
        f"Fixed {format_mwp_range(ft['mwp_lo'], ft['mwp_hi'])} · "
        f"Tracker {format_mwp_range(tr['mwp_lo'], tr['mwp_hi'])} "
        f"(1P screening @ GCR {GCR_SCREEN_LO:.2f}–{GCR_SCREEN_HI:.2f})"
    )
