"""Static EUR ↔ local currency rates — owner updates quarterly (no live FX API)."""

from __future__ import annotations

LOCAL_CURRENCY: dict[str, str] = {
    "DE": "EUR",
    "AT": "EUR",
    "CH": "CHF",
    "FR": "EUR",
    "IT": "EUR",
    "ES": "EUR",
    "PL": "PLN",
    "NL": "EUR",
    "BE": "EUR",
    "IN": "INR",
    "AU": "AUD",
    "NZ": "NZD",
    "US": "USD",
    "CA": "CAD",
    "MX": "MXN",
    "UK": "GBP",
    "GB": "GBP",
    "ZA": "ZAR",
    "NG": "NGN",
    "KE": "KES",
    "JP": "JPY",
    "KR": "KRW",
    "CN": "CNY",
}

# Local currency units per 1 EUR (e.g. INR 90.0 means €1 = ₹90).
EUR_FX: dict[str, float] = {
    "EUR": 1.0,
    "USD": 1.08,
    "INR": 90.0,
    "AUD": 1.65,
    "GBP": 0.84,
    "CHF": 0.96,
    "PLN": 4.25,
    "CAD": 1.47,
    "NZD": 1.79,
    "ZAR": 20.0,
    "JPY": 162.0,
    "MXN": 19.0,
    "NGN": 1650.0,
    "KES": 140.0,
    "KRW": 1450.0,
    "CNY": 7.8,
}


def _norm_iso(country: str) -> str:
    c = (country or "").strip().upper()
    if len(c) == 2 and c.isalpha():
        return c
    low = (country or "").strip().lower()
    mapping = {
        "germany": "DE",
        "deutschland": "DE",
        "austria": "AT",
        "österreich": "AT",
        "switzerland": "CH",
        "schweiz": "CH",
        "france": "FR",
        "italy": "IT",
        "italia": "IT",
        "spain": "ES",
        "españa": "ES",
        "poland": "PL",
        "polska": "PL",
        "india": "IN",
        "australia": "AU",
        "united states": "US",
        "usa": "US",
        "america": "US",
        "united kingdom": "GB",
        "uk": "GB",
        "britain": "GB",
        "netherlands": "NL",
        "belgium": "BE",
    }
    for key, iso in mapping.items():
        if key in low:
            return iso
    return "DE" if "de" == low else ""


def country_iso(country: str) -> str:
    iso = _norm_iso(country)
    return iso if iso else "DE"


def currency_code(country: str) -> str:
    iso = country_iso(country)
    return LOCAL_CURRENCY.get(iso, "EUR")


def eur_fx_rate(country: str) -> float:
    code = currency_code(country)
    return EUR_FX.get(code, 1.0)


def to_local(eur_value: float, country: str) -> float:
    return eur_value * eur_fx_rate(country)


def local_to_eur(local_value: float, country: str) -> float:
    fx = eur_fx_rate(country)
    if fx <= 0:
        return local_value
    return local_value / fx
