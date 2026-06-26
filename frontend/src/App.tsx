import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "./components/AppShell";
import { LoginPanel } from "./components/LoginPanel";
import { MyProjectsPage } from "./pages/MyProjectsPage";
import { ProjectSetupPage } from "./pages/ProjectSetupPage";
import { OutputPage } from "./pages/OutputPage";
import { ProcessingPage } from "./pages/ProcessingPage";
import { fetchMe, getProject, runWorkflowScreen, setTokenRefresher } from "./lib/api";
import { draftToGateRequest, projectRecordToDraft } from "./lib/projectSetup";
import {
  restoreWorkflowFromRecord,
  type WorkflowRestore,
} from "./lib/workflowSave";
import {
  isAccessTokenStale,
  loadSession,
  refreshSession,
  signOut,
  type AuthSession,
} from "./lib/auth";
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
  const [editingProjectId, setEditingProjectId] = useState("");
  const [workflowRestore, setWorkflowRestore] = useState<WorkflowRestore | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState<WorkflowScreenResponse | null>(null);
  const [outputModule, setOutputModule] = useState<OutputModuleStage>("screen");
  const sessionRef = useRef<AuthSession | null>(null);

  sessionRef.current = session;

  const loadProfile = useCallback(async (accessToken: string) => {
    try {
      setProfile(await fetchMe(accessToken));
    } catch {
      setProfile(null);
    }
  }, []);

  const refreshCurrentSession = useCallback(async (): Promise<AuthSession | null> => {
    const current = sessionRef.current;
    if (!current) return null;
    if (!isAccessTokenStale(current)) return current;
    if (!current.refresh_token) {
      signOut();
      setSession(null);
      setProfile(null);
      return null;
    }
    try {
      const next = await refreshSession(current);
      setSession(next);
      sessionRef.current = next;
      await loadProfile(next.access_token);
      return next;
    } catch {
      signOut();
      setSession(null);
      setProfile(null);
      return null;
    }
  }, [loadProfile]);

  useEffect(() => {
    setTokenRefresher(async () => {
      const next = await refreshCurrentSession();
      return next?.access_token ?? null;
    });
    return () => setTokenRefresher(null);
  }, [refreshCurrentSession]);

  useEffect(() => {
    async function boot() {
      const saved = loadSession();
      if (!saved) {
        setBooting(false);
        return;
      }
      try {
        let active = saved;
        if (isAccessTokenStale(saved) && saved.refresh_token) {
          active = await refreshSession(saved);
        }
        setSession(active);
        sessionRef.current = active;
        await loadProfile(active.access_token);
      } catch {
        signOut();
        setSession(null);
        setProfile(null);
      } finally {
        setBooting(false);
      }
    }
    void boot();
  }, [loadProfile]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setInterval(() => {
      void refreshCurrentSession();
    }, 4 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, [session, refreshCurrentSession]);

  function handleSignedIn(next: AuthSession) {
    setSession(next);
    sessionRef.current = next;
    void loadProfile(next.access_token);
  }

  function handleLogout() {
    signOut();
    setSession(null);
    setProfile(null);
    setResult(null);
    setLastInput(null);
    setEditingProjectId("");
    setStep("input");
    setOutputModule("screen");
    setError("");
  }

  function resetWorkflow() {
    setResult(null);
    setLastInput(null);
    setEditingProjectId("");
    setWorkflowRestore(null);
    setOutputModule("screen");
    setError("");
    setStep("input");
  }

  function openProjects() {
    setError("");
    setStep("projects");
  }

  async function openProject(id: string) {
    const active = await refreshCurrentSession();
    const token = active?.access_token;
    if (!token) return;
    setError("");
    try {
      const row = await getProject(token, id);
      const restored = restoreWorkflowFromRecord(row);
      setEditingProjectId(id);
      if (restored) {
        setLastInput(restored.input);
        setResult(restored.screening);
        setOutputModule(restored.lastStage);
        setWorkflowRestore(restored);
        setStep("output");
      } else {
        const draft = projectRecordToDraft(row);
        setLastInput(draftToGateRequest(draft));
        setWorkflowRestore(null);
        setResult(null);
        setStep("input");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open project");
    }
  }

  function startNewProject() {
    setEditingProjectId("");
    setWorkflowRestore(null);
    setLastInput(null);
    setResult(null);
    setError("");
    setStep("input");
  }

  const pipelineStage: PipelineStage = useMemo(() => {
    if (step === "projects" || step === "input") return "setup";
    if (step === "processing") return "siteiq";
    return pipelineFromOutputModule(outputModule);
  }, [step, outputModule]);

  const pipelineUnlocked = useMemo((): PipelineStage[] => {
    if (step === "projects" || step === "input") return ["setup"];
    if (step === "processing") return ["setup", "siteiq"];
    return ["setup", "siteiq", "topoiq", "layoutiq", "yieldiq"];
  }, [step]);

  const pipelineCompleted = useMemo((): Partial<Record<PipelineStage, boolean>> => {
    if (step === "projects" || step === "input") return {};
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
    const active = await refreshCurrentSession();
    const token = active?.access_token;
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
      onOpenProjects={openProjects}
      wide={step === "output" || step === "input" || step === "projects"}
    >
      {error ? <div className="error-banner">{error}</div> : null}

      {step === "projects" ? (
        <MyProjectsPage
          token={session.access_token}
          onOpenProject={openProject}
          onNewProject={startNewProject}
        />
      ) : null}

      {step === "input" ? (
        <ProjectSetupPage
          key={editingProjectId || "new"}
          token={session.access_token}
          initial={lastInput ?? undefined}
          initialProjectId={editingProjectId || undefined}
          onOpenProjects={openProjects}
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
          projectId={workflowRestore?.projectId ?? editingProjectId}
          initialTopo={workflowRestore?.topo ?? null}
          initialFinalScore={workflowRestore?.finalScore ?? null}
          initialGisSetbacks={workflowRestore?.gisSetbacks ?? null}
          onProjectIdChange={(id) => {
            setEditingProjectId(id);
            setWorkflowRestore((prev) => (prev ? { ...prev, projectId: id } : prev));
          }}
        />
      ) : null}
    </AppShell>
  );
}
