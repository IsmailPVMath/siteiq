#!/usr/bin/env python3
"""
PVMath Marketing Bot — LinkedIn draft generator (no auto-post).

Usage:
    python3 scripts/pvmath_marketing_bot.py run
    python3 scripts/pvmath_marketing_bot.py init-library
    python3 scripts/pvmath_marketing_bot.py run --date 2026-06-25

Commands:
    run           Generate 5 LinkedIn drafts + update content_calendar.csv
    init-library  Create 100 ideas, 90-day strategy, publishing calendar, templates
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pvmath_marketing.library import init_library, run_drafts  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="PVMath Marketing Bot")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Generate 5 LinkedIn drafts")
    run_p.add_argument("--date", type=str, help="YYYY-MM-DD (default: today)")

    sub.add_parser("init-library", help="Build 100 ideas + 90-day calendar + templates")

    args = parser.parse_args()

    if args.command == "run":
        run_date = date.fromisoformat(args.date) if args.date else date.today()
        paths = run_drafts(run_date)
        print(f"Generated {len(paths)} LinkedIn drafts:")
        for p in paths:
            print(f"  {p.relative_to(ROOT)}")
        print(f"\nCalendar updated: marketing/content_calendar.csv")
        print("Review drafts before publishing. Do not auto-post.")
        return

    if args.command == "init-library":
        outputs = init_library()
        print("Marketing library initialized:")
        for key, path in outputs.items():
            print(f"  {key}: {path.relative_to(ROOT)}")
        print("\nNext: python3 scripts/pvmath_marketing_bot.py run")
        return


if __name__ == "__main__":
    main()
