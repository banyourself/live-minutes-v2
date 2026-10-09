import { useEffect, useState } from "react";
import { api } from "../../api";
import { ErrorBox, errText, fmtDate, useLoad } from "../../ui";
import { useSudo } from "./sudo";

interface OverviewData {
  users: { total: number; verified: number; admins: number; disabled: number; new_7d: number; active_24h: number; by_type: Record<string, number> };
  orgs: number; districts: number; schools: number;
  meetings: Record<string, number>;
  jobs: Record<string, number>;
  requests: { join: number; school: number };
  email: { sent_24h: number; pending: number; failed: number };
  security: { failed_logins_24h: number };
  health: { database: boolean; worker_seen_seconds_ago: number | null; worker_ok: boolean; mail: string; turnstile: boolean;
    sso: string[]; maintenance: boolean; public_url: string };
}

function Stat({ label, value, sub, onClick, tone = "" }: { label: string; value: string | number; sub?: string; onClick?: () => void; tone?: string }) {
  return (
    <button type="button" className={"stat " + tone} onClick={onClick} disabled={!onClick}>
      <span className="stat-label">{label}</span>
      <span className="stat-num">{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </button>
  );
}

export function Overview({ go }: { go: (tab: string) => void }) {
  const o = useLoad(() => api.get<OverviewData>("/api/admin/overview"), []);
  const d = o.data;
  if (!d) return <ErrorBox error={o.error} />;
  const h = d.health;
  return (
    <div className="stack">
      {h.maintenance && <div className="alert bad">Maintenance mode is on. Only platform administrators can sign in.</div>}
      <div className="stat-grid">
        <Stat label="People" value={d.users.total} sub={(d.users.by_type.student || 0) + " students · " + (d.users.by_type.faculty || 0) + " faculty · " + (d.users.by_type.staff || 0) + " staff · " + (d.users.by_type.it || 0) + " IT · " + d.users.new_7d + " new this week"} onClick={() => go("users")} />
        <Stat label="Signed in today" value={d.users.active_24h} sub={d.users.admins + " admins · " + d.users.disabled + " disabled"} onClick={() => go("users")} />
        <Stat label="Organizations" value={d.orgs} sub={d.schools + " schools · " + d.districts + " districts"} onClick={() => go("orgs")} />
        <Stat label="Meetings" value={d.meetings.total || 0} sub={(d.meetings.open || 0) + " live · " + (d.meetings.approved || 0) + " approved"} />
        <Stat label="Waiting requests" value={d.requests.join + d.requests.school} sub={d.requests.join + " to join · " + d.requests.school + " new schools"}
          onClick={() => go(d.requests.school ? "schools" : "joins")} tone={d.requests.join + d.requests.school ? "attention" : ""} />
        <Stat label="Emails sent today" value={d.email.sent_24h} sub={d.email.pending + " waiting · " + d.email.failed + " failed"}
          onClick={() => go("emails")} tone={d.email.failed ? "bad" : ""} />
        <Stat label="Failed sign-ins today" value={d.security.failed_logins_24h} onClick={() => go("security")}
          tone={d.security.failed_logins_24h > 25 ? "attention" : ""} />
        <Stat label="Drafting jobs" value={(d.jobs.queued || 0) + (d.jobs.running || 0)} sub={(d.jobs.error || 0) + " failed"} tone={d.jobs.error ? "attention" : ""} />
      </div>
      <div className="card stack">
        <h2>Health</h2>
        <table>
          <tbody>
            <tr><td>Database</td><td>{h.database ? <span className="chip ok">ok</span> : <span className="chip bad">down</span>}</td></tr>
            <tr><td>Background worker</td><td>{h.worker_ok ? <span className="chip ok">ok</span> : <span className="chip bad">not seen</span>}
              <span className="sub"> {h.worker_seen_seconds_ago === null ? "never" : "last seen " + h.worker_seen_seconds_ago + "s ago"}</span></td></tr>
            <tr><td>Email</td><td>{h.mail === "smtp" ? <span className="chip ok">sending</span> : <span className="chip warn">{h.mail}</span>}</td></tr>
            <tr><td>Bot check (Turnstile)</td><td>{h.turnstile ? <span className="chip ok">on</span> : <span className="chip warn">off</span>}</td></tr>
            <tr><td>School sign-in</td><td>{h.sso.length ? h.sso.join(", ") : <span className="sub">not configured</span>}</td></tr>
            <tr><td>Address</td><td className="mono">{h.public_url}</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface JoinRow { id: string; org_id: string; org: string; school: string; email: string; name: string; school_email: string; message: string; created_at: number }

export function JoinRequests() {
  const list = useLoad(() => api.get<{ requests: JoinRow[] }>("/api/admin/join-requests"), []);
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const rows = list.data?.requests || [];

  async function decide(r: JoinRow, ok: boolean) {
    setError("");
    try {
      const base = "/api/orgs/" + r.org_id + "/join-requests/" + r.id;
      if (ok) await api.post(base + "/approve", { role: roles[r.id] || "member" });
      else await api.post(base + "/deny");
      await list.reload();
    } catch (e) {
      setError(errText(e));
    }
  }

  return (
    <div className="card stack">
      <h2>Requests to join organizations</h2>
      <p className="sub" style={{ margin: 0 }}>Owners usually handle these. You can act on any of them here.</p>
      <ErrorBox error={error || list.error} />
      {rows.length === 0 && <p className="sub">Nothing waiting.</p>}
      {rows.length > 0 && (
        <table>
          <thead><tr><th>Person</th><th>Organization</th><th>School email</th><th>Role</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.name || r.email}<div className="sub">{r.email}{r.message ? " · " + r.message : ""}</div></td>
                <td>{r.org}<div className="sub">{r.school}</div></td>
                <td className="mono">{r.school_email}</td>
                <td><select value={roles[r.id] || "member"} onChange={(e) => setRoles({ ...roles, [r.id]: e.target.value })}>
                  {["member", "secretary", "viewer", "owner"].map((x) => <option key={x}>{x}</option>)}
                </select></td>
                <td className="row"><button className="primary" onClick={() => void decide(r, true)}>Approve</button>
                  <button className="danger" onClick={() => void decide(r, false)}>Deny</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

interface EmailRow { id: string; to: string; subject: string; created_at: number; sent_at: number | null; attempts: number; error: string; status: string }

export function Emails() {
  const [status, setStatus] = useState("");
  const list = useLoad(() => api.get<{ emails: EmailRow[] }>("/api/admin/emails?status=" + status), [status]);
  const [error, setError] = useState("");
  return (
    <div className="card stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>Email outbox</h2>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option><option value="sent">Sent</option><option value="pending">Waiting</option><option value="failed">Failed</option>
        </select>
      </div>
      <p className="sub" style={{ margin: 0 }}>Message bodies are never shown here because they contain sign-in links and codes.</p>
      <ErrorBox error={error || list.error} />
      <table>
        <thead><tr><th>To</th><th>Subject</th><th>Status</th><th>Queued</th><th /></tr></thead>
        <tbody>
          {(list.data?.emails || []).map((e) => (
            <tr key={e.id}>
              <td className="mono">{e.to}</td>
              <td>{e.subject}{e.error && <div className="sub">{e.error}</div>}</td>
              <td><span className={"chip " + (e.status === "sent" ? "ok" : e.status === "failed" ? "bad" : "warn")}>{e.status}</span>
                {e.attempts > 1 && <span className="sub"> {e.attempts} tries</span>}</td>
              <td>{fmtDate(e.created_at)}</td>
              <td>{e.status !== "sent" && <button onClick={() => void api.post("/api/admin/emails/" + e.id + "/retry").then(() => list.reload()).catch((x) => setError(errText(x)))}>Retry</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface SettingRow { key: string; label: string; group: string; type: string; min: number | null; max: number | null; value: boolean | number; default: boolean | number; overridden: boolean }
interface SecurityData {
  settings: SettingRow[];
  failed_by_account: { email: string; count: number; last: number; user_id: string | null; locked: boolean }[];
  failed_by_network: { ip: string; count: number; last: number }[];
  turnstile_configured: boolean; mail: string; sso: string[];
}

export function Security() {
  const guard = useSudo();
  const data = useLoad(() => api.get<SecurityData>("/api/admin/security"), []);
  const [values, setValues] = useState<Record<string, boolean | number>>({});
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (data.data) setValues(Object.fromEntries(data.data.settings.map((s) => [s.key, s.value])));
  }, [data.data]);

  const d = data.data;
  if (!d) return <ErrorBox error={data.error} />;
  const groups = [...new Set(d.settings.map((s) => s.group))];
  const changed = Object.fromEntries(d.settings.filter((s) => values[s.key] !== s.value).map((s) => [s.key, values[s.key]]));

  async function save() {
    setMsg(""); setError("");
    try {
      await guard(() => api.put("/api/admin/settings", { values: changed }));
      setMsg("Saved. Changes apply across the server within 15 seconds.");
      await data.reload();
    } catch (e) {
      if (errText(e) !== "cancelled") setError(errText(e));
    }
  }

  async function unlock(id: string) {
    try { await api.post("/api/admin/users/" + id + "/unlock"); await data.reload(); } catch (e) { setError(errText(e)); }
  }

  return (
    <div className="stack">
      <div className="card stack">
        <h2>Security settings</h2>
        <p className="sub" style={{ margin: 0 }}>Each setting has safe limits, and saving asks for your password. Keys and passwords stay in the server's .env file.</p>
        {groups.map((g) => (
          <div key={g} className="stack">
            <h3>{g}</h3>
            {d.settings.filter((s) => s.group === g).map((s) => (
              <label key={s.key} className={s.type === "bool" ? "setting-row toggle" : "setting-row"}>
                <span>{s.label}{s.overridden && <span className="sub"> · changed from the default ({String(s.default)})</span>}</span>
                {s.type === "bool" ? (
                  <input type="checkbox" checked={!!values[s.key]} onChange={(e) => setValues({ ...values, [s.key]: e.target.checked })} />
                ) : (
                  <input type="number" style={{ width: 110 }} min={s.min ?? undefined} max={s.max ?? undefined} step={s.type === "float" ? 0.5 : 1}
                    value={String(values[s.key] ?? "")} onChange={(e) => setValues({ ...values, [s.key]: Number(e.target.value) })} />
                )}
              </label>
            ))}
          </div>
        ))}
        {msg && <div className="alert ok" role="status">{msg}</div>}
        <ErrorBox error={error} />
        <div className="row"><button className="primary" disabled={Object.keys(changed).length === 0} onClick={() => void save()}>Save {Object.keys(changed).length || ""} change{Object.keys(changed).length === 1 ? "" : "s"}</button></div>
        <p className="sub" style={{ margin: 0 }}>
          Configured on the server: email {d.mail}, Turnstile {d.turnstile_configured ? "keys present" : "no keys"}, school sign-in {d.sso.length ? d.sso.join(", ") : "none"}.
        </p>
      </div>
      <div className="grid-2">
        <div className="card stack">
          <h2>Failed sign-ins by account (24 hours)</h2>
          {d.failed_by_account.length === 0 && <p className="sub">None.</p>}
          <table><tbody>
            {d.failed_by_account.map((r) => (
              <tr key={r.email}><td className="mono">{r.email}{!r.user_id && <div className="sub">no such account</div>}</td><td>{r.count}</td>
                <td>{r.locked && <span className="chip bad">locked</span>}</td>
                <td>{r.user_id && r.locked && <button onClick={() => void unlock(r.user_id!)}>Unlock</button>}</td></tr>
            ))}
          </tbody></table>
        </div>
        <div className="card stack">
          <h2>Failed sign-ins by network (24 hours)</h2>
          {d.failed_by_network.length === 0 && <p className="sub">None.</p>}
          <table><tbody>
            {d.failed_by_network.map((r) => <tr key={r.ip}><td className="mono">{r.ip}</td><td>{r.count}</td><td className="sub">{fmtDate(r.last)}</td></tr>)}
          </tbody></table>
        </div>
      </div>
    </div>
  );
}

interface AuditRow { at: number; action: string; user: string; org: string; ip: string; detail: Record<string, unknown> }

export function Activity() {
  const [action, setAction] = useState("");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const list = useLoad(() => api.get<{ events: AuditRow[] }>("/api/admin/audit?limit=200&action=" + encodeURIComponent(action) + "&q=" + encodeURIComponent(search)), [action, search]);
  return (
    <div className="card stack">
      <form className="row" onSubmit={(e) => { e.preventDefault(); setSearch(q); }}>
        <select value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="">All activity</option>
          <option value="user.">Accounts and sign-ins</option>
          <option value="admin.">Administrator actions</option>
          <option value="org.">Organizations</option>
          <option value="join.">Join requests</option>
          <option value="school">Schools</option>
          <option value="meeting.">Meetings</option>
          <option value="invite.">Invites</option>
          <option value="ai.">AI connections</option>
        </select>
        <input style={{ flex: 1 }} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter by email" placeholder="Filter by person's email" />
        <button className="primary">Filter</button>
      </form>
      <ErrorBox error={list.error} />
      <table>
        <thead><tr><th>When</th><th>What</th><th>Who</th><th>Where</th></tr></thead>
        <tbody>
          {(list.data?.events || []).map((e, i) => (
            <tr key={i}>
              <td>{fmtDate(e.at)}</td>
              <td className="mono">{e.action}<div className="sub">{Object.entries(e.detail || {}).filter(([k]) => k !== "changes").map(([k, v]) => k + ": " + (typeof v === "object" ? JSON.stringify(v) : String(v))).join(" · ").slice(0, 160)}</div></td>
              <td>{e.user || <span className="sub">system</span>}{e.org && <div className="sub">{e.org}</div>}</td>
              <td className="mono">{e.ip}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
