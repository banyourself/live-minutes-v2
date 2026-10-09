import { useEffect, useState } from "react";
import { api } from "../../api";
import { ErrorBox, errText, fmtDate, useLoad } from "../../ui";
import { useSudo } from "./sudo";

interface Run { id: string; status: string; trigger: string; object_key: string; size: number; error: string; created_at: number; finished_at: number | null }
interface Backup {
  id: string; name: string; kind: string; schedule: string; data_kinds: string[]; active: boolean;
  config: Record<string, string>; created_at: number; last_run_at: number | null; runs: Run[];
}

const SCHEDULES: [string, string][] = [["daily", "Every day"], ["weekly", "Every week"], ["manual", "Only when I start it"]];
const PROVIDERS: [string, string, string][] = [
  ["aws", "Amazon S3", ""], ["r2", "Cloudflare R2", "https://ACCOUNT_ID.r2.cloudflarestorage.com"],
  ["b2", "Backblaze B2", "https://s3.us-west-004.backblazeb2.com"], ["wasabi", "Wasabi", "https://s3.us-west-1.wasabisys.com"],
  ["other", "Other S3-compatible (MinIO, campus storage)", "https://"]
];

export default function BackupsPanel({ base, district }: { base: string; district: boolean }) {
  const guard = useSudo();
  const data = useLoad(() => api.get<{ backups: Backup[]; data_kinds: { id: string; label: string }[] }>(base + "/backups"), [base]);
  const [adding, setAdding] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const running = (data.data?.backups || []).some((b) => b.runs.some((r) => r.status === "queued" || r.status === "running"));
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => void data.reload(), 4000);
    return () => window.clearInterval(t);
  }, [running]);

  async function run(fn: () => Promise<unknown>, done: string) {
    setMsg(""); setError("");
    try { await guard(fn); setMsg(done); await data.reload(); } catch (e) { if (errText(e) !== "cancelled") setError(errText(e)); }
  }

  const kinds = data.data?.data_kinds || [];
  const label = (id: string) => kinds.find((k) => k.id === id)?.label || id;
  return (
    <div className="stack">
      <div className="card stack">
        <div className="row spread">
          <h2 style={{ margin: 0 }}>Backups</h2>
          {!adding && <button className="primary" onClick={() => setAdding(true)}>Connect storage</button>}
        </div>
        <p className="sub" style={{ margin: 0 }}>Send copies of {district ? "the district's" : "the college's"} records to storage you control, on a schedule. Choose which kinds of data each
          destination gets. Copies are ZIP files in the same format as the full export. They stay under your storage's own retention rules, so set lifecycle rules there
          if your records schedule requires it. Keys are encrypted and never shown again.</p>
        {msg && <div className="alert ok" role="status">{msg}</div>}
        <ErrorBox error={error || data.error} />
        {(data.data?.backups || []).length === 0 && !adding && <div className="empty">No backup storage connected.</div>}
      </div>
      {adding && <AddForm kinds={kinds} onCancel={() => setAdding(false)}
        onSave={(body) => run(async () => { await api.post(base + "/backups", body); setAdding(false); }, "Connected. Live Minutes wrote a test file to check access.")} />}
      {(data.data?.backups || []).map((b) => (
        <div key={b.id} className="card stack">
          <div className="row spread">
            <div>
              <h2 style={{ margin: 0 }}>{b.name}</h2>
              <div className="sub">{b.kind === "s3" ? "S3 bucket " + b.config.bucket + (b.config.endpoint ? " at " + b.config.endpoint : "") + " · key ending " + b.config.key_hint
                : "Azure container " + b.config.container_url}{b.config.prefix ? " · folder " + b.config.prefix : ""}</div>
            </div>
            <span className={"chip " + (b.active ? "ok" : "")}>{b.active ? "On" : "Paused"}</span>
          </div>
          <div className="grid-2">
            <label>Schedule
              <select value={b.schedule} onChange={(e) => void run(() => api.patch(base + "/backups/" + b.id, { schedule: e.target.value }), "Schedule saved.")}>
                {SCHEDULES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </label>
            <div>
              <div className="lbl">Data in each copy</div>
              {kinds.map((k) => (
                <label key={k.id} className="row" style={{ textTransform: "none", letterSpacing: "normal" }}>
                  <input type="checkbox" checked={b.data_kinds.includes(k.id)} onChange={(e) => {
                    const next = e.target.checked ? [...b.data_kinds, k.id] : b.data_kinds.filter((x) => x !== k.id);
                    void run(() => api.patch(base + "/backups/" + b.id, { data_kinds: next }), "Saved.");
                  }} /> {k.label}
                </label>
              ))}
            </div>
          </div>
          <div className="row">
            <button className="primary" onClick={() => void run(() => api.post(base + "/backups/" + b.id + "/run"), "Backup started.")}>Back up now</button>
            <button onClick={() => void run(() => api.post(base + "/backups/" + b.id + "/test"), "Connection works.")}>Test connection</button>
            <button onClick={() => void run(() => api.patch(base + "/backups/" + b.id, { active: !b.active }), b.active ? "Paused." : "Turned on.")}>{b.active ? "Pause" : "Turn on"}</button>
            <button className="danger" onClick={() => { if (confirm("Disconnect " + b.name + "? Copies already in your storage stay there.")) void run(() => api.del(base + "/backups/" + b.id), "Disconnected."); }}>Disconnect</button>
          </div>
          {b.runs.length > 0 && (
            <table>
              <caption className="sub" style={{ textAlign: "left" }}>Recent copies</caption>
              <thead><tr><th>Started</th><th>Status</th><th>File</th></tr></thead>
              <tbody>
                {b.runs.map((r) => (
                  <tr key={r.id}>
                    <td className="sub">{fmtDate(r.created_at)}<div>{r.trigger === "manual" ? "started by hand" : "scheduled"}</div></td>
                    <td><span className={"chip " + (r.status === "done" ? "ok" : r.status === "error" ? "bad" : "")}>{r.status}</span>{r.error && <div className="sub">{r.error}</div>}</td>
                    <td className="mono" style={{ wordBreak: "break-all" }}>{r.object_key}{r.size ? " · " + Math.max(1, Math.round(r.size / 1024)) + " KB" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="sub" style={{ margin: 0 }}>Each copy includes: {b.data_kinds.map(label).join(", ")}.</p>
        </div>
      ))}
    </div>
  );
}

function AddForm({ kinds, onSave, onCancel }: { kinds: { id: string; label: string }[]; onSave: (b: object) => Promise<void>; onCancel: () => void }) {
  const [kind, setKind] = useState("s3");
  const [provider, setProvider] = useState("aws");
  const [f, setF] = useState({ name: "", endpoint: "", bucket: "", region: "", prefix: "", access_key_id: "", secret_access_key: "",
    container_url: "", sas_token: "", schedule: "weekly" });
  const [chosen, setChosen] = useState<string[]>(["minutes", "members", "funding", "activity"]);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  return (
    <div className="card stack">
      <h2>Connect storage</h2>
      <div className="grid-2">
        <label>Name<input value={f.name} onChange={set("name")} placeholder="District records bucket" /></label>
        <label>Type
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="s3">S3-compatible storage</option>
            <option value="azure">Azure Blob Storage</option>
          </select>
        </label>
        {kind === "s3" ? (
          <>
            <label>Provider
              <select value={provider} onChange={(e) => { setProvider(e.target.value); setF({ ...f, endpoint: PROVIDERS.find((p) => p[0] === e.target.value)?.[2] || "" }); }}>
                {PROVIDERS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </label>
            {provider !== "aws" && <label>Endpoint URL<input value={f.endpoint} onChange={set("endpoint")} className="mono" /></label>}
            <label>Bucket<input value={f.bucket} onChange={set("bucket")} className="mono" /></label>
            <label>Region<input value={f.region} onChange={set("region")} placeholder={provider === "r2" ? "auto" : "us-west-2"} className="mono" /></label>
            <label>Access key ID<input value={f.access_key_id} onChange={set("access_key_id")} className="mono" autoComplete="off" /></label>
            <label>Secret access key<input type="password" value={f.secret_access_key} onChange={set("secret_access_key")} className="mono" autoComplete="new-password" data-1p-ignore data-lpignore="true" data-bwignore /></label>
          </>
        ) : (
          <>
            <label>Container URL<input value={f.container_url} onChange={set("container_url")} placeholder="https://account.blob.core.windows.net/minutes-backups" className="mono" /></label>
            <label>Container SAS token (create and write only)<input type="password" value={f.sas_token} onChange={set("sas_token")} className="mono" autoComplete="new-password" data-1p-ignore data-lpignore="true" data-bwignore /></label>
          </>
        )}
        <label>Folder inside the storage (optional)<input value={f.prefix} onChange={set("prefix")} placeholder="live-minutes-backups" className="mono" /></label>
        <label>Schedule
          <select value={f.schedule} onChange={set("schedule")}>{SCHEDULES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        </label>
      </div>
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="lbl">Data in each copy</legend>
        {kinds.map((k) => (
          <label key={k.id} className="row" style={{ textTransform: "none", letterSpacing: "normal" }}>
            <input type="checkbox" checked={chosen.includes(k.id)} onChange={(e) => setChosen(e.target.checked ? [...chosen, k.id] : chosen.filter((x) => x !== k.id))} /> {k.label}
          </label>
        ))}
      </fieldset>
      <p className="sub" style={{ margin: 0 }}>Give Live Minutes a key that can only write to this bucket or container. It never needs to read or delete.</p>
      <div className="row">
        <button className="primary" disabled={!f.name.trim() || !chosen.length} onClick={() => void onSave({ ...f, kind, data_kinds: chosen, region: f.region === "auto" ? "auto" : f.region })}>Connect and test</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
