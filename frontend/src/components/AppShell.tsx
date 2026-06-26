import type { ReactNode } from "react";
import { AccountSidebar } from "./AccountSidebar";
import { Header } from "./Header";
import { WorkflowPipeline } from "./WorkflowPipeline";
import type { MeResponse } from "../types/gate";
import type { PipelineStage } from "../types/workflow";

interface Props {
  email: string;
  profile: MeResponse | null;
  token: string;
  pipelineStage: PipelineStage;
  pipelineInteractive?: boolean;
  pipelineUnlocked?: PipelineStage[];
  pipelineCompleted?: Partial<Record<PipelineStage, boolean>>;
  onPipelineNavigate?: (stage: PipelineStage) => void;
  onLogout: () => void;
  wide?: boolean;
  children: ReactNode;
}

export function AppShell({
  email,
  profile,
  token,
  pipelineStage,
  pipelineInteractive,
  pipelineUnlocked,
  pipelineCompleted,
  onPipelineNavigate,
  onLogout,
  wide = false,
  children,
}: Props) {
  return (
    <div className={`app-layout${wide ? " app-layout-wide" : ""}`}>
      <AccountSidebar
        email={email}
        profile={profile}
        token={token}
        onLogout={onLogout}
      />
      <div className="app-main">
        <Header email={email} profile={profile} />
        <div className={`app-content${wide ? " app-content-wide" : ""}`}>
          <WorkflowPipeline
            current={pipelineStage}
            interactive={pipelineInteractive}
            unlocked={pipelineUnlocked}
            completed={pipelineCompleted}
            onNavigate={onPipelineNavigate}
          />
          {children}
        </div>
      </div>
    </div>
  );
}
