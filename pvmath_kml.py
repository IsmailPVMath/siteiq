"""Shared KML/KMZ polygon extraction for Project Setup and TopoIQ."""
import io
import math
import re
import zipfile
import xml.etree.ElementTree as ET

BOUNDARY_COLORS = ["#22c55e", "#3b82f6", "#f59e0b", "#ec4899", "#8b5cf6", "#14b8a6"]
KML_NS = "http://www.opengis.net/kml/2.2"
KML = f"{{{KML_NS}}}"

_EXCLUDE_BOUNDARY_RE = re.compile(
    r"tracker|row|string|module|panel|restricted|exclusion|buffer|road|easement|"
    r"cable|inverter|subst|transformer|fence|layout|block(?!able)|"
    r"gentie|gen.?tie|bess|substation|access|parking|tie.?line|collection|"
    r"combiner|pile|rack",
    re.I,
)
_INCLUDE_BOUNDARY_RE = re.compile(
    r"site|boundary|buildable|parcel|field|area|limit|perimeter|develop|zone|"
    r"usable|solar|pv|plot|project",
    re.I,
)
_EXCLUDE_FOLDER_RE = re.compile(
    r"mv[\s\-]?circuit|circuit\s*\d|future\s*phase|collection|string|inverter|"
    r"combiner|tracker|module|row|layout|block\b|pile|rack|road|gentie|gen.?tie|"
    r"subst|bess|poi\b|access|gen[\s\-]?tie|wire|conduit|fence",
    re.I,
)
_UNNAMED_RE = re.compile(r"\bunnamed\b", re.I)


