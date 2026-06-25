#!/usr/bin/env python3
"""Scaffold PVMath Founder Handbook folders and sync invoice template."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDBOOK = ROOT / "PVMath"
SRC_INVOICE = ROOT / "docs" / "PVMath_Proforma_Invoice_Template.docx"
DST_INVOICE = HANDBOOK / "Finance" / "Invoice Templates.docx"

FOLDERS = [
    "Company Formation",
    "Finance",
    "Legal",
    "Accounting",
    "Taxes",
]


def main() -> None:
    for name in FOLDERS:
        (HANDBOOK / name).mkdir(parents=True, exist_ok=True)

    if SRC_INVOICE.exists():
        shutil.copy2(SRC_INVOICE, DST_INVOICE)
        print(f"Synced {DST_INVOICE.relative_to(ROOT)}")
    else:
        print(f"Warning: missing {SRC_INVOICE}")

    cf = HANDBOOK / "Company Formation"
    for pdf_name in ("Gewerbeanmeldung.pdf", "Tax Registration.pdf"):
        p = cf / pdf_name
        if not p.exists():
            print(f"Note: add official PDF → {p.relative_to(ROOT)}")

    print(f"Handbook root: {HANDBOOK.relative_to(ROOT)}/README.md")


if __name__ == "__main__":
    main()
