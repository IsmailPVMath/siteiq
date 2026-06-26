import { FormEvent, useState } from "react";
import { signInWithPassword, signUp, type AuthSession } from "../lib/auth";

interface Props {
  onSignedIn: (session: AuthSession) => void;
}

type AuthTab = "login" | "register";

export function LoginPanel({ onSignedIn }: Props) {
  const [tab, setTab] = useState<AuthTab>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setInfo("");
    try {
      const session = await signInWithPassword(email, password);
      onSignedIn(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setInfo("");
    try {
      const { session, emailConfirmationRequired } = await signUp(
        email,
        password,
        firstName,
        lastName,
      );
      if (session) {
        onSignedIn(session);
        return;
      }
      if (emailConfirmationRequired) {
        setInfo("Account created — check your email to confirm, then log in.");
        setTab("login");
        setPassword("");
        return;
      }
      setInfo("Account created — you can log in now.");
      setTab("login");
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card auth-card" style={{ maxWidth: 420, margin: "3rem auto" }}>
      <h2>SiteIQ by PVMath</h2>
      <p className="hint">From site to system. Log in or create a free account.</p>

      <div className="auth-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "login"}
          className={`auth-tab${tab === "login" ? " active" : ""}`}
          onClick={() => {
            setTab("login");
            setError("");
            setInfo("");
          }}
        >
          Log in
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "register"}
          className={`auth-tab${tab === "register" ? " active" : ""}`}
          onClick={() => {
            setTab("register");
            setError("");
            setInfo("");
          }}
        >
          Create account
        </button>
      </div>

      {error ? <div className="error-banner">{error}</div> : null}
      {info ? <div className="info-banner">{info}</div> : null}

      {tab === "login" ? (
        <form onSubmit={handleLogin}>
          <div className="field">
            <label htmlFor="login-email">Email</label>
            <input
              id="login-email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={loading}>
            {loading ? (
              <>
                <span className="spinner" />
                Signing in…
              </>
            ) : (
              "Sign in"
            )}
          </button>
        </form>
      ) : (
        <form onSubmit={handleRegister}>
          <div className="field-row">
            <div className="field">
              <label htmlFor="reg-first">First name</label>
              <input
                id="reg-first"
                type="text"
                autoComplete="given-name"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="reg-last">Last name</label>
              <input
                id="reg-last"
                type="text"
                autoComplete="family-name"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="reg-email">Email</label>
            <input
              id="reg-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="reg-password">Password</label>
            <input
              id="reg-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={6}
              required
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={loading}>
            {loading ? (
              <>
                <span className="spinner" />
                Creating account…
              </>
            ) : (
              "Create account"
            )}
          </button>
        </form>
      )}
    </div>
  );
}
