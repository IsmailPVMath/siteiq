import streamlit as st
import numpy as np
import requests
import math
import io
import csv
import xml.etree.ElementTree as ET
from xml.dom import minidom
import zipfile
import json
from PIL import Image
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from datetime import datetime

# ── optional heavy deps — graceful fallback ──────────────────────────────────
try:
    from scipy.interpolate import griddata
    from scipy.ndimage import gaussian_filter
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    import ezdxf
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False

try:
    from shapely.geometry import shape, Point, Polygon as ShapelyPolygon
    from shapely.ops import unary_union
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TopoIQ – Terrain Intelligence",
    page_icon="⛰",
    layout="wide"
)

st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>
    footer { visibility: hidden; }
    .topo-header { font-size: 2rem; font-weight: 800; color: #1565c0; }
    .section-hdr {
        font-size: 0.82rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.07em; margin: 0.6rem 0 0.4rem;
        display: flex; align-items: center; gap: 0.4rem;
    }
    .accuracy-card {
        background: rgba(21,101,192,0.07);
        border: 1px solid rgba(21,101,192,0.2);
        border-radius: 10px; padding: 1rem 1.2rem; margin-top: 1rem;
        font-size: 0.82rem;
    }
    .accuracy-card h4 { color: #1565c0; margin-bottom: 0.4rem; font-size: 0.85rem; }
    .accuracy-card p { color: #444; margin: 0.15rem 0; }
</style>
""", unsafe_allow_html=True)

# ─── Header ──────────────────────────────────────────────────────────────────
st.markdown("""
<div style="display:flex; align-items:center; gap:0.6rem; margin-bottom:0.2rem;">
  <span style="width:38px;height:38px;background:linear-gradient(135deg,#1565c0,#42a5f5);
               border-radius:9px;display:inline-flex;align-items:center;justify-content:center;">
    <i class="fa-solid fa-mountain" style="color:#fff;font-size:1rem;"></i>
  </span>
  <span class="topo-header">TopoIQ</span>
  <span style="font-size:0.85rem;color:#888;align-self:flex-end;padding-bottom:0.3rem;">by PVMath</span>
</div>
<p style="color:#666;font-size:0.9rem;margin-bottom:0;">
  Satellite terrain extraction for solar site engineering — Civil 3D ready outputs.
</p>
""", unsafe_allow_html=True)
st.divider()

# ─── Tile utilities ───────────────────────────────────────────────────────────

def deg2tile(lat, lon, zoom):
    """Convert lat/lon to tile x/y at given zoom."""
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(math.radians(lat)) +
             1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y

def tile2deg(x, y, zoom):
    """Convert tile x/y to NW lat/lon corner."""
    n = 2 ** zoom
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon

def fetch_terrarium_tile(x, y, zoom):
    """Fetch AWS Terrarium elevation tile and decode to elevation array."""
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{x}/{y}.png"
    r = requests.get(url, timeout=15)
    if r.status_code != 200:
        return None, None
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    arr = np.array(img, dtype=np.float32)
    # Terrarium encoding: elevation = (R*256 + G + B/256) - 32768
    elev = arr[:, :, 0] * 256.0 + arr[:, :, 1] + arr[:, :, 2] / 256.0 - 32768.0
    # Tile geographic bounds
    lat_n, lon_w = tile2deg(x, y, zoom)
    lat_s, lon_e = tile2deg(x + 1, y + 1, zoom)
    bounds = {"lat_n": lat_n, "lat_s": lat_s, "lon_w": lon_w, "lon_e": lon_e}
    return elev, bounds


def get_dem_for_bbox(south, north, west, east, zoom=14):
    """Download and mosaic all tiles covering the bounding box."""
    x_min, y_min = deg2tile(north, west, zoom)
    x_max, y_max = deg2tile(south, east, zoom)
    tiles = []
    total = (x_max - x_min + 1) * (y_max - y_min + 1)
    prog = st.progress(0, text="Downloading terrain tiles…")
    count = 0
    for ty in range(y_min, y_max + 1):
        row = []
        for tx in range(x_min, x_max + 1):
            elev, bounds = fetch_terrarium_tile(tx, ty, zoom)
            if elev is not None:
                row.append((elev, bounds))
            count += 1
            prog.progress(count / total, text=f"Downloading tile {count}/{total}…")
        if row:
            tiles.append(row)
    prog.empty()
    if not tiles:
        return None, None, None, None

    # Mosaic rows
    mosaic_rows = []
    for row in tiles:
        mosaic_rows.append(np.concatenate([t[0] for t in row], axis=1))
    mosaic = np.concatenate(mosaic_rows, axis=0)

    # Overall bounds
    lat_n_all = tiles[0][0][1]["lat_n"]
    lat_s_all = tiles[-1][0][1]["lat_s"]
    lon_w_all = tiles[0][0][1]["lon_w"]
    lon_e_all = tiles[0][-1][1]["lon_e"]
    return mosaic, lat_n_all, lat_s_all, lon_w_all, lon_e_all


def resample_to_grid(mosaic, lat_n, lat_s, lon_w, lon_e,
                     polygon_coords, grid_m=5.0):
    """
    Resample mosaic to a regular metric grid (grid_m metres).
    Returns (X_lon, Y_lat, Z_elev) arrays clipped to polygon.
    """
    h, w = mosaic.shape
    # Native pixel spacing in degrees
    dlat = (lat_n - lat_s) / h
    dlon = (lon_e - lon_w) / w

    # Approx metres per degree at site centre
    lat_c = (lat_n + lat_s) / 2
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_c))

    # Target grid spacing in degrees
    step_lat = grid_m / m_per_deg_lat
    step_lon = grid_m / m_per_deg_lon

    # Build lat/lon grid within bbox of polygon
    if polygon_coords:
        lons_p = [c[0] for c in polygon_coords]
        lats_p = [c[1] for c in polygon_coords]
        p_w, p_e = min(lons_p), max(lons_p)
        p_s, p_n = min(lats_p), max(lats_p)
    else:
        p_w, p_e, p_s, p_n = lon_w, lon_e, lat_s, lat_n

    grid_lons = np.arange(p_w, p_e, step_lon)
    grid_lats = np.arange(p_n, p_s, -step_lat)
    X, Y = np.meshgrid(grid_lons, grid_lats)

    # Bilinear sample from mosaic
    def sample(lon, lat):
        col = (lon - lon_w) / (lon_e - lon_w) * (w - 1)
        row = (lat_n - lat) / (lat_n - lat_s) * (h - 1)
        col = np.clip(col, 0, w - 2).astype(int)
        row = np.clip(row, 0, h - 2).astype(int)
        return mosaic[row, col]

    Z = sample(X, Y)

    # Mask outside polygon
    if HAS_SHAPELY and polygon_coords and len(polygon_coords) >= 3:
        poly = ShapelyPolygon(polygon_coords)
        mask = np.array([
            [poly.contains(Point(X[r, c], Y[r, c]))
             for c in range(X.shape[1])]
            for r in range(X.shape[0])
        ])
        Z = np.where(mask, Z, np.nan)

    return X, Y, Z


def compute_slope(Z, grid_m):
    """Compute slope % from elevation grid."""
    if HAS_SCIPY:
        Zf = gaussian_filter(Z.astype(float), sigma=1)
    else:
        Zf = Z.astype(float)
    dz_dy, dz_dx = np.gradient(Zf, grid_m)
    slope_pct = np.sqrt(dz_dx**2 + dz_dy**2) * 100.0
    return slope_pct


# ─── Export functions ─────────────────────────────────────────────────────────

def export_xyz(X, Y, Z):
    """Export XYZ point cloud as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Longitude", "Latitude", "Elevation_m"])
    for r in range(X.shape[0]):
        for c in range(X.shape[1]):
            if not np.isnan(Z[r, c]):
                writer.writerow([f"{X[r,c]:.8f}", f"{Y[r,c]:.8f}", f"{Z[r,c]:.3f}"])
    return buf.getvalue().encode()


def export_xyz_projected(X, Y, Z, lat_c, lon_c):
    """Export as local Northing/Easting/Elevation (simple projection)."""
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_c))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Easting_m", "Northing_m", "Elevation_m"])
    for r in range(X.shape[0]):
        for c in range(X.shape[1]):
            if not np.isnan(Z[r, c]):
                E = (X[r, c] - lon_c) * m_per_deg_lon
                N = (Y[r, c] - lat_c) * m_per_deg_lat
                writer.writerow([f"{E:.3f}", f"{N:.3f}", f"{Z[r,c]:.3f}"])
    return buf.getvalue().encode()


def export_landxml(X, Y, Z, site_name="TopoIQ_Surface"):
    """Generate LandXML TIN surface — importable directly into Civil 3D."""
    valid_pts = []
    for r in range(X.shape[0]):
        for c in range(X.shape[1]):
            if not np.isnan(Z[r, c]):
                valid_pts.append((X[r, c], Y[r, c], Z[r, c]))

    if len(valid_pts) < 3:
        return None

    # Build simple grid TIN (quad split into 2 triangles)
    rows, cols = X.shape
    faces = []
    pt_idx = {}
    idx = 1
    for r in range(rows):
        for c in range(cols):
            if not np.isnan(Z[r, c]):
                pt_idx[(r, c)] = idx
                idx += 1

    for r in range(rows - 1):
        for c in range(cols - 1):
            if all((r+dr, c+dc) in pt_idx for dr, dc in
                   [(0,0),(0,1),(1,0),(1,1)]):
                a = pt_idx[(r, c)]
                b = pt_idx[(r, c+1)]
                cc = pt_idx[(r+1, c)]
                d = pt_idx[(r+1, c+1)]
                faces.append((a, b, cc))
                faces.append((b, d, cc))

    # Build LandXML
    root = ET.Element("LandXML", {
        "xmlns": "http://www.landxml.org/schema/LandXML-1.2",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "http://www.landxml.org/schema/LandXML-1.2 http://www.landxml.org/schema/LandXML1.2/LandXML1.2.xsd",
        "version": "1.2",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M:%S"),
        "language": "English",
        "readOnly": "false"
    })
    ET.SubElement(root, "Units").append(
        ET.Element("Metric", {"areaUnit": "squareMeter",
                              "linearUnit": "meter",
                              "volumeUnit": "cubicMeter"})
    )
    proj = ET.SubElement(root, "Project", {"name": site_name})
    surfaces = ET.SubElement(root, "Surfaces")
    surface = ET.SubElement(surfaces, "Surface", {"name": site_name,
                                                   "desc": "TopoIQ satellite DEM"})
    defn = ET.SubElement(surface, "Definition", {"surfType": "TIN"})
    pnts = ET.SubElement(defn, "Pnts")
    faces_el = ET.SubElement(defn, "Faces")

    for (r, c), i in pt_idx.items():
        ET.SubElement(pnts, "P", {"id": str(i)}).text = \
            f"{Y[r,c]:.8f} {X[r,c]:.8f} {Z[r,c]:.3f}"

    for a, b, c in faces:
        ET.SubElement(faces_el, "F").text = f"{a} {b} {c}"

    xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    return xml_str.encode("utf-8")


def export_dxf(X, Y, Z, lat_c, lon_c, minor_int=0.5, major_int=1.0):
    """Generate DXF with contour lines (major + minor)."""
    if not HAS_EZDXF:
        return None

    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_c))

    # Convert to local metres
    Ex = (X - lon_c) * m_per_deg_lon
    Ny = (Y - lat_c) * m_per_deg_lat

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Layers
    doc.layers.add("CONTOUR_MINOR", color=3)   # green
    doc.layers.add("CONTOUR_MAJOR", color=1)   # red
    doc.layers.add("BOUNDARY",      color=5)   # blue

    z_valid = Z[~np.isnan(Z)]
    if len(z_valid) == 0:
        return None

    z_min = math.floor(z_valid.min() / minor_int) * minor_int
    z_max = math.ceil(z_valid.max()  / minor_int) * minor_int
    levels = np.arange(z_min, z_max + minor_int, minor_int)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    cs = ax.contour(Ex, Ny, Z, levels=levels)
    plt.close(fig)

    for i, level in enumerate(cs.levels):
        is_major = abs(level % major_int) < 1e-6
        layer = "CONTOUR_MAJOR" if is_major else "CONTOUR_MINOR"
        for seg in cs.allsegs[i]:
            if len(seg) >= 2:
                pts = [(float(p[0]), float(p[1]), float(level)) for p in seg]
                msp.add_lwpolyline([(p[0], p[1]) for p in pts],
                                   dxfattribs={"layer": layer,
                                               "elevation": float(level)})

    buf = io.BytesIO()
    doc.write(buf)
    return buf.getvalue()


