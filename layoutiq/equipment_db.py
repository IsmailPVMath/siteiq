"""Curated module/inverter database + optional PVFree API lookup."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

_log = logging.getLogger(__name__)

PVFREE_BASE = "https://pvfree.azurewebsites.net/api/v1"

CURATED_MODULES: Dict[str, Dict[str, Any]] = {
    "Jinko Tiger Neo N-type 620Wp": {
        "Wp": 620,
        "Voc": 38.8,
        "Vmp": 32.4,
        "Isc": 17.91,
        "Imp": 16.98,
        "beta_Voc": -0.0026,
        "beta_Vmp": -0.0028,
        "alpha_Isc": 0.0004,
        "T_NOCT": 43,
        "cells_in_series": 78,
        "dimensions_mm": [2278, 1134, 30],
        "bifacial": True,
    },
    "LONGi Hi-MO 6 660Wp": {
        "Wp": 660,
        "Voc": 40.2,
        "Vmp": 33.9,
        "Isc": 18.32,
        "Imp": 17.48,
        "beta_Voc": -0.0025,
        "beta_Vmp": -0.0026,
        "alpha_Isc": 0.00045,
        "T_NOCT": 43,
        "cells_in_series": 78,
        "dimensions_mm": [2384, 1134, 30],
        "bifacial": True,
    },
    "Trina Vertex S+ 695Wp": {
        "Wp": 695,
        "Voc": 40.9,
        "Vmp": 34.4,
        "Isc": 19.07,
        "Imp": 18.17,
        "beta_Voc": -0.0024,
        "beta_Vmp": -0.0025,
        "alpha_Isc": 0.00048,
        "T_NOCT": 42,
        "cells_in_series": 78,
        "dimensions_mm": [2384, 1134, 35],
        "bifacial": True,
    },
    "Canadian Solar HiKu7 665Wp": {
        "Wp": 665,
        "Voc": 40.5,
        "Vmp": 34.1,
        "Isc": 18.64,
        "Imp": 17.72,
        "beta_Voc": -0.0025,
        "beta_Vmp": -0.0027,
        "alpha_Isc": 0.00044,
        "T_NOCT": 43,
        "cells_in_series": 78,
        "dimensions_mm": [2384, 1134, 30],
        "bifacial": True,
    },
    "JA Solar JAM72D42 580Wp": {
        "Wp": 580,
        "Voc": 41.8,
        "Vmp": 34.9,
        "Isc": 15.59,
        "Imp": 14.83,
        "beta_Voc": -0.0026,
        "beta_Vmp": -0.0027,
        "alpha_Isc": 0.00040,
        "T_NOCT": 43,
        "cells_in_series": 72,
        "dimensions_mm": [2278, 1134, 30],
        "bifacial": True,
    },
}

CURATED_INVERTERS: Dict[str, Dict[str, Any]] = {
    "Sungrow SG3125HV-30 (3.125 MW, 1500V)": {
        "type": "central",
        "Paco_kW": 3125,
        "Vdcmax": 1500,
        "Vdco": 1100,
        "Mppt_low": 880,
        "Mppt_high": 1380,
        "Idcmax": 3200,
        "n_mppt": 12,
        "strings_per_mppt": None,
    },
    "Huawei SUN2000-196KTL (196 kW, 1500V)": {
        "type": "string",
        "Paco_kW": 196,
        "Vdcmax": 1500,
        "Vdco": 1080,
        "Mppt_low": 200,
        "Mppt_high": 1500,
        "Idcmax": 26,
        "n_mppt": 10,
        "strings_per_mppt": 2,
    },
    "SMA STP 110-60 (110 kW, 1500V)": {
        "type": "string",
        "Paco_kW": 110,
        "Vdcmax": 1500,
        "Vdco": 1000,
        "Mppt_low": 200,
        "Mppt_high": 1500,
        "Idcmax": 18,
        "n_mppt": 6,
        "strings_per_mppt": 2,
    },
    "Fronius Tauro ECO 100 kW (1000V)": {
        "type": "string",
        "Paco_kW": 100,
        "Vdcmax": 1000,
        "Vdco": 800,
        "Mppt_low": 200,
        "Mppt_high": 800,
        "Idcmax": 22,
        "n_mppt": 4,
        "strings_per_mppt": 3,
    },
    "GoodWe GW3600D-NS (3.6 MW, 1500V)": {
        "type": "central",
        "Paco_kW": 3600,
        "Vdcmax": 1500,
        "Vdco": 1100,
        "Mppt_low": 500,
        "Mppt_high": 1380,
        "Idcmax": 3800,
        "n_mppt": 1,
        "strings_per_mppt": None,
    },
}


def list_modules() -> List[str]:
    return list(CURATED_MODULES.keys())


def list_inverters() -> List[str]:
    return list(CURATED_INVERTERS.keys())


def curated_module_layout_specs() -> List[Dict[str, Any]]:
    """Module names with layout dimensions (m) for React LayoutIQ sidebar."""
    rows: List[Dict[str, Any]] = []
    for name, spec in CURATED_MODULES.items():
        dims = spec.get("dimensions_mm") or [2278, 1134, 30]
        rows.append(
            {
                "name": name,
                "Wp": int(spec["Wp"]),
                "module_h_m": round(float(dims[0]) / 1000.0, 4),
                "module_w_m": round(float(dims[1]) / 1000.0, 4),
                "bifacial": bool(spec.get("bifacial", True)),
            }
        )
    return rows


def get_module(name: str) -> Dict[str, Any]:
    if name not in CURATED_MODULES:
        raise KeyError(f"Unknown module: {name}")
    return dict(CURATED_MODULES[name])


def get_inverter(name: str) -> Dict[str, Any]:
    if name not in CURATED_INVERTERS:
        raise KeyError(f"Unknown inverter: {name}")
    return dict(CURATED_INVERTERS[name])


def search_modules(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search PVFree CEC module database (best-effort)."""
    try:
        r = requests.get(
            f"{PVFREE_BASE}/cecmodule/",
            params={"format": "json", "Name__icontains": query, "limit": limit},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        rows = data.get("results") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []
        out: List[Dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "name": row.get("Name") or row.get("name") or "Unknown",
                    "Wp": row.get("Pmp_ref") or row.get("Pmpo"),
                    "Voc": row.get("V_oc_ref") or row.get("Voco"),
                    "Vmp": row.get("V_mp_ref") or row.get("Vmpo"),
                    "Isc": row.get("I_sc_ref") or row.get("Isco"),
                    "Imp": row.get("I_mp_ref") or row.get("Impo"),
                    "beta_Voc": _pct_to_frac(row.get("beta_oc") or row.get("Bvoco")),
                    "beta_Vmp": _pct_to_frac(row.get("beta_mp") or row.get("Bvmpo")),
                    "alpha_Isc": row.get("alpha_sc") or row.get("Aisc"),
                    "T_NOCT": row.get("T_NOCT") or 45,
                    "source": "pvfree_cecmodule",
                }
            )
        return out
    except Exception as exc:
        _log.warning("PVFree module search failed: %s", exc)
        return []


