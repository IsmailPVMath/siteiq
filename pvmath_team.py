"""
PVMath — Developer team invites (UI + Supabase RPC wrappers).

Requires supabase_migration_team_invites.sql applied in Supabase.
"""

from __future__ import annotations

import streamlit as st
import requests as _req

from pvmath_auth import (
    _sb_url,
    _db_hdr,
    _parse_err,
    get_plan,
    get_team_id,
    seat_limit,
    team_occupied_seats,
    can_add_seat,
    is_admin,
)

APP_URL = "https://siteiq.pvmath.com"


def _rpc(fn: str, payload: dict | None = None) -> dict:
    try:
        r = _req.post(
            f"{_sb_url()}/rest/v1/rpc/{fn}",
            json=payload or {},
            headers=_db_hdr(),
            timeout=15,
        )
        if r.status_code >= 400:
            return {"success": False, "error": _parse_err(r)}
        if not r.text or r.text.strip() in ("", "null"):
            return {"success": True}
        data = r.json()
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


def is_team_owner(user_id: str) -> bool:
    return get_plan(user_id) == "developer" and get_team_id(user_id) is None


def is_team_member(user_id: str) -> bool:
    return get_plan(user_id) == "developer" and get_team_id(user_id) is not None


def team_owner_id(user_id: str) -> str | None:
    if get_plan(user_id) != "developer":
        return None
    tid = get_team_id(user_id)
    return tid or user_id


def create_team_invite(email: str) -> dict:
    return _rpc("create_team_invite", {"p_email": email.strip()})


def accept_team_invite(token: str) -> dict:
    return _rpc("accept_team_invite", {"p_token": token.strip()})


def list_team_roster() -> list[dict]:
    res = _rpc("list_team_roster")
    if not res.get("success"):
        return []
    data = res.get("data")
    return data if isinstance(data, list) else []


def list_team_invites() -> list[dict]:
    res = _rpc("list_team_invites")
    if not res.get("success"):
        return []
    data = res.get("data")
    return data if isinstance(data, list) else []


def revoke_team_invite(invite_id: str) -> dict:
    return _rpc("revoke_team_invite", {"p_invite_id": invite_id})


def remove_team_member(member_id: str) -> dict:
    return _rpc("remove_team_member", {"p_member_id": member_id})


def leave_team() -> dict:
    return _rpc("leave_team")


def peek_team_invite(token: str) -> dict | None:
    res = _rpc("peek_team_invite", {"p_token": token.strip()})
    if not res.get("success"):
        return None
    data = res.get("data")
    return data if isinstance(data, dict) else None


def invite_link(token: str) -> str:
    return f"{APP_URL}/?team_invite={token}"


def render_team_invite_banner(user_id: str, email: str) -> None:
    """Show accept banner when ?team_invite= is in the URL."""
    token = (st.query_params.get("team_invite") or "").strip()
    if not token or not user_id:
        return

    info = peek_team_invite(token)
    if not info:
        st.markdown(
            '<div style="font-size:0.78rem;color:#fca5a5;padding:0.35rem 0;">'
            "Team invite link is invalid or expired.</div>",
            unsafe_allow_html=True,
        )
        return

    if info.get("valid") is False:
        st.markdown(
            f'<div style="font-size:0.78rem;color:#fcd34d;padding:0.35rem 0;">'
            f"This invite is for <b>{info.get('invitee_email', '')}</b>. "
            f"You are signed in as {email}.</div>",
            unsafe_allow_html=True,
        )
        return

    if is_team_owner(user_id) or is_team_member(user_id):
        st.markdown(
            '<div style="font-size:0.78rem;color:#fcd34d;padding:0.35rem 0;">'
            "You are already on a Developer team.</div>",
            unsafe_allow_html=True,
        )
        return

    owner = info.get("owner_email", "a team")
    st.markdown(
        f'<div style="font-size:0.78rem;color:#b8f5c8;line-height:1.45;padding:0.2rem 0 0.4rem;">'
        f"<b>Team invite</b> — join {owner}'s Developer workspace "
        f'(250 analyses/month shared pool).</div>',
        unsafe_allow_html=True,
    )
    if st.button("Accept invite", key="pvm_accept_team_invite", use_container_width=True):
        res = accept_team_invite(token)
        if res.get("success"):
            try:
                del st.query_params["team_invite"]
            except Exception:
                pass
            st.success("Joined the team — refresh if limits don't update.")
            st.rerun()
        else:
            st.error(res.get("error", "Could not accept invite."))