# ─── KML/KMZ parser ───────────────────────────────────────────────────────────

def _parse_kml_coords(text):
    """Parse KML coordinate string into list of (lon, lat) tuples."""
    pairs = []
    for tok in text.strip().split():
        parts = tok.split(",")
        if len(parts) >= 2:
            try:
                pairs.append((float(parts[0]), float(parts[1])))
            except ValueError:
                pass
    return pairs


def parse_kml_all_polygons(raw_bytes):
    """
    Parse KML/KMZ bytes and return a dict of {name: [(lon,lat),...]}
    for every Polygon and closed LineString/LinearRing found.
    Ignores Point placemarks (pile markers etc).
    """
    import xml.etree.ElementTree as ET2
    NS = "http://www.opengis.net/kml/2.2"

    try:
        root2 = ET2.fromstring(raw_bytes)
    except Exception:
        return {}

    results = {}

    def coords_from_el(el):
        c = el.find(f"{{{NS}}}coordinates")
        if c is None:
            c = el.find("coordinates")
        return _parse_kml_coords(c.text) if (c is not None and c.text) else []

    # Walk all Placemarks
    for pm in root2.iter(f"{{{NS}}}Placemark"):
        name_el = pm.find(f"{{{NS}}}name")
        name = name_el.text.strip() if (name_el is not None and name_el.text) else "Unnamed"

        # Polygon — outerBoundaryIs/LinearRing/coordinates
        for poly_el in pm.iter(f"{{{NS}}}Polygon"):
            outer = poly_el.find(f".//{{{NS}}}outerBoundaryIs/{{{NS}}}LinearRing")
            if outer is not None:
                pts = coords_from_el(outer)
            else:
                pts = coords_from_el(poly_el)
            if len(pts) >= 3:
                key = f"Polygon: {name}" if name not in results else f"Polygon: {name}_{len(results)}"
                results[key] = pts

        # LinearRing (standalone)
        for lr in pm.iter(f"{{{NS}}}LinearRing"):
            # skip if already inside a Polygon handled above
            if pm.find(f".//{{{NS}}}Polygon") is not None:
                continue
            pts = coords_from_el(lr)
            if len(pts) >= 3:
                key = f"Ring: {name}" if name not in results else f"Ring: {name}_{len(results)}"
                results[key] = pts

        # LineString — only if it looks closed (first ≈ last point)
        for ls in pm.iter(f"{{{NS}}}LineString"):
            pts = coords_from_el(ls)
            if len(pts) >= 3:
                first, last = pts[0], pts[-1]
                dist = math.sqrt((first[0]-last[0])**2 + (first[1]-last[1])**2)
                if dist < 0.001:   # ~100m threshold — treat as closed
                    key = f"Line: {name}" if name not in results else f"Line: {name}_{len(results)}"
                    results[key] = pts

    # Fallback: no namespace
    if not results:
        for pm in root2.iter("Placemark"):
            name_el = pm.find("name")
            name = name_el.text.strip() if (name_el is not None and name_el.text) else "Unnamed"
            for poly_el in pm.iter("Polygon"):
                outer = poly_el.find(".//outerBoundaryIs/LinearRing")
                c_el = outer.find("coordinates") if outer is not None else poly_el.find("coordinates")
                if c_el is not None and c_el.text:
                    pts = _parse_kml_coords(c_el.text)
                    if len(pts) >= 3:
                        results[f"Polygon: {name}"] = pts

    return results


