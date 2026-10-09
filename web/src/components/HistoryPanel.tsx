import { useEffect, useState } from "react";
import { api } from "../api";
import { ErrorBox, errText, fmtDate, useLoad } from "../ui";

interface Version { id: string; rev: number; source: string; kind: string; who: string; label: string; created_at: number; added: number; removed: number; current: boolean }
type Word = ["same" | "add" | "del", string];
interface Row { type: "same" | "add" | "del" | "change"; label: string; old_label?: string; text?: string; words?: Word[] }
interface Diff { rows: Row[]; added: number; removed: number }

function Line({ sign, label, children, cls }: { sign: string; label: string; children: React.ReactNode; cls: string }) {
  return (
    <div className={"diff-line " + cls}>
      <span className="diff-sign" aria-hidden="true">{sign}</span>
      <span className="diff-body"><span className="diff-label">{label}</span>{children}</span>
    </div>
  );
}

function DiffView({ diff, showSame }: { diff: Diff; showSame: boolean }) {
  const rows = diff.rows.filter((r) => showSame || r.type !== "same");
  if (rows.length === 0) return <div className="empty">{diff.rows.length ? "Nothing changed." : "This version is empty."}</div>;
  return (
    <div className="diff" role="region" aria-label="Changes">
      {rows.map((r, i) => {
        if (r.type === "same") return <Line key={i} sign=" " label={r.label} cls="same">{r.text}</Line>;
        if (r.type === "add") return <Line key={i} sign="+" label={r.label} cls="add"><span className="sr-only">Added: </span>{r.text}</Line>;
        if (r.type === "del") return <Line key={i} sign="-" label={r.label} cls="del"><span className="sr-only">Removed: </span>{r.text}</Line>;
        const words = r.words || [];
        return (
          <div key={i}>
            <Line sign="-" label={r.old_label || r.label} cls="del">
              <span className="sr-only">Before: </span>{words.filter((w) => w[0] !== "add").map((w, j) => w[0] === "del" ? <del key={j}>{w[1]}</del> : <span key={j}>{w[1]}</span>)}
            </Line>
            <Line sign="+" label={r.label} cls="add">
              <span className="sr-only">After: </span>{words.filter((w) => w[0] !== "del").map((w, j) => w[0] === "add" ? <ins key={j}>{w[1]}</ins> : <span key={j}>{w[1]}</span>)}
            </Line>
          </div>
        );
      })}
    </div>
  );
}

export default function HistoryPanel({ meetingId, dirty, onRestored }: { meetingId: string; dirty: boolean; onRestored: () => Promise<void> }) {
  const base = "/api/meetings/" + meetingId + "/history";
  const list = useLoad(() => api.get<{ versions: Version[]; draft_rev: number; can_restore: boolean }>(base), [base]);
  const [pick, setPick] = useState("");
  const [against, setAgainst] = useState<"previous" | "current">("previous");
  const [showSame, setShowSame] = useState(false);
  const [diff, setDiff] = useState<Diff | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const versions = list.data?.versions || [];
  const at = versions.findIndex((v) => v.id === pick);
  const chosen = at >= 0 ? versions[at] : null;

  useEffect(() => { if (!pick && versions.length) setPick(versions[0].id); }, [versions, pick]);
  useEffect(() => {
    if (!chosen) return;
    const older = versions[at + 1];
    const q = against === "current" ? "?base=" + chosen.id + "&head=current" : "?base=" + (older ? older.id : "empty") + "&head=" + chosen.id;
    setDiff(null);
    api.get<Diff>(base + "/compare" + q).then(setDiff).catch((e) => setError(errText(e)));
  }, [chosen?.id, against, base]);

  async function restore(v: Version) {
    const warn = dirty ? " Your unsaved edits will be replaced." : "";
    if (!confirm("Restore the version from " + fmtDate(v.created_at) + "? The current draft stays in the history, so you can switch back." + warn)) return;
    setBusy(true); setError("");
    try {
      await api.post(base + "/" + v.id + "/restore");
      await onRestored();
      setPick("");
      await list.reload();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="history">
      <div className="card history-list">
        <h2>Versions</h2>
        <p className="sub" style={{ marginTop: 0 }}>Every save, AI draft, and restore is kept. Pick one to see what changed.</p>
        <ErrorBox error={list.error} />
        {versions.length === 0 && !list.loading && <div className="empty">No versions yet. One is saved each time the AI drafts or someone saves.</div>}
        <ol className="history-items">
          {versions.map((v) => (
            <li key={v.id}>
              <button className={"history-item" + (v.id === pick ? " on" : "")} aria-pressed={v.id === pick} onClick={() => setPick(v.id)}>
                <span className="row spread" style={{ flexWrap: "nowrap" }}>
                  <strong>{v.kind}{v.current ? " · current" : ""}</strong>
                  <span className="diff-stat"><span className="plus">+{v.added}</span> <span className="minus">-{v.removed}</span></span>
                </span>
                <span className="sub">{v.who ? v.who + " · " : ""}{fmtDate(v.created_at)}</span>
                {v.label && <span className="sub">{v.label}</span>}
              </button>
            </li>
          ))}
        </ol>
      </div>
      <div className="card stack">
        {chosen ? (
          <>
            <div className="row spread">
              <div>
                <h2 style={{ margin: 0 }}>{chosen.kind}{chosen.who ? " by " + chosen.who : ""}</h2>
                <div className="sub">{fmtDate(chosen.created_at)}</div>
              </div>
              {list.data?.can_restore && !chosen.current && (
                <button className="primary" disabled={busy} onClick={() => void restore(chosen)}>{busy ? "Restoring…" : "Restore this version"}</button>
              )}
            </div>
            <div className="row">
              <div className="tabs" role="group" aria-label="Compare with" style={{ margin: 0 }}>
                <button className={against === "previous" ? "on" : ""} aria-pressed={against === "previous"} onClick={() => setAgainst("previous")}>Changes in this version</button>
                <button className={against === "current" ? "on" : ""} aria-pressed={against === "current"} disabled={chosen.current} onClick={() => setAgainst("current")}>Compare with the current draft</button>
              </div>
              <label className="row" style={{ gap: 6 }}><input type="checkbox" checked={showSame} onChange={(e) => setShowSame(e.target.checked)} /> Show unchanged lines</label>
            </div>
            {against === "current" && <p className="sub" style={{ margin: 0 }}>Red is this older version, green is the draft now.</p>}
            <ErrorBox error={error} />
            {diff ? (
              <>
                <div className="diff-stat"><span className="plus">+{diff.added} added</span> <span className="minus">-{diff.removed} removed</span></div>
                <DiffView diff={diff} showSame={showSame} />
              </>
            ) : <div className="sub">Loading…</div>}
          </>
        ) : <div className="empty">Pick a version.</div>}
      </div>
    </div>
  );
}
