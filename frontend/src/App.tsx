import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "./components/AppShell";
import { LoginPanel } from "./components/LoginPanel";
import { ProjectSetupPage } from "./pages/ProjectSetupPage";
import { OutputPage } from "./pages/OutputPage";
import { ProcessingPage } from "./pages/ProcessingPage";
import { fetchMe, runWorkflowScreen } from "./lib/api";
import { loadSession, signOut, type AuthSession } from "./lib/auth";
import type { GateAnalyzeRequest, MeResponse } from "./types/gate";
import type {
  OutputModuleStage,
  PipelineStage,
  WorkflowScreenResponse,
  WorkflowStep,
} from "./types/workflow";
import {
  outputModuleFromPipeline,
  pipelineFromOutputModule,
} from "./types/workflow";

export default function App() {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [profile, setProfile] = useState<MeResponse | null>(null);
  const [booting, setBooting] = useState(true);
  const [step, setStep] = useState<WorkflowStep>("input");
  const [lastInput, setLastInput] = useState<GateAnalyzeRequest | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState<WorkflowScreenResponse | null>(null);
  const [outputModule, setOutputModule] = useState<OutputModuleStage>("screen");

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
    setOutputModule("screen");
    setError("");
  }

  function resetWorkflow() {
    setResult(null);
    setLastInput(null);
    setOutputModule("screen");
    setError("");
    setStep("input");
  }

  const pipelineStage: PipelineStage = useMemo(() => {
    if (step === "input") return "setup";
    if (step === "processing") return "siteiq";
    return pipelineFromOutputModule(outputModule);
  }, [step, outputModule]);

  const pipelineUnlocked = useMemo((): PipelineStage[] => {
    if (step === "input") return ["setup"];
    if (step === "processing") return ["setup", "siteiq"];
    return ["setup", "siteiq", "topoiq", "layoutiq", "yieldiq"];
  }, [step]);

  const pipelineCompleted = useMemo((): Partial<Record<PipelineStage, boolean>> => {
    if (step === "input") return {};
    if (step === "processing") return { setup: true };
    return {
      setup: true,
      siteiq: true,
      topoiq: outputModule !== "screen",
      layoutiq: outputModule === "layout" || outputModule === "yield",
      yieldiq: outputModule === "yield",
    };
  }, [step, outputModule]);

  function handlePipelineNavigate(stage: PipelineStage) {
    if (stage === "setup") {
      setStep("input");
      return;
    }
    if (step !== "output") return;
    const mod = outputModuleFromPipeline(stage);
    if (mod) setOutputModule(mod);
  }

  async function handleStartScreening(body: GateAnalyzeRequest) {
    const token = session?.access_token;
    if (!token) return;
    setLastInput(body);
    setError("");
    setResult(null);
    setOutputModule("screen");
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
      <div className="app-boot">
        <p className="hint">Loading…</p>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="app-boot">
        <LoginPanel onSignedIn={handleSignedIn} />
      </div>
    );
  }

  return (
    <AppShell
      email={session.email || profile?.email || ""}
      profile={profile}
      token={session.access_token}
      pipelineStage={pipelineStage}
      pipelineInteractive={step === "output" || step === "input"}
      pipelineUnlocked={pipelineUnlocked}
      pipelineCompleted={pipelineCompleted}
      onPipelineNavigate={handlePipelineNavigate}
      onLogout={handleLogout}
      wide={step === "output" || step === "input"}
    >
      {error ? <div className="error-banner">{error}</div> : null}

      {step === "input" ? (
        <ProjectSetupPage
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
          activeModule={outputModule}
          onModuleChange={setOutputModule}
          onEditInput={() => setStep("input")}
          onNewScreening={resetWorkflow}
        />
      ) : null}
    </AppShell>
  );
}