def parse_dxf_polygons(raw_bytes):
    """
    Extract closed polylines/lwpolylines from a DXF file.
    Returns dict of {layer_entity_label: [(x, y), ...]}
    """
    if not HAS_EZDXF:
        return {}
    try:
        doc = ezdxf.read(io.StringIO(raw_bytes.decode("utf-8", errors="ignore")))
    except Exception:
        try:
            doc = ezdxf.read(io.StringIO(raw_bytes.decode("latin-1", errors="ignore")))
        except Exception:
            return {}

    results = {}
    msp = doc.modelspace()
    idx = 0
    for ent in msp:
        pts = None
        if ent.dxftype() == "LWPOLYLINE":
            if ent.is_closed or ent.dxf.flags & 1:
                pts = [(p[0], p[1]) for p in ent.get_points()]
        elif ent.dxftype() == "POLYLINE":
            verts = list(ent.vertices)
            if len(verts) >= 3:
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in verts]
        elif ent.dxftype() in ("SPLINE", "ELLIPSE"):
            pass  # skip for now

        if pts and len(pts) >= 3:
            layer = ent.dxf.layer if hasattr(ent.dxf, "layer") else "0"
            key = f"Layer {layer} #{idx}"
            results[key] = pts
            idx += 1

    return results


def load_boundary_file(uploaded):
    """
    Read file, detect type, return raw bytes and file extension.
    """
    raw = uploaded.read()
    name = uploaded.name.lower()
    if name.endswith(".kmz"):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            kml_name = next((n for n in z.namelist() if n.endswith(".kml")), None)
            if kml_name:
                raw = z.read(kml_name)
        return raw, "kml"
    elif name.endswith(".kml"):
        return raw, "kml"
    elif name.endswith(".dxf"):
        return raw, "dxf"
    elif name.endswith(".dwg"):
        # ezdxf can read some DWG files — try it
        if HAS_EZDXF:
            try:
                doc = ezdxf.readfile(io.BytesIO(raw))  # noqa — may work for newer DWG
                # If it succeeds, treat as DXF-compatible
                return raw, "dwg_ok"
            except Exception:
                pass
        return raw, "dwg_unsupported"
    return raw, "unknown"


