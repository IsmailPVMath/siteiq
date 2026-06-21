"""
pages/overview.py — PVMath account Overview
A stats landing page: how many projects you've saved and how many analyses
you've run across modules. "My Projects" remains the detailed project list —
this page is the at-a-glance summary + quick actions, so the two no longer
show the same thing.
"""

import streamlit as st
from concurrent.futures import ThreadPoolExecutor
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
from pvmath_auth import (
    list_projects, get_usage, get_plan, can_download_engineering_manual,
    plan_label, UPGRADE_CONTACT, usage_status, engineering_manual_caption,
)
from pvmath_resources import load_public_manual_bytes, PUBLIC_MANUAL_FILENAME, KNOWLEDGE_CENTRE_URL
from pvmath_session import clear_module_project_state
from pvmath_styles import inject_styles

_uid   = st.session_state.get("pvm_user_id", "")
_email = st.session_state.get("pvm_email", "")

inject_styles(accent="#1d9e52", accent_light="#e2ede2")

st.markdown("""
<style>
.ov-stat-card {
    background:#fff; border:1.5px solid #d4e8d4; border-radius:12px;
    padding:1.3rem 1.4rem; text-align:center;
    box-shadow:0 1px 6px rgba(0,0,0,0.05);
}
.ov-stat-num { font-size:2.1rem; font-weight:800; color:#1a2e1a; line-height:1.1; }
.ov-stat-lbl { font-size:0.82rem; color:#5a7a5a; margin-top:0.3rem; font-weight:600; }
.ov-module-row { font-size:0.85rem; color:#5a7a5a; margin-top:0.5rem; }
.ov-module-row b { color:#1a2e1a; }
/* Smaller, tighter action buttons — scoped to the Overview action row only
   (via :has() on a marker div) so this doesn't bleed into button styling on
   other pages, since Streamlit's hidden-nav SPA navigation can keep injected
   CSS alive across page switches within the same session. */
div[data-testid="stVerticalBlock"]:has(div.ov-actions-anchor) div[data-testid="stButton"] > button {
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    padding: 0.35rem 0.8rem !important;
    border-radius: 8px !important;
    height: auto !important;
    min-height: 0 !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div style="padding:1.5rem 0 0.5rem 0;border-bottom:2px solid #e8f5ee;margin-bottom:1.5rem;">
  <div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;margin-bottom:0.35rem;">
    <div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;
                letter-spacing:0.12em;color:#1d9e52;">Overview</div>
    <span style="display:inline-flex;align-items:center;gap:0.3rem;background:#e8f5ee;border:1px solid #b8ddc8;
                 color:#145f34;font-size:0.62rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;
                 padding:0.22rem 0.5rem;border-radius:100px;">Early Access</span>
  </div>
  <h1 style="font-size:2rem;font-weight:800;color:#1a2e1a;margin:0 0 0.3rem 0;">Welcome back</h1>
  <p style="color:#5a7a5a;font-size:1rem;margin:0;">{_email}</p>
</div>
""", unsafe_allow_html=True)

if not _uid:
    st.info("Sign in to see your account overview.")
    st.stop()

with st.spinner("Loading your stats…"):
    # The 4 calls below are independent reads against Supabase — running them
    # in parallel instead of one-after-another is what was causing the
    # dashboard to feel slow (4x sequential network round-trips collapsed
    # into 1).
    #
    # BUT: list_projects()/get_usage() call _db_hdr(), which reads
    # st.session_state["pvm_access_token"] to authenticate the request as
    # the signed-in user. Streamlit's session state is only visible from the
    # thread that's running the current script — bare ThreadPoolExecutor
    # worker threads have no script-run context attached, so inside the
    # worker, st.session_state silently behaves as if it were a *different*,
    # empty session. _db_hdr() then falls back to the bare anon/service key
    # instead of the user's token, the RLS-protected query comes back empty,
    # and get_usage()/list_projects() swallow that as "0"/"[]" with no error
    # surfaced anywhere. That's why this page showed 0/0 while My Projects —
    # which calls list_projects() directly on the main thread, no
    # ThreadPoolExecutor — correctly showed the real count. Fix: attach this
    # script's run context to each worker thread before it does any
    # st.session_state-touching work.
    _ctx = get_script_run_ctx()

    def _with_ctx(fn, *args):
        add_script_run_ctx(ctx=_ctx)
        return fn(*args)

    with ThreadPoolExecutor(max_workers=4) as _ex:
        _f_rows    = _ex.submit(_with_ctx, list_projects, _uid)
        _f_siteiq  = _ex.submit(_with_ctx, get_usage, _uid, "siteiq")
        _f_topoiq  = _ex.submit(_with_ctx, get_usage, _uid, "topoiq")
        _f_yieldiq = _ex.submit(_with_ctx, get_usage, _uid, "yieldiq")
        _rows      = _f_rows.result()
        _siteiq_n  = _f_siteiq.result()
        _topoiq_n  = _f_topoiq.result()
        _yieldiq_n = _f_yieldiq.result()

