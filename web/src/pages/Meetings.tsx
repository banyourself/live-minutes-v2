import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, can, type MeetingSummary, type Series } from "../api";
import { useSession } from "../session";
import { ErrorBox, errText, fileNo, fmtDate, StatusBadge, useLoad } from "../ui";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function when(ts: number | null) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function ZoomLink({ url }: { url: string }) {
  if (!url) return null;
  return <a className="btn sm" href={url} target="_blank" rel="noopener noreferrer">Join on Zoom</a>;
}

export default function Meetings() {
  const { org } = useSession();
  const navigate = useNavigate();
  const secretary = can(org!.role, "secretary");
  const owner = can(org!.role, "owner");
  const base = "/api/orgs/" + org!.id;
  const list = useLoad(() => api.get<{ meetings: MeetingSummary[] }>(base + "/meetings"), [base]);
  const cal = useLoad(() => api.get<{ meetings: MeetingSummary[]; series: Series[] }>(base + "/calendar"), [base]);
  const [view, setView] = useState<"list" | "month">("list");
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const all = list.data?.meetings || [];
  const now = Date.now() / 1000;
  const files = all.filter((m) => m.status !== "scheduled" || (m.scheduled_at || 0) <= now);
  const upcoming = (cal.data?.meetings || []).filter((m) => m.status === "scheduled" && (m.scheduled_at || 0) > now).slice(0, 12);

  async function run(fn: () => Promise<unknown>) {
    setError("");
    try {
      await fn();
      await Promise.all([list.reload(), cal.reload()]);
    } catch (e) {
      setError(errText(e));
    }
  }

  function toggle(id: string) {
    setPicked((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  }

  function removePicked() {
    const chosen = files.filter((m) => picked.has(m.id));
    if (!chosen.length) return;
    const approved = chosen.filter((m) => m.status === "approved").length;
    const what = chosen.length === 1 ? "\"" + chosen[0].title + "\"" : chosen.length + " meetings";
    const warn = approved ? " " + (approved === 1 ? "One of them has" : approved + " of them have") + " approved minutes." : "";
    if (!confirm("Delete " + what + " with their transcripts, drafts, and files?" + warn + " This cannot be undone.")) return;
    void run(async () => {
      try {
        for (const m of chosen) await api.del("/api/meetings/" + m.id);
      } finally {
        setPicked(new Set());
      }
    });
  }

  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker">Minutes index</div>
          <h1>Meetings</h1>
          <p className="sub">Drafts update live from captions, recordings, and chat. Every draft is reviewed before approval.</p>
        </div>
        {secretary && (
          <div className="row">
            <Link className="btn" to="/meetings/upload">Upload a past meeting</Link>
            <Link className="btn primary" to="/meetings/new">New meeting</Link>
          </div>
        )}
      </div>
      <div className="tabs" role="group" aria-label="View">
        <button className={view === "list" ? "on" : ""} aria-pressed={view === "list"} onClick={() => setView("list")}>List</button>
        <button className={view === "month" ? "on" : ""} aria-pressed={view === "month"} onClick={() => setView("month")}>Calendar</button>
      </div>
      <ErrorBox error={error || list.error || cal.error} />
      {view === "month" ? <Month base={base} /> : (
        <>
          {upcoming.length > 0 && (
            <div className="card">
              <h2>Upcoming</h2>
              <table>
                <thead><tr><th>When</th><th>Meeting</th><th /></tr></thead>
                <tbody>
                  {upcoming.map((m) => (
                    <tr key={m.id}>
                      <td className="mono">{when(m.scheduled_at)}</td>
                      <td><Link to={"/meetings/" + m.id}>{m.title}</Link>{m.series_id && <span className="chip" style={{ marginLeft: 8 }}>Repeats</span>}
                        {m.sample && <span className="chip warn" style={{ marginLeft: 8 }}>Sample</span>}</td>
                      <td className="row" style={{ justifyContent: "flex-end" }}>
                        <ZoomLink url={m.zoom_url} />
                        {secretary && <button onClick={() => void run(async () => { await api.post("/api/meetings/" + m.id + "/start"); navigate("/meetings/" + m.id); })}>Start</button>}
                        {secretary && <button className="danger" onClick={() => { if (confirm("Cancel " + m.title + " on " + when(m.scheduled_at) + "?")) void run(() => api.post("/api/meetings/" + m.id + "/cancel")); }}>Cancel</button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {(cal.data?.series || []).length > 0 && <SeriesCard series={cal.data!.series} base={base} secretary={secretary} run={run} />}
          <div className="card">
            {(upcoming.length > 0 || (owner && picked.size > 0)) && (
              <div className="row" style={{ justifyContent: "space-between" }}>
                <h2>Minutes files</h2>
                {owner && picked.size > 0 && (
                  <div className="row">
                    <button onClick={() => setPicked(new Set())}>Clear</button>
                    <button className="danger" onClick={removePicked}>Delete {picked.size === 1 ? "1 meeting" : picked.size + " meetings"}</button>
                  </div>
                )}
              </div>
            )}
            {list.loading ? <div className="empty">Loading…</div> : files.length === 0 ? (
              <div className="empty">
                No meetings yet.{secretary ? " Start one with New meeting, or make sample meetings below to try things out." : ""}
              </div>
            ) : (
              <table>
                <thead><tr>{owner && <th style={{ width: 32 }}>
                  <input type="checkbox" aria-label="Select all meetings" checked={files.length > 0 && files.every((m) => picked.has(m.id))}
                    onChange={(e) => setPicked(e.target.checked ? new Set(files.map((m) => m.id)) : new Set())} /></th>}<th>File no.</th><th>Meeting</th><th>Date</th><th>Mode</th><th>Status</th><th>Opened</th></tr></thead>
                <tbody>
                  {files.map((m) => (
                    <tr key={m.id}>
                      {owner && <td><input type="checkbox" aria-label={"Select " + m.title} checked={picked.has(m.id)} onChange={() => toggle(m.id)} /></td>}
                      <td className="mono">{fileNo(m.created_at, m.id)}</td>
                      <td><Link to={"/meetings/" + m.id}>{m.title}</Link>
                        <span className="chips" style={{ marginLeft: 8 }}>
                          {m.sample && <span className="chip warn">Sample</span>}
                          {m.status === "scheduled" && <span className="chip">Never started</span>}
                          {m.has_recording && <span className="chip">Recording</span>}
                        </span>
                      </td>
                      <td>{m.meeting_date}</td>
                      <td>{m.run_mode === "live" ? "Live" : "After meeting"}</td>
                      <td><StatusBadge status={m.status} /></td>
                      <td className="sub">{fmtDate(m.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          {secretary && <Samples base={base} solo={!!org!.personal} onChange={() => run(async () => undefined)} />}
        </>
      )}
    </>
  );
}

function Samples({ base, onChange, solo }: { base: string; onChange: () => Promise<void>; solo: boolean }) {
  const info = useLoad(() => api.get<{ count: number; max: number }>(base + "/sample-meetings"), [base]);
  const [count, setCount] = useState(5);
  const [length, setLength] = useState(solo ? "short" : "standard");
  const [mins, setMins] = useState(60);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const have = info.data?.count || 0;

  async function act(label: string, fn: () => Promise<string>) {
    setBusy(label); setError(""); setMsg("");
    try { setMsg(await fn()); await Promise.all([info.reload(), onChange()]); } catch (e) { setError(errText(e)); } finally { setBusy(""); }
  }

  return (
    <div className="card stack">
      <h2>Sample meetings</h2>
      {solo ? (
        <p className="sub" style={{ margin: 0 }}>Make realistic practice meetings to try Live Minutes without a real one. Each is different: team
          check-ins, project planning, volunteer and neighborhood groups, study groups, and book clubs, with made-up people, updates, decisions,
          action items, side talk, audio problems, and misheard names in the captions. One is upcoming, one is in session, and the rest are
          finished, some with a draft already written. They use your default template, are marked Sample, and only you can see them.</p>
      ) : (
      <p className="sub" style={{ margin: 0 }}>Make realistic practice meetings to try Live Minutes without a real one. Each is different: regular, special,
        budget, workshop, and appointment meetings with made-up members, funding requests, motions that pass, fail, or get tabled, roll-call votes,
        late arrivals, guest presentations, committee reports, public comment, off-topic chatter, audio problems, and misheard names in the captions.
        Choose how long they run, from short check-ins to two-hour sessions. Every meeting has its own topic and title, and no two have the same
        transcript. One is upcoming, one is in session, and the rest are finished, some with a draft already written. They use your default
        template, are marked Sample, and are only visible to your organization.</p>
      )}
      <div className="row">
        <label className="row" style={{ gap: 8 }}>How many
          <select value={count} onChange={(e) => setCount(Number(e.target.value))} style={{ width: "auto" }}>
            {[1, 3, 5, 8, 10].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="row" style={{ gap: 8 }}>Length
          <select value={length} onChange={(e) => setLength(e.target.value)} style={{ width: "auto" }}>
            <option value="short">Short (about 15 minutes)</option>
            {solo ? <option value="long">Longer (about 25 minutes)</option> : (
              <>
                <option value="standard">Standard (about 45 minutes)</option>
                <option value="long">Long (about 90 minutes)</option>
                <option value="mixed">A mix of lengths</option>
                <option value="custom">Choose minutes</option>
              </>
            )}
          </select>
        </label>
        {length === "custom" && (
          <label className="row" style={{ gap: 8 }}>Minutes
            <input type="number" min={10} max={120} step={5} value={mins} onChange={(e) => setMins(Number(e.target.value))} style={{ width: 90 }} />
          </label>
        )}
        <button className="primary" disabled={!!busy || have + count > (info.data?.max || 40) || (length === "custom" && !(mins >= 10 && mins <= 120))}
          onClick={() => void act("make", async () => {
            const r = await api.post<{ meetings: { id: string; minutes: number }[] }>(base + "/sample-meetings", { count, length, minutes: length === "custom" ? mins : null });
            const total = r.meetings.reduce((n, m) => n + m.minutes, 0);
            const n = r.meetings.length;
            return n === 1 ? "1 sample meeting made, about " + total + " minutes long." : n + " sample meetings made, about " + total + " minutes of meetings in all.";
          })}>{busy === "make" ? "Making…" : "Make sample meetings"}</button>
        {have > 0 && (
          <button className="danger" disabled={!!busy} onClick={() => {
            if (confirm("Delete all " + have + " sample meetings? Real meetings are not touched.")) {
              void act("remove", async () => (await api.del<{ removed: number }>(base + "/sample-meetings")).removed + " sample meetings removed.");
            }
          }}>{busy === "remove" ? "Removing…" : "Remove " + have + " sample meeting" + (have === 1 ? "" : "s")}</button>
        )}
      </div>
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error || info.error} />
    </div>
  );
}

function SeriesCard({ series, base, secretary, run }: {
  series: Series[]; base: string; secretary: boolean; run: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  const [editing, setEditing] = useState("");
  const [form, setForm] = useState({ zoom_url: "", location: "", start_time: "", until_date: "" });
  return (
    <div className="card">
      <h2>Recurring meetings</h2>
      <table>
        <thead><tr><th>Meeting</th><th>Schedule</th><th>Next</th><th /></tr></thead>
        <tbody>
          {series.map((s) => editing === s.id ? (
            <tr key={s.id}><td colSpan={4}>
              <div className="grid-2" style={{ padding: "6px 0" }}>
                <label>Zoom link<input value={form.zoom_url} onChange={(e) => setForm({ ...form, zoom_url: e.target.value })} placeholder="https://zoom.us/j/..." /></label>
                <label>Room or place<input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></label>
                <label>Start time<input type="time" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} /></label>
                <label>Last meeting on (optional)<input type="date" value={form.until_date} onChange={(e) => setForm({ ...form, until_date: e.target.value })} /></label>
              </div>
              <div className="row">
                <button className="primary" onClick={() => void run(async () => { await api.patch(base + "/series/" + s.id, form); setEditing(""); })}>Save</button>
                <button onClick={() => setEditing("")}>Cancel</button>
              </div>
            </td></tr>
          ) : (
            <tr key={s.id}>
              <td>{s.title}{s.zoom_url && <div className="sub">Zoom link saved</div>}</td>
              <td className="sub">{s.rule}<div className="mono">{s.timezone}</div></td>
              <td className="mono">{when(s.next_at)}</td>
              <td className="row" style={{ justifyContent: "flex-end" }}>
                {secretary && <button onClick={() => { setForm({ zoom_url: s.zoom_url, location: s.location, start_time: s.start_time, until_date: s.until_date }); setEditing(s.id); }}>Edit</button>}
                {secretary && <button className="danger" onClick={() => { if (confirm("Stop repeating " + s.title + "? Upcoming meetings in this series are removed; past minutes stay.")) void run(() => api.del(base + "/series/" + s.id)); }}>Stop</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Month({ base }: { base: string }) {
  const [cursor, setCursor] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const start = new Date(cursor.getFullYear(), cursor.getMonth(), 1 - ((cursor.getDay() + 6) % 7));
  const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 42);
  const data = useLoad(() => api.get<{ meetings: MeetingSummary[] }>(base + "/calendar?start=" + start.getTime() / 1000 + "&end=" + end.getTime() / 1000),
    [base, start.getTime()]);
  const byDay = useMemo(() => {
    const out: Record<string, MeetingSummary[]> = {};
    for (const m of data.data?.meetings || []) {
      const d = new Date((m.scheduled_at || 0) * 1000);
      const k = d.getFullYear() + "-" + d.getMonth() + "-" + d.getDate();
      (out[k] = out[k] || []).push(m);
    }
    return out;
  }, [data.data]);
  const cells = Array.from({ length: 42 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
  const today = new Date();
  return (
    <div className="card">
      <div className="row spread" style={{ marginBottom: 10 }}>
        <button onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}>Previous</button>
        <h2 style={{ margin: 0 }}>{cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</h2>
        <button onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}>Next</button>
      </div>
      <ErrorBox error={data.error} />
      <div className="cal-grid">
        {DAYS.map((d) => <div key={d} className="cal-head">{d}</div>)}
        {cells.map((d) => {
          const k = d.getFullYear() + "-" + d.getMonth() + "-" + d.getDate();
          const isToday = d.toDateString() === today.toDateString();
          return (
            <div key={k} className={"cal-day" + (d.getMonth() !== cursor.getMonth() ? " dim" : "") + (isToday ? " today" : "")}>
              <div className="cal-num">{d.getDate()}</div>
              {(byDay[k] || []).map((m) => (
                <Link key={m.id} to={"/meetings/" + m.id} className={"cal-item " + m.status}>
                  {new Date((m.scheduled_at || 0) * 1000).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })} {m.title}
                </Link>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
