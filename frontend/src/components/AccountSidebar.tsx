import { FormEvent, useState } from "react";
import { changePassword } from "../lib/api";
import type { MeResponse } from "../types/gate";

const UPGRADE_MAIL =
  "mailto:contact@pvmath.com?subject=PVMath%20%E2%80%94%20Billing%20or%20upgrade%20inquiry";
const HELP_MAIL = "mailto:contact@pvmath.com?subject=PVMath%20support";
const SITE_URL = "https://pvmath.com";

function planLabel(plan: string) {
  const labels: Record<string, string> = {
    free: "Free",
    professional: "Professional",
    developer: "Developer",
    enterprise: "Enterprise",
    dev: "Development",
  };
  return labels[plan] || plan;
}

function initials(email: string) {
  return (email.split("@")[0] || "?").slice(0, 2).toUpperCase();
}

interface Props {
  email: string;
  profile: MeResponse | null;
  token: string;
  onLogout: () => void;
}

type Panel = "none" | "settings" | "membership";

export function AccountSidebar({ email, profile, token, onLogout }: Props) {
  const [accountOpen, setAccountOpen] = useState(false);
  const [panel, setPanel] = useState<Panel>("none");
  const [currentPass, setCurrentPass] = useState("");
  const [newPass, setNewPass] = useState("");
  const [confirmPass, setConfirmPass] = useState("");
  const [passMsg, setPassMsg] = useState("");
  const [passBusy, setPassBusy] = useState(false);

  const usage = profile?.usage;
  let usageLine = "";
  if (profile?.is_admin) usageLine = "Unlimited (admin)";
  else if (usage?.mode === "pooled" && usage.limit != null)
    usageLine = `${usage.total} / ${usage.limit} this month`;
  else if (usage?.remaining != null) usageLine = `${usage.remaining} remaining`;

  async function handlePassword(e: FormEvent) {
    e.preventDefault();
    setPassMsg("");
    if (!currentPass || !newPass || !confirmPass) {
      setPassMsg("Fill in all fields.");
      return;
    }
    if (newPass !== confirmPass) {
      setPassMsg("Passwords do not match.");
      return;
    }
    setPassBusy(true);
    try {
      await changePassword(token, currentPass, newPass);
      setPassMsg("Password updated.");
      setCurrentPass("");
      setNewPass("");
      setConfirmPass("");
    } catch (err) {
      setPassMsg(err instanceof Error ? err.message : "Update failed.");
    } finally {
      setPassBusy(false);
    }
  }

  function togglePanel(next: Exclude<Panel, "none">) {
    setPanel((p) => (p === next ? "none" : next));
  }

  return (
    <aside className="account-sidebar">
      <button
        type="button"
        className="account-sidebar-head account-head-btn"
        onClick={() => setAccountOpen((o) => !o)}
        aria-expanded={accountOpen}
      >
        <div className="account-avatar" aria-hidden>
          {initials(email)}
        </div>
        <div className="account-identity">
          <div className="account-email">{email}</div>
          {usage ? (
            <div className="account-plan">
              {planLabel(usage.plan)}
              {profile?.is_admin ? " · Admin" : ""}
            </div>
          ) : null}
        </div>
        <span className="account-caret">{accountOpen ? "▾" : "▸"}</span>
      </button>

      {accountOpen ? (
        <div className="account-collapsible">
          {usageLine ? <p className="account-usage">{usageLine}</p> : null}

          <nav className="account-nav">
            <button
              type="button"
              className={`account-nav-item${panel === "membership" ? " active" : ""}`}
              onClick={() => togglePanel("membership")}
            >
              Membership &amp; billing
            </button>
            <button
              type="button"
              className={`account-nav-item${panel === "settings" ? " active" : ""}`}
              onClick={() => togglePanel("settings")}
            >
              Settings
            </button>
            <a className="account-nav-item" href={HELP_MAIL}>
              Help center
            </a>
            <a className="account-nav-item" href={SITE_URL} target="_blank" rel="noreferrer">
              pvmath.com
            </a>
          </nav>

          {panel === "settings" ? (
            <form className="account-panel account-panel-sm" onSubmit={(e) => void handlePassword(e)}>
              <h3>Change password</h3>
              <div className="field">
                <label htmlFor="cur-pass">Current</label>
                <input
                  id="cur-pass"
                  type="password"
                  autoComplete="current-password"
                  value={currentPass}
                  onChange={(e) => setCurrentPass(e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="new-pass">New</label>
                <input
                  id="new-pass"
                  type="password"
                  autoComplete="new-password"
                  value={newPass}
                  onChange={(e) => setNewPass(e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="confirm-pass">Confirm</label>
                <input
                  id="confirm-pass"
                  type="password"
                  value={confirmPass}
                  onChange={(e) => setConfirmPass(e.target.value)}
                />
              </div>
              {passMsg ? <p className="hint account-msg">{passMsg}</p> : null}
              <button className="btn btn-primary btn-block btn-sm" type="submit" disabled={passBusy}>
                {passBusy ? "Saving…" : "Save password"}
              </button>
            </form>
          ) : null}

          {panel === "membership" ? (
            <div className="account-panel account-panel-sm">
              <h3>Membership &amp; billing</h3>
              <p className="hint">
                Plan: <strong>{planLabel(usage?.plan || "free")}</strong>
              </p>
              {usage?.limit != null && !profile?.is_admin ? (
                <p className="hint">
                  {usage.total} of {usage.limit} analyses used this month.
                </p>
              ) : null}
              <a className="btn btn-primary btn-block btn-sm" href={UPGRADE_MAIL}>
                Contact to upgrade
              </a>
            </div>
          ) : null}

          <div className="account-sidebar-foot">
            <button className="btn btn-ghost btn-block btn-sm" type="button" onClick={onLogout}>
              Log out
            </button>
          </div>
        </div>
      ) : null}
    </aside>
  );
}