def _local_tag(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _kml_color_to_rgb(kml_color: str):
    """KML colours are aabbggrr; return (r, g, b) or None."""
    if not kml_color:
        return None
    c = kml_color.strip().lstrip("#").lower()
    if len(c) == 8:
        _, bb, gg, rr = c[0:2], c[2:4], c[4:6], c[6:8]
    elif len(c) == 6:
        bb, gg, rr = c[0:2], c[2:4], c[4:6]
    else:
        return None
    try:
        return int(rr, 16), int(gg, 16), int(bb, 16)
    except ValueError:
        return None


def is_vivid_boundary_stroke(rgb) -> bool:
    """True when KML assigns a non-default vivid line/fill colour (any hue)."""
    if not rgb:
        return False
    r, g, b = rgb
    if max(r, g, b) < 90:
        return False
    if max(r, g, b) - min(r, g, b) < 35:
        return False
    return max(r, g, b) >= 110


def is_magenta_boundary_color(rgb) -> bool:
    """Backward-compatible alias — prefer is_vivid_boundary_stroke."""
    return is_vivid_boundary_stroke(rgb)


def _display_name(full_name: str) -> str:
    """Short label for UI — drop long KMZ filename prefixes."""
    parts = [p.strip() for p in (full_name or "").split("/") if p.strip()]
    if not parts:
        return "Unnamed"
    for i, part in enumerate(parts):
        if _INCLUDE_BOUNDARY_RE.search(part):
            tail = parts[i:]
            return " / ".join(tail[-2:]) if len(tail) > 2 else " / ".join(tail)
    if len(parts) >= 2 and _UNNAMED_RE.search(parts[-1]):
        return f"{parts[-2]} / {parts[-1]}"
    return parts[-1]


def is_primary_site_feature(name: str, area_ha: float, line_rgb=None, poly_rgb=None) -> bool:
    """
    True for site parcels — primarily layer/folder names, not a specific colour.
    Vivid KML stroke colour is a secondary signal when names are generic.
    """
    if _EXCLUDE_FOLDER_RE.search(name or ""):
        return False
    if _INCLUDE_BOUNDARY_RE.search(name or ""):
        return True
    if _EXCLUDE_BOUNDARY_RE.search(name or "") and area_ha < 20.0:
        return False
    rgb = line_rgb or poly_rgb
    if is_vivid_boundary_stroke(rgb) and area_ha >= 3.0:
        return not _UNNAMED_RE.search(name or "") or area_ha >= 8.0
    if _UNNAMED_RE.search(name or ""):
        return False
    return area_ha >= 10.0 and not _EXCLUDE_BOUNDARY_RE.search(name or "")


def guess_boundary_enabled(name: str, area_ha: float, line_rgb=None, poly_rgb=None) -> bool:
    """Auto-select site parcels for analysis; skip layout / circuit geometry."""
    return is_primary_site_feature(name, area_ha, line_rgb, poly_rgb)


def normalize_ring_lonlat(pts):
    """Ensure closed ring as (lon, lat) tuples."""
    if not pts or len(pts) < 3:
        return pts
    out = [(float(p[0]), float(p[1])) for p in pts]
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def _parse_kml_coords(text):
    pairs = []
    for tok in (text or "").strip().split():
        parts = tok.split(",")
        if len(parts) >= 2:
            try:
                pairs.append((float(parts[0]), float(parts[1])))
            except ValueError:
                pass
    return pairs


def _coords_from_el(el):
    if el is None:
        return []
    c = el.find(f"{KML}coordinates")
    if c is None:
        c = el.find("coordinates")
    return _parse_kml_coords(c.text) if (c is not None and c.text) else []


def _gap_meters(pts):
    if len(pts) < 2:
        return float("inf")
    lat = pts[0][1]
    lat_m = 111320.0
    lon_m = 111320.0 * math.cos(math.radians(lat))
    return math.hypot(
        (pts[0][0] - pts[-1][0]) * lon_m,
        (pts[0][1] - pts[-1][1]) * lat_m,
    )


def _ring_area_ha_lonlat(pts):
    if len(pts) < 3:
        return 0.0
    lats = [p[1] for p in pts]
    mean_lat = sum(lats) / len(lats)
    lat_m = 111320.0
    lon_m = 111320.0 * math.cos(math.radians(mean_lat))
    mpts = [(p[0] * lon_m, p[1] * lat_m) for p in pts]
    n = len(mpts)
    area_m2 = abs(sum(
        mpts[i][0] * mpts[(i + 1) % n][1] - mpts[(i + 1) % n][0] * mpts[i][1]
        for i in range(n)
    )) / 2.0
    return area_m2 / 10_000


def _line_to_ring(pts, label, force_close=False):
    if not pts or len(pts) < 3:
        return None
    label = label or ""
    is_site = bool(_INCLUDE_BOUNDARY_RE.search(label))
    gap = _gap_meters(pts)

    if gap <= 1.0:
        return normalize_ring_lonlat(pts)

    closed = normalize_ring_lonlat(list(pts) + [pts[0]])
    area_ha = _ring_area_ha_lonlat(closed)

    if force_close and len(pts) >= 4:
        return closed

    max_gap = 2000.0 if is_site else 500.0
    if gap <= max_gap:
        return closed
    if is_site and len(pts) >= 4:
        return closed
    if area_ha >= 3.0 and len(pts) >= 4:
        return closed
    return None


def read_kml_bytes(raw: bytes, filename: str = "") -> bytes:
    if filename.lower().endswith(".kmz") or raw[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                kml_name = next((n for n in z.namelist() if n.lower().endswith(".kml")), None)
                if kml_name:
                    return z.read(kml_name)
        except Exception:
            pass
    return raw


def _colors_from_style_el(style_el):
    if style_el is None:
        return None, None
    line = style_el.find(f"{KML}LineStyle")
    if line is None:
        line = style_el.find("LineStyle")
    poly = style_el.find(f"{KML}PolyStyle")
    if poly is None:
        poly = style_el.find("PolyStyle")
    line_rgb, poly_rgb = None, None
    if line is not None:
        c = line.find(f"{KML}color")
        if c is None:
            c = line.find("color")
        if c is not None and c.text:
            line_rgb = _kml_color_to_rgb(c.text)
    if poly is not None:
        c = poly.find(f"{KML}color")
        if c is None:
            c = poly.find("color")
        if c is not None and c.text:
            poly_rgb = _kml_color_to_rgb(c.text)
    return line_rgb, poly_rgb


def _build_style_map(root):
    """Map style id → (line_rgb, poly_rgb), resolving StyleMap → normal Style."""
    styles = {}

    def _store(sid, line_rgb, poly_rgb):
        if sid:
            styles[sid] = (line_rgb, poly_rgb)

    for el in root.iter():
        if _local_tag(el.tag) != "Style":
            continue
        sid = el.get("id")
        _store(sid, *_colors_from_style_el(el))

    for sm in root.iter():
        if _local_tag(sm.tag) != "StyleMap":
            continue
        sid = sm.get("id")
        for pair in sm:
            if _local_tag(pair.tag) != "Pair":
                continue
            key_el = pair.find(f"{KML}key")
            if key_el is None:
                key_el = pair.find("key")
            if key_el is not None and (key_el.text or "").strip() != "normal":
                continue
            url_el = pair.find(f"{KML}styleUrl")
            if url_el is None:
                url_el = pair.find("styleUrl")
            if url_el is None or not url_el.text:
                continue
            ref = url_el.text.strip().lstrip("#")
            if ref in styles:
                _store(sid, *styles[ref])

    return styles


def _placemark_colors(pm, style_map):
    for child in pm:
        if _local_tag(child.tag) == "Style":
            return _colors_from_style_el(child)
    url_el = pm.find(f"{KML}styleUrl")
    if url_el is None:
        url_el = pm.find("styleUrl")
    if url_el is not None and url_el.text:
        ref = url_el.text.strip().lstrip("#")
        if ref in style_map:
            return style_map[ref]
    return None, None


def _parse_kml_root(root) -> list:
    """Parse KML into feature dicts with coords and style metadata."""
    features = []
    seen = set()
    counter = [0]
    style_map = _build_style_map(root)

    def _unique_key(label):
        counter[0] += 1
        base = (label or "Unnamed").strip()
        return base if not any(f["name"] == base for f in features) else f"{base} ({counter[0]})"

    def _add_ring(pts, label, force_close=False, line_rgb=None, poly_rgb=None):
        ring = _line_to_ring(pts, label, force_close=force_close)
        if not ring or len(ring) < 4:
            return
        area_ha = _ring_area_ha_lonlat(ring)
        if area_ha < 0.5 and not _INCLUDE_BOUNDARY_RE.search(label or ""):
            return
        if _EXCLUDE_BOUNDARY_RE.search(label or "") and area_ha < 15.0:
            if not is_vivid_boundary_stroke(line_rgb or poly_rgb):
                return
        sig = (round(ring[0][0], 5), round(ring[0][1], 5), len(ring))
        if sig in seen:
            return
        seen.add(sig)
        name = _unique_key(label)
        features.append({
            "name": name,
            "display_name": _display_name(name),
            "coords": ring,
            "area_ha": round(area_ha, 2),
            "line_rgb": line_rgb,
            "poly_rgb": poly_rgb,
            "is_styled_boundary": is_vivid_boundary_stroke(line_rgb or poly_rgb),
            "is_primary": is_primary_site_feature(name, area_ha, line_rgb, poly_rgb),
        })

    def _geom_parts(geom_el, base_name, line_rgb, poly_rgb):
        tag = _local_tag(geom_el.tag)
        idx = [0]

        def _one(el, suffix=""):
            lt = _local_tag(el.tag)
            label = f"{base_name}{suffix}"
            if lt == "Polygon":
                outer = el.find(f"{KML}outerBoundaryIs/{KML}LinearRing")
                if outer is None:
                    outer = el.find("outerBoundaryIs/LinearRing")
                _add_ring(_coords_from_el(outer), label, line_rgb=line_rgb, poly_rgb=poly_rgb)
            elif lt == "LinearRing":
                _add_ring(_coords_from_el(el), label, line_rgb=line_rgb, poly_rgb=poly_rgb)
            elif lt == "LineString":
                _add_ring(
                    _coords_from_el(el), label, force_close=True,
                    line_rgb=line_rgb, poly_rgb=poly_rgb,
                )
            elif lt == "MultiGeometry":
                for child in el:
                    idx[0] += 1
                    _one(child, f" — part {idx[0]}" if idx[0] > 1 else "")

        if tag == "MultiGeometry":
            for child in geom_el:
                idx[0] += 1
                _one(child, f" — part {idx[0]}" if idx[0] > 1 else "")
        else:
            _one(geom_el)

    def _process_placemark(pm, folder_path=""):
        name_el = pm.find(f"{KML}name")
        if name_el is None:
            name_el = pm.find("name")
        pm_name = name_el.text.strip() if (name_el is not None and name_el.text) else "Unnamed"
        full_name = f"{folder_path}{pm_name}" if folder_path else pm_name
        line_rgb, poly_rgb = _placemark_colors(pm, style_map)

        for child in pm:
            lt = _local_tag(child.tag)
            if lt in ("Polygon", "LineString", "LinearRing", "MultiGeometry"):
                _geom_parts(child, full_name, line_rgb, poly_rgb)

    def _walk(node, folder_path=""):
        tag = _local_tag(node.tag)
        if tag in ("kml", "Document"):
            for child in node:
                _walk(child, folder_path)
        elif tag == "Folder":
            name_el = node.find(f"{KML}name")
            if name_el is None:
                name_el = node.find("name")
            fname = name_el.text.strip() if (name_el is not None and name_el.text) else ""
            new_path = f"{folder_path}{fname} / " if fname else folder_path
            for child in node:
                _walk(child, new_path)
        elif tag == "Placemark":
            _process_placemark(node, folder_path)

    _walk(root)

    if not features:
        for pm in root.iter("Placemark"):
            _process_placemark(pm, "")

    return features


def parse_kml_features(raw_bytes) -> list:
    try:
        root = ET.fromstring(raw_bytes)
    except Exception:
        return []
    return _parse_kml_root(root)


def parse_kmz_features(raw: bytes) -> list:
    if raw[:2] != b"PK":
        return parse_kml_features(raw)
    merged = []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for name in z.namelist():
                if name.lower().endswith(".kml"):
                    merged.extend(parse_kml_features(z.read(name)))
    except Exception:
        return parse_kml_features(read_kml_bytes(raw))
    return merged or parse_kml_features(read_kml_bytes(raw))


def features_to_lonlat_dict(features: list, primary_only: bool = False) -> dict:
    out = {}
    for f in features:
        if primary_only and not f.get("is_primary"):
            continue
        out[f["name"]] = f["coords"]
    return out


def parse_kml_all_polygons(raw_bytes) -> dict:
    return features_to_lonlat_dict(parse_kml_features(raw_bytes))


def parse_kmz_all_polygons(raw: bytes) -> dict:
    return features_to_lonlat_dict(parse_kmz_features(raw))


def boundaries_from_features(features: list, source_key: str) -> list:
    """Build boundary dicts for session state (lon/lat coords)."""
    out = []
    for i, f in enumerate(features):
        out.append({
            "id": f"{source_key}_{i}",
            "name": f.get("display_name") or f["name"],
            "full_name": f["name"],
            "coords": f["coords"],
            "enabled": guess_boundary_enabled(
                f["name"], f.get("area_ha", 0),
                f.get("line_rgb"), f.get("poly_rgb"),
            ),
            "is_styled_boundary": f.get("is_styled_boundary", False),
            "is_primary": f.get("is_primary", True),
        })
    return out


def lonlat_polys_to_latlon(all_polys: dict) -> dict:
    out = {}
    for name, coords in all_polys.items():
        ring = [[c[1], c[0]] for c in coords]
        if ring and ring[0] == ring[-1] and len(ring) > 3:
            ring = ring[:-1]
        out[name] = ring
    return out


def boundaries_from_kmz_latlon(raw: bytes, source_key: str) -> tuple:
    """KMZ → lat/lon boundary dicts for Project Setup. Returns (boundaries, hidden_count, total)."""
    features = parse_kmz_features(raw)
    bounds_lonlat = boundaries_from_features(features, source_key)
    latlon = lonlat_polys_to_latlon({b["full_name"]: b["coords"] for b in bounds_lonlat})
    out = []
    for b in bounds_lonlat:
        out.append({
            "id": b["id"],
            "name": b["name"],
            "full_name": b["full_name"],
            "coords": latlon[b["full_name"]],
            "enabled": b["enabled"],
            "is_styled_boundary": b.get("is_styled_boundary", False),
            "is_primary": b.get("is_primary", True),
        })
    hidden = sum(1 for b in out if not b.get("is_primary"))
    return out, hidden, len(features)
