"""Customer resources — Pro-gated downloads (public-safe assets only)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
PUBLIC_MANUAL_PATH = ROOT / "docs" / "PVMath_Engineering_Reference_Manual_PUBLIC.docx"
PUBLIC_MANUAL_FILENAME = "PVMath_Engineering_Reference_Manual_PUBLIC.docx"
KNOWLEDGE_CENTRE_URL = "https://pvmath.com/guides/"


@st.cache_data(show_spinner=False)
def load_public_manual_bytes() -> bytes | None:
    """Read the redacted public Word manual from disk."""
    if not PUBLIC_MANUAL_PATH.is_file():
        return None
    return PUBLIC_MANUAL_PATH.read_bytes()
