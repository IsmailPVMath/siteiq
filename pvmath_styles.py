"""
pvmath_styles.py — Shared typography & chrome-removal CSS for all PVMath modules.
Call inject_styles() at the top of every page module.
"""
import streamlit as st

# ─── Badge / Streamlit chrome killer (JS) ────────────────────────────────────
_BADGE_KILLER = """
<script>
(function() {
  function killBadge() {
    document.querySelectorAll('*').forEach(function(el) {
      try {
        var s = window.getComputedStyle(el);
        var cl = el.className ? el.className.toString().toLowerCase() : '';
        if (
          (s.position === 'fixed' && parseInt(s.bottom) >= 0 &&
           parseInt(s.right) >= 0 && el.tagName !== 'BODY') ||
          cl.includes('badge') || cl.includes('viewer')
        ) {
          el.style.setProperty('display', 'none', 'important');
          el.style.setProperty('visibility', 'hidden', 'important');
        }
      } catch(e) {}
    });
  }
  killBadge();
  new MutationObserver(killBadge).observe(
    document.documentElement, {childList:true, subtree:true}
  );
})();
</script>
"""

# ─── Shared base CSS ─────────────────────────────────────────────────────────
_BASE_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap"
      rel="stylesheet">
<style>
/* ── Base ── */
html, body, [class*="css"] {{
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif !important;
    font-size: 16px !important;
    color: #0d1a0d;
}}

/* ── Input labels: near-black, bold ── */
[data-testid="stTextInput"] label,
[data-testid="stNumberInput"] label,
[data-testid="stSelectbox"] label,
[data-testid="stFileUploader"] label,
[data-testid="stSlider"] label,
[data-testid="stTextArea"] label {{
    font-size: 1rem !important;
    font-weight: 700 !important;
    color: #0d1a0d !important;
    letter-spacing: -0.01em !important;
}}

/* ── Input field text ── */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {{
    font-size: 1rem !important;
    color: #0d1a0d !important;
    font-weight: 500 !important;
}}
[data-testid="stSelectbox"] div[data-baseweb="select"] span {{
    font-size: 1rem !important;
    color: #0d1a0d !important;
}}

/* ── Metric values: big, heavy, near-black ── */
[data-testid="stMetricValue"] {{
    font-size: 2rem !important;
    font-weight: 800 !important;
    color: #0d1a0d !important;
    letter-spacing: -0.03em !important;
    line-height: 1.1 !important;
}}

/* ── Metric labels: visible, not grey ── */
[data-testid="stMetric"] label,
[data-testid="stMetricLabel"] {{
    font-size: 0.8rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
    color: {accent} !important;
}}

/* ── Metric delta text ── */
[data-testid="stMetricDelta"] {{
    font-size: 0.88rem !important;
    font-weight: 600 !important;
}}

/* ── Markdown body text: dark, readable ── */
[data-testid="stMarkdown"] p,
[data-testid="stMarkdown"] li {{
    font-size: 1rem !important;
    color: #1a2e1a !important;
    line-height: 1.75 !important;
}}
[data-testid="stMarkdown"] strong {{
    font-weight: 700 !important;
    color: #0d1a0d !important;
}}

/* ── Radio + checkbox labels ── */
[data-testid="stRadio"] label span {{
    font-size: 1rem !important;
    font-weight: 500 !important;
    color: #0d1a0d !important;
}}
[data-testid="stCheckbox"] label span {{
    font-size: 1rem !important;
    color: #0d1a0d !important;
}}

/* ── Expander headers ── */
[data-testid="stExpander"] summary p {{
    font-size: 1rem !important;
    font-weight: 700 !important;
    color: #0d1a0d !important;
}}

/* ── Alert / info / warning / error text ── */
[data-testid="stAlert"] p {{
    font-size: 0.97rem !important;
    font-weight: 500 !important;
    color: #0d1a0d !important;
}}

