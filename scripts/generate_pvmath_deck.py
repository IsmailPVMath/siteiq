#!/usr/bin/env python3
"""Generate PVMath sales and technical PowerPoint decks."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pvmath_deck.builder import DeckBuilder
from pvmath_deck.decks.sales_15 import build_sales_15
from pvmath_deck.decks.terrainiq_30 import build_terrainiq_30

DEFAULT_OUT = ROOT / "docs" / "decks"

DECKS = {
    "sales-15": ("PVMath_Sales_15min.pptx", build_sales_15),
    "terrainiq-30": ("PVMath_TerrainIQ_30min.pptx", build_terrainiq_30),
}


def generate(
    deck_id: str,
    out_dir: Path,
    presenter: str,
    deck_date: str | None,
) -> Path:
    filename, builder_fn = DECKS[deck_id]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    b = DeckBuilder(presenter=presenter, deck_date=deck_date or date.today().strftime("%d %B %Y"))
    builder_fn(b)
    b.save(str(path))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PVMath .pptx presentation decks")
    parser.add_argument(
        "--deck",
        choices=list(DECKS) + ["all"],
        default="all",
        help="Which deck to build (default: all)",
    )
    parser.add_argument("--presenter", default="Mohammed Ismail Pasha", help="Presenter name on cover")
    parser.add_argument("--date", default=None, help="Deck date string (default: today)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output directory")
    args = parser.parse_args()

    ids = list(DECKS) if args.deck == "all" else [args.deck]
    for deck_id in ids:
        path = generate(deck_id, args.out, args.presenter, args.date)
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
