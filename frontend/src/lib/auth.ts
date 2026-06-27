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

/** True when access token is expired or within 5 minutes of expiry. */
export function isAccessTokenStale(session: AuthSession): boolean {
  if (!session.expires_at) return false;
  return session.expires_at * 1000 < Date.now() + 5 * 60 * 1000;
}

export function loadSession(): AuthSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as AuthSession;
    if (!session.access_token) return null;
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

export async function signUp(
  email: string,
  password: string,
  firstName = "",
  lastName = "",
): Promise<{ session: AuthSession | null; otpRequired: boolean; email: string }> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        email: email.trim(),
        password,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
      }),
    });
  } catch {
    throw new Error(
      `Could not reach API at ${API_URL}. Check internet and VITE_API_URL in .env.local.`,
    );
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.detail || data.message || "Could not create account";
    throw new Error(String(msg));
  }

  if (data.otp_required) {
    return { session: null, otpRequired: true, email: data.email || email.trim() };
  }

  if (!data.access_token) {
    return { session: null, otpRequired: false, email: email.trim() };
  }

  const session: AuthSession = {
    access_token: data.access_token,
    refresh_token: data.refresh_token ?? "",
    email: data.user?.email ?? email.trim(),
    user_id: data.user?.id ?? "",
    expires_at: data.expires_at ?? 0,
  };
  saveSession(session);
  return { session, otpRequired: false, email: session.email };
}

export async function verifySignupOtp(email: string, code: string): Promise<AuthSession> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/auth/signup/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ email: email.trim(), code: code.trim() }),
    });
  } catch {
    throw new Error("Could not reach verification service.");
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.access_token) {
    const msg = data.detail || data.message || "Invalid verification code";
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

export async function resendSignupOtp(email: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/auth/signup/resend`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ email: email.trim() }),
    });
  } catch {
    throw new Error("Could not reach verification service.");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(String(data.detail || "Could not resend code"));
  }
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

export async function requestPasswordReset(email: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/auth/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ email: email.trim() }),
    });
  } catch {
    throw new Error("Could not reach the password reset service.");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(String(data.detail || "Could not send reset email"));
  }
}

export async function refreshSession(session: AuthSession): Promise<AuthSession> {
  if (!session.refresh_token) {
    throw new Error("Session expired — please sign in again.");
  }

  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ refresh_token: session.refresh_token }),
    });
  } catch {
    throw new Error("Could not reach auth service.");
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.access_token) {
    const msg = data.detail || data.message || "Session expired — please sign in again.";
    throw new Error(String(msg));
  }

  const next: AuthSession = {
    access_token: data.access_token,
    refresh_token: data.refresh_token ?? session.refresh_token,
    email: data.user?.email ?? session.email,
    user_id: data.user?.id ?? session.user_id,
    expires_at: data.expires_at ?? 0,
  };
  saveSession(next);
  return next;
}

export function signOut(): void {
  saveSession(null);
}
