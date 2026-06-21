#!/usr/bin/env python3
"""
Guard against Folium Draw regression (4th fix 2026-06).

Fails if pages call st_folium with all_drawings or combine last_clicked with Draw mode.
Run: python3 scripts/check_folium_draw_regression.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "pages" / "project.py", ROOT / "pages" / "topoiq.py"]

# Direct st_folium(... returned_objects=[... all_drawings ...]) in map pages
BAD_RETURNED = re.compile(
    r"st_folium\s*\([^)]*returned_objects\s*=\s*\[[^\]]*\ball_drawings\b",
    re.DOTALL,
)

# Draw + last_clicked in same returned_objects list (multiline)
BAD_DRAW_CLICK = re.compile(
    r"returned_objects\s*=\s*\[[^\]]*\blast_clicked\b[^\]]*\].*"
    r"(?:Draw|enable_draw|is_full)",
    re.DOTALL | re.IGNORECASE,
)


def main() -> int:
    errors: list[str] = []
    for path in TARGETS:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if BAD_RETURNED.search(text):
            errors.append(f"{path.relative_to(ROOT)}: st_folium uses all_drawings — breaks Draw")
        if "returned_objects=[\"all_drawings\"]" in text.replace(" ", ""):
            errors.append(f"{path.relative_to(ROOT)}: returned_objects includes all_drawings")
        if re.search(
            r'returned_objects=\[[^\]]*"last_clicked"[^\]]*"last_active_drawing"',
            text.replace("\n", " "),
        ) or re.search(
            r'returned_objects=\[[^\]]*"last_active_drawing"[^\]]*"last_clicked"',
            text.replace("\n", " "),
        ):
            errors.append(
                f"{path.relative_to(ROOT)}: do not combine last_clicked with draw returned_objects"
            )
        if "validate_draw_returned_objects" not in text and "st_folium_with_draw" not in text:
            if path.name == "project.py" and "is_full" in text:
                errors.append(
                    f"{path.relative_to(ROOT)}: must use st_folium_with_draw from pvmath_folium_draw"
                )
    if errors:
        print("Folium Draw regression check FAILED:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print("\nSee pvmath_folium_draw.py", file=sys.stderr)
        return 1
    print("Folium Draw regression check OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
