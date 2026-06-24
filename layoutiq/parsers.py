"""Boundary polygon parsers (KML, DXF, pasted coordinates)."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET


def parse_kml(data: bytes):
    """Extract first polygon as list of (lat, lon)."""
    try:
        root = ET.fromstring(data.decode("utf-8", errors="ignore"))
        for elem in root.iter():
            if "coordinates" in elem.tag and elem.text:
                pts = []
                for token in elem.text.strip().split():
                    parts = token.split(",")
                    if len(parts) >= 2:
                        try:
                            pts.append((float(parts[1]), float(parts[0])))
                        except ValueError:
                            pass
                if len(pts) >= 3:
                    return pts
    except Exception:
        pass
    return None


def parse_dxf(data: bytes):
    """Extract first closed LWPOLYLINE. Returns (points, is_local)."""
    try:
        import ezdxf

        doc = ezdxf.read(io.StringIO(data.decode("utf-8", errors="ignore")))
        msp = doc.modelspace()
        for e in msp:
            if e.dxftype() == "LWPOLYLINE":
                pts = [(p[1], p[0]) for p in e.get_points()]
                if len(pts) >= 3:
                    return pts, True
    except Exception:
        pass
    return None, False


def parse_pasted(text: str):
    """Parse pasted lat,lon lines."""
    pts = []
    for line in text.strip().splitlines():
        line = re.sub(r"[;|\t]", ",", line).strip()
        m = re.match(r"^(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)$", line)
        if m:
            pts.append((float(m.group(1)), float(m.group(2))))
    return pts if len(pts) >= 3 else None
