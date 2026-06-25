const STORAGE_KEY = "pvmath_gate_session";

const API_URL = (import.meta.env.VITE_API_URL || "https://api.pvmath.com").replace(
  /\/$/,
  "",
);

export interface AuthSession {
  access_token: string;
  refresh_token: string;
  email: string;
  user_id: string;
  expires_at: number;
}

export function loadSession(): AuthSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as AuthSession;
    if (!session.access_token) return null;
    if (session.expires_at && session.expires_at * 1000 < Date.now()) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function saveSession(session: AuthSession | null): void {
  if (!session) {
    localStorage.removeItem(STORAGE_KEY);
    return;
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export async function signInWithPassword(
  email: string,
  password: string,
): Promise<AuthSession> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ email: email.trim(), password }),
    });
  } catch {
    throw new Error(
      `Could not reach API at ${API_URL}. Check internet and VITE_API_URL in .env.local.`,
    );
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.access_token) {
    const msg = data.detail || data.message || "Invalid email or password";
    throw new Error(String(msg));
  }

  const session: AuthSession = {
    access_token: data.access_token,
    refresh_token: data.refresh_token ?? "",
    email: data.user?.email ?? email.trim(),
    user_id: data.user?.id ?? "",
    expires_at: data.expires_at ?? 0,
  };
  saveSession(session);
  return session;
}

export function signOut(): void {
  saveSession(null);
}
