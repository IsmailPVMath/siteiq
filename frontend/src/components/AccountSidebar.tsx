import { FormEvent, useState } from "react";
import { changePassword } from "../lib/api";
import type { MeResponse } from "../types/gate";

const UPGRADE_MAIL =
  "mailto:contact@pvmath.com?subject=PVMath%20%E2%80%94%20Billing%20or%20upgrade%20inquiry";
const HELP_MAIL = "mailto:contact@pvmath.com?subject=PVMath%20support";

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

const NAV_ITEMS = [
  { id: "dashboard", label: "Dashboard", disabled: true },
  { id: "projects", label: "Projects", disabled: true },
  { id: "templates", label: "Templates", disabled: true },
  { id: "recent", label: "Recent projects", disabled: true },
  { id: "shared", label: "Shared projects", disabled: true },
  { id: "reports", label: "Reports", disabled: true },
] as const;

const ACCOUNT_ITEMS = [
  { id: "membership", label: "Membership", action: "membership" as const },
  { id: "billing", label: "Billing", href: UPGRADE_MAIL },
  { id: "notifications", label: "Notifications", disabled: true },
  { id: "profile", label: "Profile", disabled: true },
  { id: "settings", label: "Settings", action: "password" as const },
  { id: "help", label: "Help center", href: HELP_MAIL },
  { id: "feedback", label: "Feedback", href: "mailto:contact@pvmath.com?subject=PVMath%20feedback" },
] as const;

interface Props {
  email: string;
  profile: MeResponse | null;
  token: string;
  onLogout: () => void;
}

export function AccountSidebar({ email, profile, token, onLogout }: Props) {
  const [panel, setPanel] = useState<"none" | "password" | "membership">("none");
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

  return (
    <aside className="account-sidebar">
      <div className="account-sidebar-head">
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
      </div>

      {usageLine ? <p className="account-usage">{usageLine}</p> : null}

      <nav className="account-nav account-nav-section">
        <div className="account-nav-label">Workspace</div>
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className="account-nav-item disabled"
            disabled
            title="Coming soon"
          >
            {item.label}
          </button>
        ))}
      </nav>

      <nav className="account-nav account-nav-section">
        <div className="account-nav-label">Account</div>
        {ACCOUNT_ITEMS.map((item) => {
          if ("href" in item && item.href) {
            return (
              <a key={item.id} className="account-nav-item" href={item.href}>
                {item.label}
              </a>
            );
          }
          if ("action" in item) {
            return (
              <button
                key={item.id}
                type="button"
                className={`account-nav-item${panel === item.action ? " active" : ""}`}
                onClick={() => setPanel((p) => (p === item.action ? "none" : item.action))}
              >
                {item.label}
              </button>
            );
          }
          return (
            <button key={item.id} type="button" className="account-nav-item" disabled>
              {item.label}
            </button>
          );
        })}
      </nav>

      {panel === "password" ? (
        <form className="account-panel" onSubmit={(e) => void handlePassword(e)}>
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
          <button className="btn btn-primary btn-block" type="submit" disabled={passBusy}>
            {passBusy ? "Saving…" : "Save"}
          </button>
        </form>
      ) : null}

      {panel === "membership" ? (
        <div className="account-panel">
          <h3>Membership</h3>
          <p className="hint">
            Plan: <strong>{planLabel(usage?.plan || "free")}</strong>
          </p>
          <a className="btn btn-primary btn-block" href={UPGRADE_MAIL}>
            Contact to upgrade
          </a>
        </div>
      ) : null}

      <div className="account-sidebar-foot">
        <button className="btn btn-ghost btn-block" type="button" onClick={onLogout}>
          Log out
        </button>
      </div>
    </aside>
  );
}
