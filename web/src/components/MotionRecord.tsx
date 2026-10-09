import { useEffect, useState } from "react";
import { useExamples } from "../examples";
import { api } from "../api";
import { ErrorBox, errText, fmtClock, useLoad } from "../ui";

export interface SavedMotion {
  id?: string; t: number | null; under: string; text: string; mover: string; seconder: string;
  method: string; result: string; votes: Record<string, string>; tally?: Record<string, number>;
}
interface RecordData { motions: SavedMotion[]; detected: SavedMotion[]; saved: boolean; editable: boolean }

const METHODS: [string, string][] = [["voice", "Voice vote"], ["roll_call", "Roll call"], ["hands", "Show of hands"],
  ["consent", "Consent agenda"], ["unanimous", "Unanimous consent"]];
const RESULTS: [string, string][] = [["", "No result yet"], ["passed", "Passed"], ["failed", "Failed"], ["tabled", "Tabled"], ["withdrawn", "Withdrawn"]];
const VOTES = ["yes", "no", "abstain", "absent", "present"];

export default function MotionRecord({ meetingId }: { meetingId: string }) {
  const ex = useExamples();
  const data = useLoad(() => api.get<RecordData>("/api/meetings/" + meetingId + "/record"), [meetingId]);
  const [rows, setRows] = useState<SavedMotion[]>([]);
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (data.data) { setRows(data.data.motions); setDirty(false); }
  }, [data.data]);

  const d = data.data;
  if (!d) return <ErrorBox error={data.error} />;
  const edit = d.editable;
  const change = (i: number, patch: Partial<SavedMotion>) => { setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r))); setDirty(true); };

  async function save() {
    setError(""); setMsg("");
    try {
      const r = await api.put<{ motions: SavedMotion[] }>("/api/meetings/" + meetingId + "/record", { motions: rows });
      setRows(r.motions); setDirty(false); setMsg("Motions and votes saved.");
    } catch (e) {
      setError(errText(e));
    }
  }

  return (
    <div className="card stack">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Motions and votes</h2>
        {edit && (
          <div className="row">
            {d.detected.length > 0 && (
              <button onClick={() => { if (!rows.length || confirm("Replace the list below with the motions detected in the transcript?")) { setRows(d.detected); setDirty(true); } }}>
                Use detected motions ({d.detected.length})
              </button>
            )}
            <button onClick={() => { setRows([...rows, { t: null, under: "", text: "", mover: "", seconder: "", method: "voice", result: "", votes: {} }]); setDirty(true); }}>Add a motion</button>
            <button className="primary" disabled={!dirty} onClick={() => void save()}>Save</button>
          </div>
        )}
      </div>
      <p className="sub" style={{ margin: 0 }}>
        This is the official record of motions and how each person voted. It feeds the voting record and funding requests.
        {!d.saved && d.detected.length > 0 && edit ? " Nothing is saved yet; start from the detected motions and correct them." : ""}
      </p>
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error} />
      {rows.length === 0 ? <div className="empty">No motions recorded.</div> : rows.map((m, i) => (
        <div key={m.id || "new-" + i} className="motion stack">
          <div className="row spread">
            <span className="lbl" style={{ margin: 0 }}>Motion {i + 1}{m.t !== null ? " · " + fmtClock(m.t) : ""}</span>
            {edit && <button className="danger" onClick={() => { setRows(rows.filter((_, j) => j !== i)); setDirty(true); }}>Remove</button>}
          </div>
          {edit ? (
            <>
              <label>Motion<textarea rows={2} value={m.text} onChange={(e) => change(i, { text: e.target.value })} /></label>
              <div className="grid-2">
                <label>Agenda item<input value={m.under} onChange={(e) => change(i, { under: e.target.value })} placeholder={ex.agendaItem} /></label>
                <label>Result
                  <select value={m.result} onChange={(e) => change(i, { result: e.target.value })}>{RESULTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
                </label>
                <label>Moved by<input value={m.mover} onChange={(e) => change(i, { mover: e.target.value })} /></label>
                <label>Seconded by<input value={m.seconder} onChange={(e) => change(i, { seconder: e.target.value })} /></label>
                <label>How it was voted on
                  <select value={m.method} onChange={(e) => change(i, { method: e.target.value })}>{METHODS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
                </label>
              </div>
              <VotesEditor votes={m.votes} onChange={(votes) => change(i, { votes })} />
            </>
          ) : (
            <>
              <div>{m.text}</div>
              <div className="sub">
                {m.under ? m.under + " · " : ""}Moved by {m.mover || "?"}{m.seconder ? ", seconded by " + m.seconder : ""} ·{" "}
                {METHODS.find((x) => x[0] === m.method)?.[1]} · {RESULTS.find((x) => x[0] === m.result)?.[1]}
              </div>
              {Object.keys(m.votes).length > 0 && (
                <div className="chips">{Object.entries(m.votes).map(([who, v]) => <span key={who} className={"chip " + (v === "yes" ? "ok" : v === "no" ? "bad" : "")}>{who}: {v}</span>)}</div>
              )}
            </>
          )}
        </div>
      ))}
    </div>
  );
}

function VotesEditor({ votes, onChange }: { votes: Record<string, string>; onChange: (v: Record<string, string>) => void }) {
  const [who, setWho] = useState("");
  const entries = Object.entries(votes);
  return (
    <div>
      <div className="lbl">Votes by person (roll call)</div>
      {entries.length > 0 && (
        <table>
          <tbody>
            {entries.map(([name, v]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>
                  <select value={v} onChange={(e) => onChange({ ...votes, [name]: e.target.value })}>{VOTES.map((x) => <option key={x}>{x}</option>)}</select>
                </td>
                <td><button onClick={() => { const next = { ...votes }; delete next[name]; onChange(next); }}>Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="row" style={{ marginTop: 6 }}>
        <input value={who} onChange={(e) => setWho(e.target.value)} aria-label="Name of the person voting" placeholder="Name" style={{ maxWidth: 260 }} />
        <button disabled={!who.trim()} onClick={() => { onChange({ ...votes, [who.trim()]: "yes" }); setWho(""); }}>Add vote</button>
      </div>
    </div>
  );
}
