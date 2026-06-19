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
    r"gentie|gen.?tie|bess|substation|access|parking|tie.?line|collection",
    re.I,
)
_INCLUDE_BOUNDARY_RE = re.compile(
    r"site|boundary|buildable|parcel|field|area|limit|perimeter|develop|zone|"
    r"usable|solar|pv|plot|project",
    re.I,
)


def _local_tag(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def guess_boundary_enabled(name: str, area_ha: float) -> bool:
    """Auto-select likely site parcels; skip tracker rows and tiny layout shapes."""
    if _EXCLUDE_BOUNDARY_RE.search(name or ""):
        return False
    if _INCLUDE_BOUNDARY_RE.search(name or ""):
        return True
    if area_ha < 2.0:
        return False
    return area_ha >= 5.0


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
    """Rough area (ha) for a (lon,lat) ring — for filtering tiny shapes."""
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
    """Turn Polygon ring or GIS boundary LineString into a closed ring."""
    if not pts or len(pts) < 3:
        return None
    label = label or ""
    is_site = bool(_INCLUDE_BOUNDARY_RE.search(label))
    gap = _gap_meters(pts)

    if gap <= 1.0:
        return normalize_ring_lonlat(pts)

    closed = normalize_ring_lonlat(list(pts) + [pts[0]])
    area_ha = _ring_area_ha_lonlat(closed)

    # Shapefile → KML exports use open LineStrings for parcel boundaries
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
    """Return inner KML bytes from .kml or .kmz upload."""
    if filename.lower().endswith(".kmz") or raw[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                kml_name = next((n for n in z.namelist() if n.lower().endswith(".kml")), None)
                if kml_name:
                    return z.read(kml_name)
        except Exception:
            pass
    return raw


def _parse_kml_root(root) -> dict:
    """Parse one KML ElementTree root into {name: [(lon,lat),...]}."""
    results = {}
    seen = set()
    counter = [0]

    def _unique_key(label):
        counter[0] += 1
        base = (label or "Unnamed").strip()
        return base if base not in results else f"{base} ({counter[0]})"

    def _add_ring(pts, label, force_close=False):
        ring = _line_to_ring(pts, label, force_close=force_close)
        if not ring or len(ring) < 4:
            return
        area_ha = _ring_area_ha_lonlat(ring)
        # Skip thousands of small tracker/module rectangles from layout exports
        if area_ha < 0.5 and not _INCLUDE_BOUNDARY_RE.search(label or ""):
            return
        if _EXCLUDE_BOUNDARY_RE.search(label or "") and area_ha < 15.0:
            return
        sig = (round(ring[0][0], 5), round(ring[0][1], 5), len(ring))
        if sig in seen:
            return
        seen.add(sig)
        results[_unique_key(label)] = ring

    def _geom_parts(geom_el, base_name):
        tag = _local_tag(geom_el.tag)
        idx = [0]

        def _one(el, suffix=""):
            tag = _local_tag(el.tag)
            label = f"{base_name}{suffix}"
            if tag == "Polygon":
                outer = el.find(f"{KML}outerBoundaryIs/{KML}LinearRing")
                if outer is None:
                    outer = el.find("outerBoundaryIs/LinearRing")
                _add_ring(_coords_from_el(outer), label)
            elif tag == "LinearRing":
                _add_ring(_coords_from_el(el), label)
            elif tag == "LineString":
                _add_ring(_coords_from_el(el), label, force_close=True)
            elif tag == "MultiGeometry":
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

        for child in pm:
            lt = _local_tag(child.tag)
            if lt in ("Polygon", "LineString", "LinearRing", "MultiGeometry"):
                _geom_parts(child, full_name)

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

    # Fallback without namespaces
    if not results:
        for pm in root.iter("Placemark"):
            _process_placemark(pm, "")

    return results


def parse_kml_all_polygons(raw_bytes) -> dict:
    """Extract every boundary ring from KML (values: list of (lon, lat))."""
    try:
        root = ET.fromstring(raw_bytes)
    except Exception:
        return {}
    return _parse_kml_root(root)


def parse_kmz_all_polygons(raw: bytes) -> dict:
    """Parse KMZ — merge polygons from every .kml file in the archive."""
    if raw[:2] != b"PK":
        return parse_kml_all_polygons(raw)
    merged = {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for name in z.namelist():
                if name.lower().endswith(".kml"):
                    part = parse_kml_all_polygons(z.read(name))
                    for k, v in part.items():
                        key = k if k not in merged else f"{name}: {k}"
                        merged[key] = v
    except Exception:
        return parse_kml_all_polygons(read_kml_bytes(raw))
    return merged or parse_kml_all_polygons(read_kml_bytes(raw))


def lonlat_polys_to_latlon(all_polys: dict) -> dict:
    """Convert {name: [(lon,lat)...]} → {name: [[lat,lon],...]}."""
    out = {}
    for name, coords in all_polys.items():
        ring = [[c[1], c[0]] for c in coords]
        if ring and ring[0] == ring[-1] and len(ring) > 3:
            ring = ring[:-1]
        out[name] = ring
    return out
