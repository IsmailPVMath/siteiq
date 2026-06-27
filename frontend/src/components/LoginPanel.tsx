import { FormEvent, useState } from "react";
import { PRODUCT_NAME, TAGLINE } from "../lib/brand";
import {
  requestPasswordReset,
  resendSignupOtp,
  signInWithPassword,
  signUp,
  verifySignupOtp,
  type AuthSession,
} from "../lib/auth";

interface Props {
  onSignedIn: (session: AuthSession) => void;
}

type AuthTab = "login" | "register" | "verify-otp";

export function LoginPanel({ onSignedIn }: Props) {
  const [tab, setTab] = useState<AuthTab>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [otpCode, setOtpCode] = useState("");
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

  async function handleForgotPassword() {
    setError("");
    setInfo("");
    if (!email.trim()) {
      setError("Enter your email above, then tap “Forgot password?”.");
      return;
    }
    setLoading(true);
    try {
      await requestPasswordReset(email);
      setInfo(`If an account exists for ${email.trim()}, a reset link is on its way.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send reset email");
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(e: FormEvent) {
    e.preventDefault();
    setError("");
    setInfo("");
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setLoading(true);
    try {
      const { session, otpRequired } = await signUp(email, password, firstName, lastName);
      if (session) {
        onSignedIn(session);
        return;
      }
      if (otpRequired) {
        setTab("verify-otp");
        setOtpCode("");
        setInfo(`We sent a 6-digit code to ${email.trim()}. Check spam if you do not see it.`);
        setPassword("");
        setConfirmPassword("");
        return;
      }
      setInfo("Account created — you can log in now.");
      setTab("login");
      setPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyOtp(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setInfo("");
    try {
      const session = await verifySignupOtp(email, otpCode);
      onSignedIn(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleResendOtp() {
    setLoading(true);
    setError("");
    setInfo("");
    try {
      await resendSignupOtp(email);
      setInfo(`New code sent to ${email.trim()}.`);
      setOtpCode("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resend code");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="hero-badge auth-hero-badge">
        <span className="dot" />
        {PRODUCT_NAME} — Early Access
      </div>
      <div className="card auth-card" style={{ maxWidth: 420, margin: "0 auto" }}>
        <h2>{PRODUCT_NAME}</h2>
        <p className="hint">{TAGLINE} Log in or create a free account.</p>

        {tab !== "verify-otp" ? (
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
        ) : null}

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
            <button
              type="button"
              className="auth-link-btn"
              onClick={() => void handleForgotPassword()}
              disabled={loading}
            >
              Forgot password?
            </button>
          </form>
        ) : null}

        {tab === "register" ? (
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
                minLength={8}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="reg-password2">Repeat password</label>
              <input
                id="reg-password2"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                minLength={8}
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
        ) : null}

        {tab === "verify-otp" ? (
          <form onSubmit={handleVerifyOtp}>
            <p className="hint" style={{ marginBottom: "1rem" }}>
              Enter the 6-digit code sent to <strong>{email}</strong>
            </p>
            <div className="field">
              <label htmlFor="otp-code">Verification code</label>
              <input
                id="otp-code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={otpCode}
                onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="• • • • • •"
                maxLength={6}
                required
                style={{ letterSpacing: "0.25em", textAlign: "center", fontWeight: 700 }}
              />
            </div>
            <button className="btn btn-primary" type="submit" disabled={loading || otpCode.length < 6}>
              {loading ? (
                <>
                  <span className="spinner" />
                  Verifying…
                </>
              ) : (
                "Verify & sign in"
              )}
            </button>
            <button
              type="button"
              className="auth-link-btn"
              onClick={() => void handleResendOtp()}
              disabled={loading}
            >
              Resend code
            </button>
            <button
              type="button"
              className="auth-link-btn"
              onClick={() => {
                setTab("register");
                setOtpCode("");
                setError("");
                setInfo("");
              }}
              disabled={loading}
            >
              ← Back
            </button>
          </form>
        ) : null}
      </div>
    </div>
  );
}
