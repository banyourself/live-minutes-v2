import { useState } from "react";
import { api, type Meeting } from "../api";
import { ErrorBox, errText, fmtDate, useLoad } from "../ui";

interface Reference { id: string; label: string; filename: string; chars: number; lines: number; created_at: number }
interface References { references: Reference[]; sources: string[]; max: number }

export default function ReferencePanel({ meeting, canEdit }: { meeting: Meeting; canEdit: boolean }) {
  const base = "/api/meetings/" + meeting.id + "/references";
  const list = useLoad(() => api.get<References>(base), [base]);
  const [label, setLabel] = useState("Otter");
  const [paste, setPaste] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const data = list.data;
  const full = !!data && data.references.length >= data.max;
  const locked = meeting.status === "approved";

  async function add(text: string, filename: string) {
    setBusy(true); setMsg(""); setError("");
    try {
      await api.post(base, { label, filename, text });
      setPaste("");
      setMsg("Added. The next draft checks names, numbers, motions, and votes against it.");
      await list.reload();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true); setMsg(""); setError("");
    try {
      await api.del(base + "/" + id);
      await list.reload();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card stack">
      <h2>Reference transcript</h2>
      <p className="sub">Add the same meeting's transcript from another app, such as Otter, Fireflies, Fathom, tl;dv, Read.ai, Teams, or Meet.
        The AI drafts from the main transcript and uses this one only to check names, numbers, motions, and votes. Where they
        disagree, it marks the item [verify] for you. Export a .txt, .srt, or .vtt file from the other app.</p>
      {(data?.references || []).map((r) => (
        <div key={r.id} className="row spread motion">
          <span>{r.label}<br /><span className="sub">{r.filename || "Pasted text"} · {r.lines} lines · {fmtDate(r.created_at)}</span></span>
          {canEdit && <button className="danger" disabled={busy} onClick={() => void remove(r.id)}>Remove</button>}
        </div>
      ))}
      {canEdit && !locked && !full && (
        <>
          <label>From
            <select value={label} onChange={(e) => setLabel(e.target.value)}>
              {(data?.sources || ["Otter"]).map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
          <input type="file" accept=".txt,.srt,.vtt,.md" disabled={busy} aria-label="Reference transcript file"
            onChange={async (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) await add(await f.text(), f.name); }} />
          <textarea aria-label="Reference transcript text" placeholder="…or paste the other app's transcript here" value={paste}
            onChange={(e) => setPaste(e.target.value)} />
          <div className="row">
            <button disabled={busy || !paste.trim()} onClick={() => void add(paste, "")}>Add pasted text</button>
          </div>
        </>
      )}
      {full && <p className="sub">This meeting has the most reference transcripts allowed. Remove one to add another.</p>}
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error || list.error} />
    </div>
  );
}