/* ── Buttons ── */
button[data-testid="stBaseButton-primary"],
button[data-testid="stBaseButton-secondary"] {{
    font-size: 1rem !important;
    font-weight: 700 !important;
    border-radius: 9px !important;
    letter-spacing: -0.01em !important;
}}

/* ── Caption text: readable, not #999 ── */
[data-testid="stCaptionContainer"] p,
small {{
    font-size: 0.88rem !important;
    color: #4a6a4a !important;
    font-weight: 500 !important;
}}

/* ── Tab labels ── */
[data-testid="stTabs"] button p {{
    font-size: 0.97rem !important;
    font-weight: 700 !important;
}}

/* ── Subheader ── */
[data-testid="stMarkdown"] h3 {{
    font-size: 1.15rem !important;
    font-weight: 800 !important;
    color: #0d1a0d !important;
    letter-spacing: -0.02em !important;
}}

/* ── Divider ── */
[data-testid="stDivider"] {{
    border-color: #d4e4d4 !important;
}}

/* ── Form submit button ── */
[data-testid="stFormSubmitButton"] button {{
    font-size: 1rem !important;
    font-weight: 700 !important;
    border-radius: 9px !important;
}}

/* ── Download button ── */
[data-testid="stDownloadButton"] button {{
    font-size: 1rem !important;
    font-weight: 700 !important;
    border-radius: 9px !important;
}}

/* ── Shared result card classes ── */
.pvm-result-label {{
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: {accent};
    margin-bottom: 0.15rem;
}}
.pvm-result-value {{
    font-size: 1.6rem;
    font-weight: 800;
    color: #0d1a0d;
    line-height: 1.15;
    letter-spacing: -0.02em;
}}
.pvm-result-unit {{
    font-size: 0.9rem;
    font-weight: 500;
    color: #3a5a3a;
    margin-left: 0.2rem;
}}

/* ── Shared section header class ── */
.pvm-section-hdr {{
    font-size: 0.72rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: {accent};
    display: flex; align-items: center; gap: 0.5rem;
    margin: 1.6rem 0 0.85rem 0;
    padding-bottom: 0.5rem;
    border-bottom: 2.5px solid {accent_light};
}}

/* ── Hide Streamlit chrome ── */
footer {{ visibility: hidden !important; height: 0 !important; }}
#MainMenu {{ visibility: hidden !important; }}
header {{ visibility: hidden !important; }}
[data-testid="stToolbar"]      {{ display: none !important; }}
[data-testid="stDeployButton"] {{ display: none !important; }}
[data-testid="stStatusWidget"] {{ display: none !important; }}
[data-testid="stDecoration"]   {{ display: none !important; }}
#stDecoration                  {{ display: none !important; }}
[class*="viewerBadge"]         {{ display: none !important; }}
[class*="StatusWidget"]        {{ display: none !important; }}
[class*="deployButton"]        {{ display: none !important; }}
[class*="styles_viewerBadge"]  {{ display: none !important; }}
iframe[title="streamlitApp"]   {{ display: none !important; }}
[style*="position: fixed"][style*="bottom"][style*="right"],
[style*="position:fixed"][style*="bottom"][style*="right"] {{ display: none !important; }}
</style>
"""


def inject_styles(accent: str = "#1d9e52", accent_light: str = "#e2ede2"):
    """
    Inject shared PVMath typography + chrome-removal CSS.
    Call once at the top of every page module, before any st.markdown / st.write.

    Args:
        accent:       Module accent hex (green / blue / amber).
        accent_light: Light tint of the accent used for borders / backgrounds.
    """
    css = _BASE_CSS.format(accent=accent, accent_light=accent_light)
    full_html = css + _BADGE_KILLER
    # st.html() (Streamlit 1.31+) reliably injects raw HTML without markdown rendering.
    # Falls back to st.markdown() for older versions.
    if hasattr(st, "html"):
        st.html(full_html)
    else:
        st.markdown(full_html, unsafe_allow_html=True)
