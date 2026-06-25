import type { MeResponse } from "../types/gate";

interface Props {
  email: string;
  profile: MeResponse | null;
  onLogout: () => void;
}

export function Header({ email, profile, onLogout }: Props) {
  const usage = profile?.usage;
  let usageLine = "";
  if (profile?.is_admin) {
    usageLine = "Admin · unlimited";
  } else if (usage?.mode === "pooled" && usage.limit != null) {
    usageLine = `${usage.total} / ${usage.limit} analyses this month`;
  } else if (usage?.remaining != null) {
    usageLine = `${usage.remaining} SiteIQ analyses left`;
  }

  return (
    <header className="topbar">
      <div className="brand">
        <strong>PVMath</strong>
        <span>From site to system</span>
      </div>
      <div className="user-chip">
        <div>{email}</div>
        {usageLine ? <div>{usageLine}</div> : null}
        <button
          className="btn btn-ghost"
          type="button"
          onClick={onLogout}
          style={{ marginTop: "0.5rem" }}
        >
          Log out
        </button>
      </div>
    </header>
  );
}
