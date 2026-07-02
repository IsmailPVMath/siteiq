import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
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
  pipelineModules?: import("../types/workflow").PipelineModule[];
  pipelineInteractive?: boolean;
  pipelineUnlocked?: PipelineStage[];
  pipelineCompleted?: Partial<Record<PipelineStage, boolean>>;
  onPipelineNavigate?: (stage: PipelineStage) => void;
  onLogout: () => void;
  onOpenProjects?: () => void;
  wide?: boolean;
  children: ReactNode;
}

const MIN_W = 200;
const MAX_W = 440;
const DEFAULT_W = 260;

function clampWidth(w: number) {
  return Math.min(MAX_W, Math.max(MIN_W, w));
}

export function AppShell({
  email,
  profile,
  token,
  pipelineStage,
  pipelineModules: pipelineModuleList,
  pipelineInteractive,
  pipelineUnlocked,
  pipelineCompleted,
  onPipelineNavigate,
  onLogout,
  onOpenProjects,
  wide = false,
  children,
}: Props) {
  const [collapsed, setCollapsed] = useState<boolean>(
    () => localStorage.getItem("pvm_sb_collapsed") === "1",
  );
  const [width, setWidth] = useState<number>(() => {
    const stored = Number(localStorage.getItem("pvm_sb_width"));
    return stored ? clampWidth(stored) : DEFAULT_W;
  });
  const draggingRef = useRef(false);

  useEffect(() => {
    localStorage.setItem("pvm_sb_collapsed", collapsed ? "1" : "0");
  }, [collapsed]);
  useEffect(() => {
    localStorage.setItem("pvm_sb_width", String(width));
  }, [width]);

  const onPointerMove = useCallback((e: PointerEvent) => {
    if (!draggingRef.current) return;
    setWidth(clampWidth(e.clientX));
  }, []);

  const stopDrag = useCallback(() => {
    draggingRef.current = false;
    document.body.classList.remove("sb-resizing");
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", stopDrag);
  }, [onPointerMove]);

  const startDrag = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      draggingRef.current = true;
      document.body.classList.add("sb-resizing");
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", stopDrag);
    },
    [onPointerMove, stopDrag],
  );

  useEffect(() => () => stopDrag(), [stopDrag]);

  const sidebarWidth = collapsed ? "0px" : `${width}px`;

  return (
    <div
      className={`app-layout${wide ? " app-layout-wide" : ""}${collapsed ? " app-layout-collapsed" : ""}`}
      style={{ "--sb-w": sidebarWidth } as CSSProperties}
    >
      {collapsed ? (
        <button
          type="button"
          className="sidebar-reopen"
          onClick={() => setCollapsed(false)}
          title="Show account panel"
          aria-label="Show account panel"
        >
          »
        </button>
      ) : (
        <div className="account-sidebar-dock">
          <AccountSidebar
            email={email}
            profile={profile}
            token={token}
            onLogout={onLogout}
            onCollapse={() => setCollapsed(true)}
            onOpenProjects={onOpenProjects}
          />
          <div
            className="sidebar-resizer"
            onPointerDown={startDrag}
            onDoubleClick={() => setWidth(DEFAULT_W)}
            role="separator"
            aria-orientation="vertical"
            title="Drag to resize · double-click to reset"
          />
        </div>
      )}
      <div className="app-main">
        <Header email={email} profile={profile} />
        <div className={`app-content${wide ? " app-content-wide" : ""}`}>
          <WorkflowPipeline
            current={pipelineStage}
            modules={pipelineModuleList}
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
