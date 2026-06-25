"""LayoutIQ — ground-mount row layout + BOM engine."""

from layoutiq.bom import compute_bom
from layoutiq.engine import run_layout

__all__ = ["run_layout", "compute_bom"]

def __getattr__(name: str):
    """Lazy exports so API gate path avoids matplotlib unless needed."""
    if name == "MODULE_PRESETS":
        from layoutiq.presets import MODULE_PRESETS
        return MODULE_PRESETS
    if name == "parse_kml":
        from layoutiq.parsers import parse_kml
        return parse_kml
    if name == "parse_dxf":
        from layoutiq.parsers import parse_dxf
        return parse_dxf
    if name == "parse_pasted":
        from layoutiq.parsers import parse_pasted
        return parse_pasted
    if name == "make_layout_drawing":
        from layoutiq.drawing import make_layout_drawing
        return make_layout_drawing
    if name == "build_pdf":
        from layoutiq.pdf import build_pdf
        return build_pdf
    if name == "load_project_context":
        from layoutiq.project import load_project_context
        return load_project_context
    raise AttributeError(name)