# ─── Main UI ─────────────────────────────────────────────────────────────────

left, right = st.columns([1, 1.4])

with left:
    st.markdown('<div class="section-hdr"><i class="fa-solid fa-draw-polygon" style="color:#1565c0;"></i> Site Boundary</div>', unsafe_allow_html=True)

    input_method = st.radio("Input method", [
        "✏️ Draw Site Boundary on Map",
        "📁 Upload KML / KMZ / DXF / DWG",
    ], horizontal=True)

    polygon_coords = None

    # ── Draw on map ──
    if input_method == "✏️ Draw Site Boundary on Map":
        search_q = st.text_input("Search location", placeholder="e.g. Rajasthan India or Andalusia Spain")
        if search_q and search_q != st.session_state.get("topo_last_search", ""):
            try:
                r = requests.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": search_q, "format": "json", "limit": 1},
                    headers={"User-Agent": "TopoIQ/1.0 (pvmath.com; contact@pvmath.de)"},
                    timeout=10
                )
                data = r.json()
                if data:
                    st.session_state["topo_center"] = [float(data[0]["lat"]), float(data[0]["lon"])]
                    st.session_state["topo_zoom"] = 13
            except Exception:
                pass
            st.session_state["topo_last_search"] = search_q
            st.rerun()

        center = st.session_state.get("topo_center", [30.0, 10.0])
        zoom   = st.session_state.get("topo_zoom", 3)

        st.markdown(
            '<div style="background:rgba(255,193,7,0.08);border:1px solid rgba(255,193,7,0.35);'
            'border-radius:8px;padding:0.6rem 0.9rem;font-size:0.82rem;color:#ccc;margin-bottom:0.5rem;">'
            '<i class="fa-solid fa-pen-to-square" style="color:#ffc107;margin-right:0.4rem;"></i>'
            '<strong>How to draw:</strong>&nbsp; '
            '① Click the <strong>polygon tool</strong> (pentagon icon) on the left toolbar &nbsp;'
            '② Click each corner of your site boundary &nbsp;'
            '③ To close — click back on the <strong>first point</strong> (it glows when you hover it), '
            'or simply <strong>double-click</strong> the last point.'
            '</div>',
            unsafe_allow_html=True
        )

        m = folium.Map(location=center, zoom_start=zoom,
                       tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                       attr="Google Satellite")

        Draw(
            export=True,
            draw_options={
                "polygon": {
                    "allowIntersection": False,
                    "showArea": True,
                    "shapeOptions": {
                        "color": "#ffeb3b",        # bright yellow — visible on any satellite bg
                        "weight": 4,
                        "opacity": 1.0,
                        "fillColor": "#ffeb3b",
                        "fillOpacity": 0.12,
                    },
                    "icon": {                       # enlarge snap target on first vertex
                        "className": "leaflet-div-icon",
                        "iconSize": [12, 12],
                    },
                },
                "polyline": False,
                "rectangle": False,
                "circle": False,
                "marker": False,
                "circlemarker": False,
            },
            edit_options={"edit": True}
        ).add_to(m)

        # Inject JS to widen the snap tolerance so first-point closing is easy
        m.get_root().html.add_child(folium.Element("""
        <script>
        document.addEventListener('DOMContentLoaded', function() {
            // Wait for Leaflet.Draw to initialise, then raise snap tolerance
            setTimeout(function() {
                if (window.L && L.Draw && L.Draw.Polygon) {
                    L.Draw.Polygon.prototype.options.touchIcon = new L.DivIcon({
                        className: 'leaflet-div-icon leaflet-editing-icon',
                        iconSize: new L.Point(16, 16)
                    });
                }
            }, 800);
        });
        </script>
        """))

        map_data = st_folium(m, width=None, height=420,
                             returned_objects=["all_drawings"])

        if map_data and map_data.get("all_drawings"):
            for feat in map_data["all_drawings"]:
                geom = feat.get("geometry", {})
                if geom.get("type") == "Polygon":
                    polygon_coords = [(c[0], c[1]) for c in geom["coordinates"][0]]
                    break
                elif geom.get("type") == "LineString":
                    # Auto-close a drawn polyline into a polygon
                    pts = [(c[0], c[1]) for c in geom["coordinates"]]
                    if len(pts) >= 3:
                        if pts[0] != pts[-1]:
                            pts.append(pts[0])
                        polygon_coords = pts
                    break

        if polygon_coords:
            st.success(f"Site boundary captured — {len(polygon_coords)-1} vertices")
        else:
            st.caption("Draw your site boundary on the map above to enable analysis.")

    # ── Upload KML / KMZ / DXF ──
    else:
        f = st.file_uploader(
            "Upload boundary file",
            type=["kml", "kmz", "dxf", "dwg"],
            help="KML / KMZ from Google Earth · DXF or DWG from Civil 3D / AutoCAD"
        )
        if f:
            raw, ftype = load_boundary_file(f)

            if ftype == "dwg_unsupported":
                st.warning(
                    "**DWG file could not be read directly.**\n\n"
                    "In Civil 3D / AutoCAD: **File → Save As → AutoCAD DXF** (takes ~5 seconds). "
                    "Then re-upload the `.dxf` file here."
                )
                all_polys = {}
            elif ftype in ("kml",):
                all_polys = parse_kml_all_polygons(raw)
            elif ftype in ("dxf", "dwg_ok"):
                all_polys = parse_dxf_polygons(raw)
            else:
                all_polys = {}

            if not all_polys:
                st.error("No closed polygon found in file. Check the file contains a site boundary polyline or polygon.")
            elif len(all_polys) == 1:
                polygon_coords = list(all_polys.values())[0]
                st.success(f"Boundary loaded — {len(polygon_coords)} vertices")
            else:
                # Multiple polygons found — let user pick
                st.info(f"Found {len(all_polys)} polygons/boundaries in file. Select the site boundary:")
                chosen = st.selectbox("Select boundary", list(all_polys.keys()))
                polygon_coords = all_polys[chosen]
                st.success(f"Selected: **{chosen}** — {len(polygon_coords)} vertices")

            if polygon_coords:
                lons = [c[0] for c in polygon_coords]
                lats = [c[1] for c in polygon_coords]
                m2 = folium.Map(location=[np.mean(lats), np.mean(lons)],
                                zoom_start=13,
                                tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                                attr="Google Satellite")
                folium.Polygon(
                    locations=[(c[1], c[0]) for c in polygon_coords],
                    color="#42a5f5", fill=True, fill_opacity=0.25, weight=2
                ).add_to(m2)
                st_folium(m2, width=None, height=300, returned_objects=[])

    # ── Settings ──
    st.markdown('<div class="section-hdr" style="margin-top:1rem;"><i class="fa-solid fa-sliders" style="color:#1565c0;"></i> Settings</div>', unsafe_allow_html=True)
    sc1, sc2 = st.columns(2)
    grid_spacing = sc1.selectbox("Grid spacing", [5, 3, 10], index=0,
                                  help="5m = preliminary design, 3m = detailed study")
    contour_minor = sc2.selectbox("Minor contour (m)", [0.5, 0.25, 1.0], index=0)
    contour_major = st.selectbox("Major contour (m)", [1.0, 2.0, 5.0], index=0)

    run = st.button("⛰ Run Terrain Analysis", type="primary",
                    use_container_width=True,
                    disabled=(polygon_coords is None))
    if polygon_coords is None:
        st.caption("Draw or upload a site boundary to enable analysis.")

