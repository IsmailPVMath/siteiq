import { useCallback, useEffect, useState } from "react";
import { Header } from "./components/Header";
import { LoginPanel } from "./components/LoginPanel";
import { Stepper } from "./components/Stepper";
import { InputPage } from "./pages/InputPage";
import { OutputPage } from "./pages/OutputPage";
import { ProcessingPage } from "./pages/ProcessingPage";
import { fetchMe, runWorkflowScreen } from "./lib/api";
import { loadSession, signOut, type AuthSession } from "./lib/auth";
import type { GateAnalyzeRequest, MeResponse } from "./types/gate";
import type { WorkflowScreenResponse, WorkflowStep } from "./types/workflow";

export default function App() {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [profile, setProfile] = useState<MeResponse | null>(null);
  const [booting, setBooting] = useState(true);
  const [step, setStep] = useState<WorkflowStep>("input");
  const [lastInput, setLastInput] = useState<GateAnalyzeRequest | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState<WorkflowScreenResponse | null>(null);

  const loadProfile = useCallback(async (accessToken: string) => {
    try {
      setProfile(await fetchMe(accessToken));
    } catch {
      setProfile(null);
    }
  }, []);

  useEffect(() => {
    const saved = loadSession();
    setSession(saved);
    setBooting(false);
    if (saved?.access_token) void loadProfile(saved.access_token);
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
    setLastInput(null);
    setStep("input");
    setError("");
  }

  function resetWorkflow() {
    setResult(null);
    setLastInput(null);
    setError("");
    setStep("input");
  }

  async function handleStartScreening(body: GateAnalyzeRequest) {
    const token = session?.access_token;
    if (!token) return;
    setLastInput(body);
    setError("");
    setResult(null);
    setStep("processing");
    try {
      const data = await runWorkflowScreen(token, {
        project_name: body.project_name,
        lat: body.lat,
        lon: body.lon,
        area_ha: body.area_ha,
        land_use: body.land_use,
        mount_type: body.mount_type,
        country: body.country,
      });
      setResult(data);
      await loadProfile(token);
      setStep("output");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Screening failed");
      setStep("input");
    }
  }

  if (booting) {
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
    <div className={`app-shell ${step === "output" ? "app-shell-results" : "app-shell-wide"}`}>
      <Header
        email={session.email || profile?.email || ""}
        profile={profile}
        onLogout={handleLogout}
      />
      <Stepper current={step} />
      {error ? <div className="error-banner">{error}</div> : null}

      {step === "input" ? (
        <InputPage
          token={session.access_token}
          initial={lastInput ?? undefined}
          onSubmit={handleStartScreening}
        />
      ) : null}
      {step === "processing" && lastInput ? (
        <ProcessingPage projectName={lastInput.project_name} />
      ) : null}
      {step === "output" && result ? (
        <OutputPage
          token={session.access_token}
          result={result}
          input={lastInput ?? undefined}
          onEditInput={() => setStep("input")}
          onNewScreening={resetWorkflow}
        />
      ) : null}
    </div>
  );
}
