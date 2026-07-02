"""Curated module/inverter database + cached PVFree API lookup."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from layoutiq.curated_equipment_data import CURATED_INVERTERS, CURATED_MODULES

_log = logging.getLogger(__name__)

PVFREE_BASE = "https://pvfree.azurewebsites.net/api/v1"
PVFREE_TIMEOUT_SEC = 5.0
CACHE_TTL_SEC = 604800  # 7 days

_redis_client = None
_redis_checked = False


def _get_redis():
    """Lazy Redis client; returns None if unavailable."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    url = (os.environ.get("PVMATH_REDIS_URL") or os.environ.get("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        from redis import Redis

        _redis_client = Redis.from_url(url, decode_responses=True)
        _redis_client.ping()
    except Exception as exc:
        _log.debug("Redis cache unavailable for PVFree: %s", exc)
        _redis_client = None
    return _redis_client


def _cache_get(key: str) -> Optional[List[Dict[str, Any]]]:
    client = _get_redis()
    if not client:
        return None
    try:
        raw = client.get(key)
        if raw:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
    except Exception as exc:
        _log.debug("PVFree cache read failed: %s", exc)
    return None


def _cache_set(key: str, value: List[Dict[str, Any]]) -> None:
    if not value:
        return
    client = _get_redis()
    if not client:
        return
    try:
        client.setex(key, CACHE_TTL_SEC, json.dumps(value))
    except Exception as exc:
        _log.debug("PVFree cache write failed: %s", exc)


def _cache_key(kind: str, query: str) -> str:
    return f"pvfree:{kind}:{query.lower().strip()}"


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


def _pct_to_frac(val: Optional[Any]) -> float:
    if val is None:
        return -0.0026
    v = float(val)
    return v / 100.0 if abs(v) > 0.05 else v


def _parse_module_rows(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
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


def _parse_inverter_rows(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
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


async def _fetch_pvfree_modules(query: str, limit: int) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=PVFREE_TIMEOUT_SEC) as client:
        r = await client.get(
            f"{PVFREE_BASE}/cecmodule/",
            params={"format": "json", "Name__icontains": query, "limit": limit},
        )
        r.raise_for_status()
        data = r.json()
        rows = data.get("results") if isinstance(data, dict) else data
        return _parse_module_rows(rows)


async def _fetch_pvfree_inverters(query: str, limit: int) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=PVFREE_TIMEOUT_SEC) as client:
        r = await client.get(
            f"{PVFREE_BASE}/pvinverter/",
            params={"format": "json", "Name__icontains": query, "limit": limit},
        )
        r.raise_for_status()
        data = r.json()
        rows = data.get("results") if isinstance(data, dict) else data
        return _parse_inverter_rows(rows)


async def search_modules(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search PVFree CEC module database (cached, async httpx)."""
    q = (query or "").strip()
    if not q:
        return []
    key = _cache_key("modules", q)
    cached = _cache_get(key)
    if cached is not None:
        return cached[:limit]
    try:
        results = await _fetch_pvfree_modules(q, limit)
        _cache_set(key, results)
        return results
    except Exception as exc:
        _log.warning("PVFree module search failed: %s", exc)
        return []


async def search_inverters(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search PVFree inverter database (cached, async httpx)."""
    q = (query or "").strip()
    if not q:
        return []
    key = _cache_key("inverters", q)
    cached = _cache_get(key)
    if cached is not None:
        return cached[:limit]
    try:
        results = await _fetch_pvfree_inverters(q, limit)
        _cache_set(key, results)
        return results
    except Exception as exc:
        _log.warning("PVFree inverter search failed: %s", exc)
        return []

