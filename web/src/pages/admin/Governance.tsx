import { useEffect, useState } from "react";
import { api } from "../../api";
import { ErrorBox, errText, fmtDate, useLoad } from "../../ui";
import { useSudo } from "./sudo";

interface Retention { unapproved_days: number; transcript_days: number; approved_years: number }
interface Preview { unapproved_meetings: number; transcripts: number; approved_meetings: number; held_meetings: number }
interface Hold { id: string; scope: string; target_id: string; target: string; reason: string; created_at: number; created_by: string; released_at: number | null }
interface Exp { id: string; status: string; size: number; counts: Record<string, number>; error: string; created_at: number; finished_at: number | null; expires_at: number | null }

const plural = (n: number, word: string) => n + " " + word + (n === 1 ? "" : "s");
const SCOPE: Record<string, string> = { district: "Whole district", school: "College", org: "Organization" };

export default function RecordsPanel({ base, district }: { base: string; district: boolean }) {
  return (
    <div className="stack">
      <RetentionCard base={base} />
      <HoldsCard base={base} district={district} />
      <ExportsCard base={base} district={district} />
      <RecordingsCard base={base} district={district} />
    </div>
  );
}

function RetentionCard({ base }: { base: string }) {
  const guard = useSudo();
  const data = useLoad(() => api.get<{ retention: Retention; preview: Preview; editable: boolean }>(base + "/retention"), [base]);
  const [form, setForm] = useState<Retention>({ unapproved_days: 0, transcript_days: 0, approved_years: 0 });
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { if (data.data) setForm(data.data.retention); }, [data.data]);

  async function save() {
    setMsg(""); setError("");
    try {
      data.setData(await guard(() => api.put(base + "/retention", form)));
      setMsg("Saved. The worker applies these rules every few hours.");
    } catch (e) {
      if (errText(e) !== "cancelled") setError(errText(e));
    }
  }

  const d = data.data;
  const edit = !!d?.editable;
  const field = (k: keyof Retention, label: string, unit: string) => (
    <label>{label}
      <div className="row">
        <input type="number" min={0} value={form[k]} disabled={!edit} style={{ maxWidth: 140 }}
          onChange={(e) => setForm({ ...form, [k]: Number(e.target.value) })} />
        <span className="sub">{form[k] ? unit : "keep forever"}</span>
      </div>
    </label>
  );
  return (
    <div className="card stack">
      <h2>Retention</h2>
      <p className="sub" style={{ margin: 0 }}>Set how long records are kept, following your district's records schedule. 0 keeps them forever. Records under a legal hold are never removed.</p>
      <div className="grid-2">
        {field("unapproved_days", "Delete meetings that were never approved after", "days")}
        {field("transcript_days", "Delete transcripts of approved minutes after", "days (the minutes stay)")}
        {field("approved_years", "Delete approved minutes after", "years")}
      </div>
      {d && (
        <div className="sub">Under these rules right now: {d.preview.unapproved_meetings} unapproved meeting{d.preview.unapproved_meetings === 1 ? "" : "s"},{" "}
          {d.preview.transcripts} transcript{d.preview.transcripts === 1 ? "" : "s"}, and {d.preview.approved_meetings} approved meeting{d.preview.approved_meetings === 1 ? "" : "s"} would be removed.
          {d.preview.held_meetings ? " " + d.preview.held_meetings + (d.preview.held_meetings === 1 ? " meeting is" : " meetings are") + " protected by a legal hold." : ""}</div>
      )}
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error || data.error} />
      {edit ? <div className="row"><button className="primary" onClick={() => void save()}>Save retention rules</button></div>
        : <p className="sub" style={{ margin: 0 }}>District IT sets retention for the whole district.</p>}
    </div>
  );
}

