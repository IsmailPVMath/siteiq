import { useCallback, useEffect, useState } from "react";
import { AnalysisForm } from "./components/AnalysisForm";
import { Header } from "./components/Header";
import { LoginPanel } from "./components/LoginPanel";
import { ResultsPanel } from "./components/ResultsPanel";
import { fetchMe, runGateAnalysis } from "./lib/api";
import { loadSession, signOut, type AuthSession } from "./lib/auth";
import type { GateAnalyzeRequest, GateAnalyzeResponse, MeResponse } from "./types/gate";

export default function App() {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [profile, setProfile] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<GateAnalyzeResponse | null>(null);

  const loadProfile = useCallback(async (accessToken: string) => {
    try {
      const me = await fetchMe(accessToken);
      setProfile(me);
    } catch {
      setProfile(null);
    }
  }, []);

  useEffect(() => {
    const saved = loadSession();
    setSession(saved);
    setLoading(false);
    if (saved?.access_token) {
      void loadProfile(saved.access_token);
    }
  }, [loadProfile]);

  function handleSignedIn(next: AuthSession) {
    setSession(next);
    void loadProfile(next.access_token);
  }

  function handleLogout() {
    signOut();
    setSession(null);
    setProfile(null);
    setResult(null);
    setError("");
  }

  async function handleAnalyze(body: GateAnalyzeRequest) {
    const token = session?.access_token;
    if (!token) return;
    setAnalyzing(true);
    setError("");
    setResult(null);
    try {
      const data = await runGateAnalysis(token, body);
      setResult(data);
      await loadProfile(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  }

  if (loading) {
    return (
      <div className="app-shell">
        <p className="hint">Loading…</p>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="app-shell">
        <LoginPanel onSignedIn={handleSignedIn} />
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Header
        email={session.email || profile?.email || ""}
        profile={profile}
        onLogout={handleLogout}
      />
      {error ? <div className="error-banner">{error}</div> : null}
      <div className="grid-2">
        <AnalysisForm loading={analyzing} onSubmit={handleAnalyze} />
        <ResultsPanel result={result} />
      </div>
    </div>
  );
}
