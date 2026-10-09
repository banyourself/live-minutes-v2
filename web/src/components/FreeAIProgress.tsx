import { cancelRun, dismissRun, minutesLeft, useFreeRuns, useSmoothProgress, type FreeRun } from "../freeai";

export function ProgressBar({ run, compact = false }: { run: FreeRun; compact?: boolean }) {
  const shown = useSmoothProgress(run);
  const pct = Math.round(shown * 100);
  const phase = run.status === "queued"
    ? (run.position > 1 ? "Number " + run.position + " in line" : "Starting soon")
    : run.status === "done" ? "Done" : run.status === "error" ? "Stopped"
    : run.phase === "writing" ? "Writing" : "Reading the material";
  return (
    <div className={"ai-progress" + (compact ? " compact" : "")}>
      <div className="ai-progress-head">
        <span>{phase}{run.model ? " · " + run.model : ""}</span>
        <span>{run.status === "done" ? "100%" : run.status === "error" ? "" : pct + "%"}</span>
      </div>
      <div className="ai-progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}
        aria-label={run.label + " progress"}>
        <div className={"ai-progress-fill" + (run.status === "queued" ? " waiting" : "")} style={{ width: Math.max(2, pct) + "%" }} />
      </div>
      {run.status !== "done" && run.status !== "error" && <div className="sub">{minutesLeft(run.eta_seconds)}</div>}
      {run.status === "error" && <div className="sub">{run.error || "The free AI could not finish."}</div>}
    </div>
  );
}

export default function FreeAIProgress() {
  const runs = useFreeRuns();
  if (!runs.length) return null;
  return (
    <div className="ai-progress-dock" role="status" aria-live="polite">
      {runs.map((run) => (
        <div key={run.id} className="ai-progress-card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <strong>{run.label} with the free AI</strong>
            {run.status === "queued" && <button className="link" onClick={() => void cancelRun(run.id)}>Cancel</button>}
            {(run.status === "done" || run.status === "error") && <button className="link" aria-label="Close" onClick={() => dismissRun(run.id)}>✕</button>}
          </div>
          <ProgressBar run={run} />
          {run.status !== "done" && run.status !== "error" && <div className="sub">You can keep working on this page while it runs. It runs on the Live Minutes server, so it is free but slower.</div>}
        </div>
      ))}
    </div>
  );
}