_project_count  = len(_rows)
_analysis_total = _siteiq_n + _topoiq_n + _yieldiq_n
_usage = usage_status(_uid)
_plan = _usage["plan"]
_limit_mode = _usage["mode"]
_limit = _usage["limit"]

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"""
    <div class="ov-stat-card">
      <div class="ov-stat-num">{_project_count}</div>
      <div class="ov-stat-lbl">Projects saved</div>
    </div>
    """, unsafe_allow_html=True)
with c2:
    if _limit_mode == "pooled" and _limit is not None and _usage["remaining_total"] is not None:
        _rem = _usage["remaining_total"]
        _used_pooled = _analysis_total
        st.markdown(f"""
        <div class="ov-stat-card">
          <div class="ov-stat-num">{_used_pooled} / {_limit}</div>
          <div class="ov-stat-lbl">Analyses used this month ({plan_label(_plan)} pool)</div>
          <div class="ov-module-row"><b>{_rem}</b> remaining &nbsp;·&nbsp; shared across all modules</div>
          <div class="ov-module-row">
            <b>{_siteiq_n}</b> SiteIQ &nbsp;·&nbsp; <b>{_topoiq_n}</b> TopoIQ &nbsp;·&nbsp; <b>{_yieldiq_n}</b> YieldIQ
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="ov-stat-card">
          <div class="ov-stat-num">{_analysis_total}</div>
          <div class="ov-stat-lbl">Analyses run (all modules)</div>
          <div class="ov-module-row">
            <b>{_siteiq_n}</b> SiteIQ &nbsp;·&nbsp; <b>{_topoiq_n}</b> TopoIQ &nbsp;·&nbsp; <b>{_yieldiq_n}</b> YieldIQ
          </div>
        </div>
        """, unsafe_allow_html=True)

if _limit_mode == "pooled" and _usage.get("at_limit"):
    st.warning(
        f"Monthly limit reached ({_limit} analyses on {plan_label(_plan)}). "
        f"Contact us to upgrade or wait until next month."
    )
elif _limit_mode == "per_module" and _limit is not None and _usage.get("remaining_per_app"):
    _rem_apps = _usage["remaining_per_app"]
    _low = min(_rem_apps.values())
    if _low <= 1:
        st.caption(
            f"Per-module limits ({_limit}/module on {plan_label(_plan)}): "
            f"SiteIQ {_rem_apps['siteiq']} left · TopoIQ {_rem_apps['topoiq']} left · "
            f"YieldIQ {_rem_apps['yieldiq']} left."
        )

st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)

st.markdown('<div class="ov-actions-anchor"></div>', unsafe_allow_html=True)
_a1, _a2, _a3 = st.columns(3)
with _a1:
    if st.button("+ New Project", use_container_width=True, type="primary"):
        clear_module_project_state(st.session_state, blank=True)
        st.switch_page("pages/project.py")
with _a2:
    if st.button("View My Projects", use_container_width=True):
        st.switch_page("pages/my_projects.py")
with _a3:
    if _project_count and st.button("Continue last project", use_container_width=True):
        st.switch_page("pages/project.py")

if _project_count == 0:
    st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
    st.caption("No projects yet — use **+ New Project** above to set up your first site.")

st.markdown("<div style='margin-top:2rem;border-top:1px solid #e8f5ee;padding-top:1.5rem;'></div>", unsafe_allow_html=True)
st.markdown("#### Resources")
st.caption("Engineering concepts for customers — proprietary scoring stays internal.")

_kc_col, _manual_col = st.columns(2)
with _kc_col:
    st.markdown(
        f"**Knowledge Centre** — free guides for all signed-in users  \n"
        f"[Open guides ↗]({KNOWLEDGE_CENTRE_URL})"
    )
    st.caption("GLO-30, cross-row slope, CAD exports, screening vs survey.")

with _manual_col:
    if can_download_engineering_manual(_uid):
        _manual = load_public_manual_bytes()
        if _manual:
            st.download_button(
                "⬇ Engineering Reference Manual (Word)",
                _manual,
                file_name=PUBLIC_MANUAL_FILENAME,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                help="Public Edition — concepts and definitions; formulas redacted.",
            )
            st.caption(engineering_manual_caption(_uid))
        else:
            st.warning("Manual file unavailable — contact contact@pvmath.com.")
    else:
        st.markdown(
            "**Engineering Reference Manual (Word)**  \n"
            "Public Edition — Professional plan and above."
        )
        st.link_button("Contact us to upgrade →", UPGRADE_CONTACT, use_container_width=True)
        st.caption("Free tier: use the Knowledge Centre for public guides.")