function HoldsCard({ base, district }: { base: string; district: boolean }) {
  const guard = useSudo();
  const data = useLoad(() => api.get<{ holds: Hold[]; can_manage: boolean }>(base + "/holds"), [base]);
  const orgs = useLoad(() => api.get<{ orgs: { id: string; name: string }[] }>(base + "/orgs"), [base]);
  const schools = useLoad(() => district ? api.get<{ schools: { id: string; name: string }[] }>(base + "/schools") : Promise.resolve({ schools: [] }), [base, district]);
  const [form, setForm] = useState({ scope: "org", target_id: "", reason: "" });
  const [error, setError] = useState("");
  const id = base.split("/").pop() || "";

  async function run(fn: () => Promise<unknown>) {
    setError("");
    try { await guard(fn); await data.reload(); } catch (e) { if (errText(e) !== "cancelled") setError(errText(e)); }
  }

  const targets = form.scope === "org" ? orgs.data?.orgs || [] : form.scope === "school" ? schools.data?.schools || [] : [];
  const active = (data.data?.holds || []).filter((h) => !h.released_at);
  const past = (data.data?.holds || []).filter((h) => h.released_at);
  return (
    <div className="card stack">
      <h2>Legal holds</h2>
      <p className="sub" style={{ margin: 0 }}>A hold keeps every meeting, transcript, and file it covers. Nothing under a hold can be deleted, by people or by retention rules, until it is released.</p>
      {active.length === 0 ? <div className="empty">No active holds.</div> : (
        <table>
          <thead><tr><th>Covers</th><th>Reason</th><th>Placed</th><th /></tr></thead>
          <tbody>
            {active.map((h) => (
              <tr key={h.id}>
                <td><strong>{h.target || h.target_id}</strong><div className="sub">{SCOPE[h.scope]}</div></td>
                <td>{h.reason}</td>
                <td className="sub">{fmtDate(h.created_at)}<div>{h.created_by}</div></td>
                <td>{data.data?.can_manage && <button onClick={() => { if (confirm("Release this hold? Retention rules will apply again.")) void run(() => api.post(base + "/holds/" + h.id + "/release")); }}>Release</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data.data?.can_manage && (
        <div className="grid-2">
          <label>Covers
            <select value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value, target_id: e.target.value === "district" ? id : "" })}>
              <option value="org">One organization</option>
              <option value="school">One college</option>
              <option value="district">The whole district</option>
            </select>
          </label>
          {form.scope !== "district" && (
            <label>{form.scope === "org" ? "Organization" : "College"}
              <select value={form.target_id} onChange={(e) => setForm({ ...form, target_id: e.target.value })}>
                <option value="">Choose…</option>
                {targets.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </label>
          )}
          <label style={{ gridColumn: "1 / -1" }}>Reason (case or request number)
            <input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="Public records request 2026-114" />
          </label>
          <div className="row"><button className="primary" disabled={!form.reason.trim() || !(form.target_id || form.scope === "district")}
            onClick={() => void run(async () => { await api.post(base + "/holds", { ...form, target_id: form.scope === "district" ? id : form.target_id }); setForm({ scope: "org", target_id: "", reason: "" }); })}>Place hold</button></div>
        </div>
      )}
      {past.length > 0 && <details><summary>Released holds ({past.length})</summary>
        {past.map((h) => <div key={h.id} className="sub" style={{ marginTop: 6 }}>{h.target || h.target_id}: {h.reason}. Released {fmtDate(h.released_at)}.</div>)}
      </details>}
      <ErrorBox error={error || data.error} />
    </div>
  );
}

function ExportsCard({ base, district }: { base: string; district: boolean }) {
  const guard = useSudo();
  const data = useLoad(() => api.get<{ exports: Exp[] }>(base + "/exports"), [base]);
  const [error, setError] = useState("");
  const busy = (data.data?.exports || []).some((x) => x.status === "queued" || x.status === "running");
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(() => void data.reload(), 4000);
    return () => window.clearInterval(t);
  }, [busy]);

  async function request() {
    setError("");
    try { await guard(() => api.post(base + "/exports")); await data.reload(); } catch (e) { if (errText(e) !== "cancelled") setError(errText(e)); }
  }

  async function download(x: Exp) {
    setError("");
    try {
      await guard(() => api.get(base + "/exports/" + x.id + "/download?check=1"));
      window.location.href = base + "/exports/" + x.id + "/download";
    } catch (e) {
      if (errText(e) !== "cancelled") setError(errText(e));
    }
  }

  const size = (n: number) => n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
  return (
    <div className="card stack">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Full data export</h2>
        <button className="primary" disabled={busy} onClick={() => void request()}>{busy ? "Preparing…" : "Export everything"}</button>
      </div>
      <p className="sub" style={{ margin: 0 }}>One ZIP with every organization {district ? "in the district" : "at the college"}: members, officer terms, meetings with minutes, motions and votes, transcripts, translations, funding, templates, and activity logs. AI keys and access tokens are left out. Downloads need your password and expire after 7 days.</p>
      {(data.data?.exports || []).length > 0 && (
        <table>
          <thead><tr><th>Requested</th><th>Status</th><th>Contents</th><th /></tr></thead>
          <tbody>
            {data.data!.exports.map((x) => (
              <tr key={x.id}>
                <td className="sub">{fmtDate(x.created_at)}</td>
                <td><span className={"chip " + (x.status === "done" ? "ok" : x.status === "error" ? "bad" : "")}>{x.status}</span>{x.error && <div className="sub">{x.error}</div>}</td>
                <td className="sub">{x.status === "done" ? plural(x.counts.orgs || 0, "organization") + ", " + plural(x.counts.meetings || 0, "meeting") + ", " + size(x.size) : ""}{x.expires_at && x.status === "done" ? " · until " + fmtDate(x.expires_at) : ""}</td>
                <td>{x.status === "done" && <button onClick={() => void download(x)}>Download</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <ErrorBox error={error || data.error} />
    </div>
  );
}

function RecordingsCard({ base, district }: { base: string; district: boolean }) {
  const guard = useSudo();
  const data = useLoad(() => api.get<{ count: number; total_bytes: number; organizations: number }>(base + "/recordings"), [base]);
  const [error, setError] = useState("");
  const d = data.data;
  const size = (n: number) => n >= 1073741824 ? (n / 1073741824).toFixed(1) + " GB" : (n / 1048576).toFixed(1) + " MB";

  async function download() {
    setError("");
    try {
      await guard(() => api.get(base + "/recordings.zip?check=1"));
      window.location.href = base + "/recordings.zip";
    } catch (e) {
      if (errText(e) !== "cancelled") setError(errText(e));
    }
  }

  return (
    <div className="card stack">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Recordings</h2>
        <button disabled={!d?.count} onClick={() => void download()}>Download all recordings</button>
      </div>
      <p className="sub" style={{ margin: 0 }}>Meeting recordings are kept out of the data export and automatic backups because of their size. Download them here as one
        ZIP, sorted into a folder per organization, with a list of every file. It needs your password.</p>
      {d && <div className="sub">{d.count ? plural(d.count, "recording") + " from " + plural(d.organizations, "organization") + " " + (district ? "in the district" : "at the college") + ", " + size(d.total_bytes) : "No recordings yet."}</div>}
      <ErrorBox error={error || data.error} />
    </div>
  );
}

