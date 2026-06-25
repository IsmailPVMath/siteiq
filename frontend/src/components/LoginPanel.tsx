import { FormEvent, useState } from "react";
import { signInWithPassword, type AuthSession } from "../lib/auth";

interface Props {
  onSignedIn: (session: AuthSession) => void;
}

export function LoginPanel({ onSignedIn }: Props) {
  const [email, setEmail] = useState("admin@pvmath.com");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const session = await signInWithPassword(email, password);
      onSignedIn(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 420, margin: "3rem auto" }}>
      <h2>Sign in to PVMath</h2>
      <p className="hint">From site to system. Use your SiteIQ account.</p>
      {error ? <div className="error-banner">{error}</div> : null}
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
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
    </div>
  );
}