def search_inverters(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    try:
        r = requests.get(
            f"{PVFREE_BASE}/pvinverter/",
            params={"format": "json", "Name__icontains": query, "limit": limit},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        rows = data.get("results") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []
        out: List[Dict[str, Any]] = []
        for row in rows:
            paco_w = row.get("Paco") or row.get("Paco_kW")
            paco_kw = float(paco_w) / 1000.0 if paco_w and float(paco_w) > 500 else float(paco_w or 0)
            out.append(
                {
                    "name": row.get("Name") or "Unknown",
                    "type": "string",
                    "Paco_kW": round(paco_kw, 1),
                    "Vdcmax": row.get("Vdcmax"),
                    "Vdco": row.get("Vdco"),
                    "Mppt_low": row.get("Mppt_low"),
                    "Mppt_high": row.get("Mppt_high"),
                    "Idcmax": row.get("Idcmax"),
                    "n_mppt": row.get("n_mppt") or 6,
                    "strings_per_mppt": 2,
                    "source": "pvfree_pvinverter",
                }
            )
        return out
    except Exception as exc:
        _log.warning("PVFree inverter search failed: %s", exc)
        return []


def _pct_to_frac(val: Optional[Any]) -> float:
    if val is None:
        return -0.0026
    v = float(val)
    return v / 100.0 if abs(v) > 0.05 else v