def render_team_settings(user_id: str, email: str) -> None:
    """Developer plan team panel — owner invites / member leave."""
    plan = get_plan(user_id)
    if plan != "developer":
        return

    st.markdown(
        '<div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;'
        'letter-spacing:0.08em;color:#7fd99a;margin:0.75rem 0 0.35rem;">Team</div>',
        unsafe_allow_html=True,
    )

    owner_id = team_owner_id(user_id)
    if not owner_id:
        return

    limit = seat_limit("developer") or 5
    occupied = team_occupied_seats(owner_id)
    roster = list_team_roster()

    st.markdown(
        f'<div style="font-size:0.78rem;color:#d1e7d1;line-height:1.45;margin-bottom:0.45rem;">'
        f"<b>{occupied} / {limit}</b> seats · shared monthly analysis pool</div>",
        unsafe_allow_html=True,
    )

    if roster:
        for m in roster:
            role = m.get("role", "member")
            label = m.get("display_name") or m.get("email") or "User"
            em = m.get("email") or ""
            mid = m.get("id") or ""
            suffix = " (you)" if mid == user_id else ""
            role_tag = " · owner" if role == "owner" else ""
            st.markdown(
                f'<div style="font-size:0.76rem;color:#e6f5e6;padding:0.15rem 0;">'
                f"• {label}{suffix}<br>"
                f'<span style="color:#8ab88a;font-size:0.7rem;">{em}{role_tag}</span></div>',
                unsafe_allow_html=True,
            )
            if is_team_owner(user_id) and role == "member" and mid:
                if st.button("Remove", key=f"pvm_rm_member_{mid}", use_container_width=True):
                    res = remove_team_member(mid)
                    if res.get("success"):
                        st.success("Member removed.")
                        st.rerun()
                    else:
                        st.error(res.get("error", "Could not remove member."))

    if is_team_member(user_id):
        st.caption("Usage counts against your team's shared pool.")
        if st.button("Leave team", key="pvm_leave_team", use_container_width=True):
            res = leave_team()
            if res.get("success"):
                st.success("You left the team.")
                st.rerun()
            else:
                st.error(res.get("error", "Could not leave team."))
        return

    if not is_team_owner(user_id):
        return

    pending = list_team_invites()
    if pending:
        st.markdown(
            '<div style="font-size:0.72rem;color:#8ab88a;margin:0.5rem 0 0.2rem;">Pending invites</div>',
            unsafe_allow_html=True,
        )
        for inv in pending:
            inv_email = inv.get("invitee_email", "")
            inv_id = inv.get("id", "")
            inv_token = inv.get("token", "")
            st.markdown(
                f'<div style="font-size:0.74rem;color:#d1e7d1;">{inv_email}</div>',
                unsafe_allow_html=True,
            )
            if inv_token:
                st.text_input(
                    "Invite link",
                    value=invite_link(inv_token),
                    key=f"pvm_inv_link_{inv_id}",
                    disabled=True,
                    label_visibility="collapsed",
                )
            if inv_id and st.button("Revoke", key=f"pvm_revoke_{inv_id}", use_container_width=True):
                res = revoke_team_invite(inv_id)
                if res.get("success"):
                    st.rerun()
                else:
                    st.error(res.get("error", "Could not revoke invite."))

    if not can_add_seat(owner_id, "developer"):
        st.markdown(
            '<div style="font-size:0.76rem;color:#fcd34d;">All seats in use — remove a member to invite someone else.</div>',
            unsafe_allow_html=True,
        )
        return

    with st.form("pvm_team_invite_form", clear_on_submit=True):
        invite_email = st.text_input(
            "Invite by email",
            placeholder="colleague@company.com",
            help="They must sign up with this exact email, then open the invite link.",
        )
        if st.form_submit_button("Send invite", use_container_width=True):
            if not invite_email.strip():
                st.error("Enter an email address.")
            else:
                res = create_team_invite(invite_email)
                if res.get("success"):
                    data = res.get("data") or {}
                    tok = data.get("token", "")
                    st.success("Invite created — copy the link below.")
                    if tok:
                        st.code(invite_link(tok), language=None)
                    st.rerun()
                else:
                    st.error(res.get("error", "Could not create invite."))

    st.caption(
        "Invitee creates a PVMath account with the invited email, opens the link, "
        "and clicks Accept invite."
    )


def render_membership_panel(user_id: str, email: str) -> None:
    """Billing, upgrades, and Developer team seats — plan/usage lives in the sidebar."""
    if not user_id:
        return

    if is_admin(user_id):
        st.markdown(
            '<div style="font-size:0.78rem;color:#8ab88a;line-height:1.45;margin:0.25rem 0 0.5rem;">'
            "Admin preview — unlimited access. Plan limits do not apply.</div>",
            unsafe_allow_html=True,
        )
        return

    plan = get_plan(user_id)

    if plan == "developer":
        render_team_settings(user_id, email)
    elif plan == "free":
        st.markdown(
            '<div style="font-size:0.76rem;color:#8ab88a;line-height:1.45;margin:0.25rem 0;">'
            "Need team access? Developer adds 5 seats and 250 project analyses/month.</div>",
            unsafe_allow_html=True,
        )
