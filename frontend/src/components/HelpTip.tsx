import { useEffect, useId, useRef, useState } from "react";
import { guideUrl, TERRAIN_HELP, type TerrainHelpKey } from "../lib/terrainHelp";

interface HelpTipProps {
  topic: TerrainHelpKey;
  /** Optional override for the trigger label (default ⓘ). */
  label?: string;
  className?: string;
}

/** Small info control — click to open a short engineering explanation. */
export function HelpTip({ topic, label = "i", className }: HelpTipProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLSpanElement>(null);
  const panelId = useId();
  const help = TERRAIN_HELP[topic];

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent | TouchEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <span className={["help-tip", className].filter(Boolean).join(" ")} ref={rootRef}>
      <button
        type="button"
        className="help-tip-trigger"
        aria-label={`About ${help.title}`}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        {label}
      </button>
      {open ? (
        <div className="help-tip-panel" id={panelId} role="dialog" aria-labelledby={`${panelId}-title`}>
          <p className="help-tip-title" id={`${panelId}-title`}>
            {help.title}
          </p>
          {help.body.split("\n\n").map((para, i) => (
            <p key={i} className="help-tip-body">
              {para}
            </p>
          ))}
          <a
            className="help-tip-link"
            href={guideUrl(help.slug)}
            target="_blank"
            rel="noopener noreferrer"
          >
            Read full guide →
          </a>
        </div>
      ) : null}
    </span>
  );
}
