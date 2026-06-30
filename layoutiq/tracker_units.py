"""Tracker unit grouping, counts, and bounding rectangles."""

from __future__ import annotations

from collections import Counter
from typing import Any

from shapely.geometry import box
from shapely.ops import unary_union

from layoutiq.tracker_styles import style_for_unit


def count_tracker_units_by_size(layout: dict[str, Any]) -> dict[str, int]:
    """Aggregate e.g. {'8S': 120, '7S': 34} from rows_data tracker_units lists."""
    counter: Counter[int] = Counter()
    for row in layout.get("rows_data") or []:
        for n in row.get("tracker_units") or []:
            counter[int(n)] += 1
    for n, count in sorted((layout.get("tracker_unit_counts") or {}).items(), key=lambda x: -int(x[0])):
        if int(n) not in counter:
            counter[int(n)] += int(count)
    return {style_for_unit(k)["label"]: v for k, v in sorted(counter.items(), reverse=True)}


def tracker_unit_bom_lines(layout: dict[str, Any]) -> dict[str, str]:
    """BOM rows for tracker unit legend (8S, 7S, …)."""
    counts = count_tracker_units_by_size(layout)
    if not counts:
        return {}
    lines = {f"Tracker {label}": f"{qty:,}" for label, qty in counts.items()}
    total_units = sum(counts.values())
    lines["Total tracker units"] = f"{total_units:,}"
    return lines


def build_tracker_unit_polys(layout: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Build one bounding rectangle per rigid tracker unit from placed strings.

    Returns list of {poly, unit_strings, row_index, unit_index, style}.
    """
    if layout.get("tracker_unit_polys"):
        return layout["tracker_unit_polys"]

    string_polys = layout.get("string_polys") or []
    string_row_local_idx = layout.get("string_row_local_idx") or []
    rows_data = layout.get("rows_data") or []
    if not string_polys or not rows_data:
        return []

    # Group string indices by row local index.
    row_to_string_idxs: dict[int, list[int]] = {}
    for s_idx, r_idx in enumerate(string_row_local_idx):
        if s_idx < len(string_polys):
            row_to_string_idxs.setdefault(r_idx, []).append(s_idx)

    units: list[dict[str, Any]] = []
    unit_global = 0
    for r_idx, row in enumerate(rows_data):
        unit_sizes = row.get("tracker_units") or []
        if not unit_sizes:
            continue
        str_idxs = row_to_string_idxs.get(r_idx, [])
        cursor = 0
        for u_idx, n_strings in enumerate(unit_sizes):
            n = int(n_strings)
            chunk = str_idxs[cursor : cursor + n]
            cursor += n
            if len(chunk) < n:
                continue
            polys = [string_polys[i] for i in chunk]
            merged = unary_union(polys)
            if merged.is_empty:
                continue
            minx, miny, maxx, maxy = merged.bounds
            unit_poly = box(minx, miny, maxx, maxy)
            style = style_for_unit(n)
            units.append(
                {
                    "poly": unit_poly,
                    "unit_strings": n,
                    "string_indices": chunk,
                    "row_index": r_idx + 1,
                    "unit_index": unit_global + 1,
                    "style": style,
                }
            )
            unit_global += 1
    return units