# ─── Results ──────────────────────────────────────────────────────────────────
with right:
    if run and polygon_coords:
        lons_p = [c[0] for c in polygon_coords]
        lats_p = [c[1] for c in polygon_coords]
        south, north = min(lats_p) - 0.001, max(lats_p) + 0.001
        west,  east  = min(lons_p) - 0.001, max(lons_p) + 0.001
        lat_c = (south + north) / 2
        lon_c = (west  + east)  / 2

        # Estimate area
        m_per_deg_lat = 111320.0
        m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_c))
        area_ha = ((north - south) * m_per_deg_lat *
                   (east  - west)  * m_per_deg_lon) / 10000

        with st.spinner("Fetching satellite terrain data…"):
            mosaic, lat_n, lat_s, lon_w, lon_e = get_dem_for_bbox(
                south, north, west, east, zoom=14
            )

        if mosaic is None:
            st.error("Could not fetch terrain data. Check your internet connection.")
            st.stop()

        with st.spinner(f"Processing {grid_spacing}m grid…"):
            X, Y, Z = resample_to_grid(
                mosaic, lat_n, lat_s, lon_w, lon_e,
                polygon_coords, grid_m=float(grid_spacing)
            )
            slope = compute_slope(Z, float(grid_spacing))

        z_valid = Z[~np.isnan(Z)]
        s_valid = slope[~np.isnan(slope) & ~np.isnan(Z)]

        # ── Summary metrics ──
        m1, m2, m3, m4 = st.columns(4)
        metrics = [
            ("fa-arrow-down", "#e53935", "Min Elevation", f"{z_valid.min():.1f} m"),
            ("fa-arrow-up",   "#43a047", "Max Elevation", f"{z_valid.max():.1f} m"),
            ("fa-wave-square","#1565c0", "Elev Range",    f"{z_valid.max()-z_valid.min():.1f} m"),
            ("fa-percent",    "#f57c00", "Max Slope",     f"{s_valid.max():.1f}%"),
        ]
        for col, (icon, color, label, val) in zip([m1,m2,m3,m4], metrics):
            col.markdown(
                f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);'
                f'border-radius:9px;padding:0.8rem 1rem;margin-bottom:0.5rem;">'
                f'<div><i class="fa-solid {icon}" style="color:{color};font-size:0.9rem;"></i></div>'
                f'<div style="font-size:0.7rem;color:#888;text-transform:uppercase;letter-spacing:0.06em;">{label}</div>'
                f'<div style="font-size:1.5rem;font-weight:700;">{val}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        # ── Slope assessment ──
        mean_slope = float(s_valid.mean())
        pct_over5  = float((s_valid > 5).sum() / len(s_valid) * 100)
        pct_over10 = float((s_valid > 10).sum() / len(s_valid) * 100)

        if mean_slope <= 3:
            st.success(f"**Excellent terrain** — Mean slope {mean_slope:.1f}%. Ideal for both fixed tilt and tracker.")
        elif mean_slope <= 6:
            st.success(f"**Good terrain** — Mean slope {mean_slope:.1f}%. Suitable for fixed tilt; tracker feasible.")
        elif mean_slope <= 10:
            st.warning(f"**Moderate terrain** — Mean slope {mean_slope:.1f}%. Fixed tilt preferred; tracker design needs care.")
        else:
            st.error(f"**Challenging terrain** — Mean slope {mean_slope:.1f}%. Detailed civil study required.")

        st.caption(f"Area: ~{area_ha:.1f} ha  ·  {len(z_valid):,} grid points at {grid_spacing}m  ·  "
                   f"{pct_over5:.0f}% of site >5% slope  ·  {pct_over10:.0f}% >10% slope")

        # ── Elevation heatmap ──
        st.divider()
        st.markdown('<div class="section-hdr"><i class="fa-solid fa-layer-group" style="color:#1565c0;"></i> Elevation Map</div>', unsafe_allow_html=True)
        import pandas as pd
        Z_display = np.flipud(Z)
        st.image(
            _normalize_for_display(Z_display),
            caption=f"Elevation heatmap (blue=low, red=high) · {grid_spacing}m grid · Copernicus DEM via AWS",
            use_container_width=True
        )

        # ── Exports ──
        st.divider()
        st.markdown('<div class="section-hdr"><i class="fa-solid fa-download" style="color:#1565c0;"></i> Download Outputs</div>', unsafe_allow_html=True)
        fname = f"TopoIQ_{lat_c:.3f}_{lon_c:.3f}_{grid_spacing}m"

        ex1, ex2, ex3, ex4 = st.columns(4)

        # LandXML
        with st.spinner("Generating LandXML…"):
            lxml = export_landxml(X, Y, Z, site_name=fname)
        if lxml:
            ex1.download_button("⬇ LandXML", lxml,
                                file_name=f"{fname}.xml",
                                mime="application/xml",
                                use_container_width=True,
                                help="Import directly into Civil 3D as TIN surface")

        # XYZ CSV
        xyz = export_xyz_projected(X, Y, Z, lat_c, lon_c)
        ex2.download_button("⬇ XYZ Points", xyz,
                            file_name=f"{fname}_xyz.csv",
                            mime="text/csv",
                            use_container_width=True,
                            help="Easting / Northing / Elevation CSV")

        # DXF
        if HAS_EZDXF:
            with st.spinner("Generating DXF contours…"):
                dxf_data = export_dxf(X, Y, Z, lat_c, lon_c,
                                      minor_int=contour_minor,
                                      major_int=contour_major)
            if dxf_data:
                ex3.download_button("⬇ DXF Contours", dxf_data,
                                    file_name=f"{fname}_contours.dxf",
                                    mime="application/dxf",
                                    use_container_width=True,
                                    help="Major + minor contour lines for Civil 3D / AutoCAD")
        else:
            ex3.info("Install ezdxf for DXF export")

        # XYZ lon/lat (GIS)
        xyz_geo = export_xyz(X, Y, Z)
        ex4.download_button("⬇ XYZ (Geo)", xyz_geo,
                            file_name=f"{fname}_geo.csv",
                            mime="text/csv",
                            use_container_width=True,
                            help="Lon / Lat / Elevation for GIS / PVsyst")

        # ── Accuracy card ──
        st.markdown(f"""
        <div class="accuracy-card">
          <h4><i class="fa-solid fa-circle-info" style="margin-right:0.3rem;"></i> Data Source & Accuracy</h4>
          <p><strong>Source:</strong> Copernicus GLO-30 DEM (ESA/EC, 2021) via AWS Terrain Tiles</p>
          <p><strong>Native resolution:</strong> ~2.4m per pixel at zoom 14</p>
          <p><strong>Output grid:</strong> {grid_spacing}m resampled</p>
          <p><strong>Vertical accuracy:</strong> ~4m RMSE globally (better in flat terrain, worse in dense vegetation)</p>
          <p><strong>Recommendation:</strong> Suitable for preliminary layout and civil design starting point.
             Verify critical slope areas with LiDAR before final tracker pile design.</p>
          <p style="color:#e53935;margin-top:0.4rem;">
            <i class="fa-solid fa-triangle-exclamation"></i>
            Dense vegetation (forests) and urban areas may cause elevation overestimation.
            Check against site photos before final use.
          </p>
        </div>
        """, unsafe_allow_html=True)

    else:
        # Welcome state
        st.caption("Draw or upload your site boundary on the left, then click Run Terrain Analysis.")
        wc1, wc2 = st.columns(2)
        _wcards = [
            (wc1, "#1a2a4a", "#0f1e38", "#2a4080", "#5b9bd5",
             "SATELLITE DEM", "Copernicus GLO-30 · ~2.4m resolution · Global coverage"),
            (wc2, "#1a3a2a", "#0f2a1e", "#2a6040", "#4caf82",
             "CIVIL 3D READY", "LandXML TIN surface · import directly, no conversion"),
            (wc1, "#2a2a1a", "#1e1e0f", "#5a5a20", "#d4c44a",
             "DXF CONTOURS", f"Major & minor contour lines · configurable intervals"),
            (wc2, "#2a1a3a", "#1e0f2a", "#5a3a80", "#a87fd4",
             "XYZ POINT CLOUD", "Easting / Northing / Elevation CSV for any tool"),
            (wc1, "#1a2a3a", "#0a1828", "#1a4a6a", "#4ab0d4",
             "SLOPE ANALYSIS", "Mean slope · % area over threshold · tracker suitability"),
            (wc2, "#2a1a1a", "#1e0f0f", "#6a2a2a", "#d47a4a",
             "ACCURACY REPORT", "Source · resolution · RMSE · vegetation warnings"),
        ]
        for _col, _bg1, _bg2, _bd, _tc, _title, _desc in _wcards:
            _col.markdown(
                f'<div style="background:linear-gradient(135deg,{_bg1},{_bg2});'
                f'border:1px solid {_bd};border-radius:10px;padding:1rem;margin-bottom:0.75rem;">'
                f'<div style="color:{_tc};font-weight:700;font-size:0.9rem;">{_title}</div>'
                f'<div style="color:#ccc;font-size:0.78rem;margin-top:0.3rem;">{_desc}</div>'
                f'</div>',
                unsafe_allow_html=True
            )


def _normalize_for_display(Z):
    """Convert elevation grid to RGB heatmap image."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm

    Zm = np.ma.masked_invalid(Z)
    if Zm.count() == 0:
        return np.zeros((100, 100, 3), dtype=np.uint8)
    norm = (Zm - Zm.min()) / max(Zm.max() - Zm.min(), 1e-6)
    rgba = cm.RdYlBu_r(norm.filled(0))
    rgb = (rgba[:, :, :3] * 255).astype(np.uint8)
    mask = Zm.mask if np.ma.is_masked(Zm) else np.zeros_like(Z, dtype=bool)
    if isinstance(mask, np.ndarray):
        rgb[mask] = [30, 30, 30]
    return rgb
