import type { MeResponse } from "../types/gate";

interface Props {
  email: string;
  profile: MeResponse | null;
}

export function Header({ email, profile }: Props) {
  const usage = profile?.usage;
  let usageLine = "";
  if (profile?.is_admin) {
    usageLine = "Admin";
  } else if (usage?.mode === "pooled" && usage.limit != null) {
    usageLine = `${usage.total}/${usage.limit} this month`;
  } else if (usage?.remaining != null) {
    usageLine = `${usage.remaining} left`;
  }

  return (
    <header className="topbar">
      <div className="brand">
        <strong>PVMath</strong>
        <span>From site to system</span>
      </div>
      <div className="topbar-meta">
        <span className="topbar-email">{email}</span>
        {usageLine ? <span className="topbar-usage">{usageLine}</span> : null}
      </div>
    </header>
  );
}
