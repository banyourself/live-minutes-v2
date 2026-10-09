import { useEffect, useState } from "react";
import { api, ROLE_LABEL, ROLES, type AdminScope } from "../../api";
import { useSession } from "../../session";
import { ErrorBox, errText, fmtDate, useLoad } from "../../ui";
import RequestsPanel from "../../components/RequestsPanel";
import { typeLabel } from "../../components/AccountType";
import { ScopeAi } from "./AiAdmin";
import { LibraryPanel, SchoolSignIn } from "./Provisioning";
import RecordsPanel from "./Governance";
import BackupsPanel from "./Backups";
import { ProcurementCard, UsageReport } from "./Reports";
import { SudoProvider, useSudo } from "./sudo";

interface Overview {
  scope: string; name: string; district: string; can_manage_admins: boolean;
  counts: { orgs: number; people: number; meetings: number; join_requests: number; school_requests: number; schools: number };
}
interface OrgRow { id: string; name: string; school: string; created_at: number; owners: string[]; members: number; meetings: number }
interface OrgDetail {
  id: string; name: string; school: string; created_at: number;
  members: { membership_id: string; user_id: string; email: string; name: string; role: string }[];
  meetings: { id: string; title: string; status: string; created_at: number }[];
}
interface Person { id: string; email: string; name: string; account_type: string; last_login_at: number | null; disabled: boolean; locked: boolean; orgs: { org: string; role: string }[] }
interface JoinRow { id: string; org_id: string; org: string; school: string; email: string; name: string; school_email: string; message: string; created_at: number }
interface RoleRow { id: string; scope: string; target_id: string; target: string; email: string; name: string; staff_email: string; created_at: number }
interface SchoolRow { id: string; name: string; domains: string[]; staff_domains: string[]; active: boolean }
interface AuditRow { at: number; action: string; user: string; org: string; ip: string; detail: Record<string, unknown> }

const LABEL: Record<string, string> = { district: "District IT", school: "College IT" };

export default function Console() {
  const { me } = useSession();
  const scopes = me?.user.admin_scopes || [];
  const [pick, setPick] = useState(scopes[0] ? scopes[0].scope + ":" + scopes[0].id : "");
  const current = scopes.find((s) => s.scope + ":" + s.id === pick) || scopes[0];
  if (!current) return <p className="sub">You do not have an IT role.</p>;
  return (
    <SudoProvider>
      <div className="page-head">
        <div>
          <div className="kicker">{LABEL[current.scope]} console</div>
          <h1>{current.name}</h1>
          <p className="sub">{current.scope === "school" ? current.district + " · " : ""}Only organizations and people in this {current.scope === "district" ? "district" : "college"} are shown.</p>
        </div>
        {scopes.length > 1 && (
          <select value={pick} onChange={(e) => setPick(e.target.value)}>
            {scopes.map((s) => <option key={s.scope + s.id} value={s.scope + ":" + s.id}>{LABEL[s.scope]}: {s.name}</option>)}
          </select>
        )}
      </div>
      <ScopeView key={current.scope + current.id} s={current} />
    </SudoProvider>
  );
}

function ScopeView({ s }: { s: AdminScope }) {
  const base = "/api/manage/" + s.scope + "/" + s.id;
  const [tab, setTab] = useState("overview");
  const ov = useLoad(() => api.get<Overview>(base + "/overview"), [base]);
  const district = s.scope === "district";
  const tabs: [string, string][] = [["overview", "Overview"], ["requests", "New requests"], ["orgs", "Organizations"], ["people", "People"],
    ["joins", "Join requests"], ["staff", "IT staff"], ["ai", "AI"], ["library", "Templates"], ["records", "Records"], ["backups", "Backups"], ["reports", "Reports"],
    ...(district ? [["schools", "Colleges"], ["sso", "School sign-in"]] as [string, string][] : []), ["activity", "Activity"]];
  const schoolOptions = useLoad(() => district ? api.get<{ schools: SchoolRow[] }>(base + "/schools") : Promise.resolve({ schools: [] as SchoolRow[] }), [base, district]);
  return (
    <>
      <div className="tabs" role="group" aria-label="Sections">{tabs.map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} aria-pressed={tab === k} onClick={() => setTab(k)}>{l}</button>)}</div>
      {tab === "overview" && ov.data && (
        <div className="stat-grid">
          <button type="button" className="stat" onClick={() => setTab("orgs")}><span className="stat-label">Organizations</span><span className="stat-num">{ov.data.counts.orgs}</span></button>
          <button type="button" className="stat" onClick={() => setTab("people")}><span className="stat-label">People</span><span className="stat-num">{ov.data.counts.people}</span></button>
          <div className="stat"><span className="stat-label">Meetings</span><span className="stat-num">{ov.data.counts.meetings}</span></div>
          <button type="button" className={"stat" + (ov.data.counts.join_requests ? " attention" : "")} onClick={() => setTab("joins")}><span className="stat-label">Join requests</span><span className="stat-num">{ov.data.counts.join_requests}</span></button>
          <button type="button" className={"stat" + (ov.data.counts.school_requests ? " attention" : "")} onClick={() => setTab("requests")}><span className="stat-label">New requests</span><span className="stat-num">{ov.data.counts.school_requests}</span></button>
          {district && <button type="button" className="stat" onClick={() => setTab("schools")}><span className="stat-label">Colleges</span><span className="stat-num">{ov.data.counts.schools}</span></button>}
        </div>
      )}
      <ErrorBox error={ov.error} />
      {tab === "requests" && (
        <RequestsPanel listUrl={base + "/requests"} actionBase={base + "/requests"}
          title={district ? "New colleges and organizations" : "New organizations"}
          schools={(schoolOptions.data?.schools || []).map((x) => ({ id: x.id, name: x.name, district_id: s.id }))} />
      )}
      {tab === "ai" && <ScopeAi scope={s.scope} scopeId={s.id} base={base} />}
      {tab === "orgs" && <Orgs base={base} />}
      {tab === "people" && <People base={base} />}
      {tab === "joins" && <Joins base={base} />}
      {tab === "staff" && <Staff base={base} district={district} />}
      {tab === "schools" && district && <Colleges base={base} />}
      {tab === "library" && <LibraryPanel base={base} district={district} />}
      {tab === "records" && <RecordsPanel base={base} district={district} />}
      {tab === "backups" && <BackupsPanel base={base} district={district} />}
      {tab === "reports" && <div className="stack"><UsageReport url={base + "/reports"} title={district ? "District usage" : "College usage"} /><ProcurementCard /></div>}
      {tab === "sso" && district && <SchoolSignIn base={base} />}
      {tab === "activity" && <ActivityLog base={base} />}
    </>
  );
}

function OrgRules({ base }: { base: string }) {
  const guard = useSudo();
  const r = useLoad(() => api.get<{ advisors_create_orgs: boolean; allow_org_delete: boolean }>(base + "/org-rules"), [base]);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  async function save(patch: Partial<{ advisors_create_orgs: boolean; allow_org_delete: boolean }>) {
    setMsg(""); setError("");
    try { await guard(() => api.put(base + "/org-rules", { ...r.data, ...patch })); await r.reload(); setMsg("Saved."); }
    catch (e) { if (errText(e) !== "cancelled") setError(errText(e)); }
  }
  return (
    <div className="card stack">
      <h2>Who can create and delete organizations</h2>
      <p className="sub" style={{ margin: 0 }}>College and district IT can always create and delete organizations. Students and staff request new ones,
        and you approve them under New requests. These settings let you hand some of that to faculty and staff.</p>
      <label className="setting-row"><span>Faculty and staff with a confirmed work email can create organizations without approval</span>
        <input type="checkbox" checked={!!r.data?.advisors_create_orgs} disabled={!r.data} onChange={(e) => void save({ advisors_create_orgs: e.target.checked })} /></label>
      <label className="setting-row"><span>Positions with the "Delete the organization" permission (advisors by default) can delete their own organization</span>
        <input type="checkbox" checked={!!r.data?.allow_org_delete} disabled={!r.data} onChange={(e) => void save({ allow_org_delete: e.target.checked })} /></label>
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error || r.error} />
    </div>
  );
}

function Orgs({ base }: { base: string }) {
  const list = useLoad(() => api.get<{ orgs: OrgRow[] }>(base + "/orgs"), [base]);
  const [open, setOpen] = useState("");
  return (
    <div className="stack">
      <OrgRules base={base} />
      <div className="card stack">
        <ErrorBox error={list.error} />
        <table>
          <thead><tr><th>Organization</th><th>Owners</th><th>Members</th><th>Meetings</th><th>Created</th></tr></thead>
          <tbody>
            {(list.data?.orgs || []).map((o) => (
              <tr key={o.id} className={"clickable" + (open === o.id ? " on" : "")} onClick={() => setOpen(o.id)}>
                <td>{o.name}<div className="sub">{o.school}</div></td><td className="sub">{o.owners.join(", ") || "none"}</td>
                <td>{o.members}</td><td>{o.meetings}</td><td>{fmtDate(o.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {list.data && list.data.orgs.length === 0 && <p className="sub">No organizations yet.</p>}
      </div>
      {open && <OrgPanel base={base} id={open} onChanged={() => { setOpen(""); void list.reload(); }} />}
    </div>
  );
}

function OrgPanel({ base, id, onChanged }: { base: string; id: string; onChanged: () => void }) {
  const d = useLoad(() => api.get<OrgDetail>(base + "/orgs/" + id), [base, id]);
  const guard = useSudo();
  const [error, setError] = useState("");
  const o = d.data;
  async function run(fn: () => Promise<unknown>) {
    setError("");
    try { await fn(); await d.reload(); onChanged(); } catch (e) { setError(errText(e)); }
  }
  if (!o) return <ErrorBox error={d.error} />;
  const orgBase = "/api/orgs/" + o.id;
  return (
    <div className="card stack">
      <div className="row spread">
        <div><h2 style={{ margin: 0 }}>{o.name}</h2><div className="sub">{o.school} · created {fmtDate(o.created_at)}</div></div>
        <button className="danger" onClick={() => {
          const typed = prompt("This permanently deletes " + o.name + " with all of its meetings, recordings, minutes, and members. Type its name to confirm.");
          if (typed) void (async () => {
            setError("");
            try { await guard(() => api.del(base + "/orgs/" + o.id + "?confirm=" + encodeURIComponent(typed))); onChanged(); }
            catch (e) { setError(errText(e)); }
          })();
        }}>Delete organization</button>
      </div>
      <ErrorBox error={error} />
      <h3>Members</h3>
      <table>
        <tbody>
          {o.members.map((m) => (
            <tr key={m.membership_id}>
              <td>{m.name || m.email}<div className="sub">{m.email}</div></td>
              <td><select value={m.role} onChange={(e) => void run(() => api.patch(orgBase + "/members/" + m.membership_id, { role: e.target.value }))}>
                {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
              </select></td>
              <td><button className="danger" onClick={() => { if (confirm("Remove " + m.email + " from " + o.name + "?")) void run(() => api.del(orgBase + "/members/" + m.membership_id)); }}>Remove</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Meetings ({o.meetings.length})</h3>
      {o.meetings.slice(0, 20).map((m) => <div key={m.id}>{m.title} <span className="sub">· {m.status} · {fmtDate(m.created_at)}</span></div>)}
    </div>
  );
}

function People({ base }: { base: string }) {
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const list = useLoad(() => api.get<{ people: Person[] }>(base + "/people?q=" + encodeURIComponent(search)), [base, search]);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  async function run(fn: () => Promise<unknown>, done: string) {
    setMsg(""); setError("");
    try { await fn(); setMsg(done); await list.reload(); } catch (e) { setError(errText(e)); }
  }
  return (
    <div className="card stack">
      <form className="row" onSubmit={(e) => { e.preventDefault(); setSearch(q); }}>
        <input style={{ flex: 1 }} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search people" placeholder="Search people" />
        <button className="primary">Search</button>
      </form>
      <p className="sub" style={{ margin: 0 }}>To change someone's role or remove them, open their organization. Disabling or deleting accounts is handled by the platform owner.</p>
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error || list.error} />
      <table>
        <thead><tr><th>Person</th><th>Organizations</th><th>Last sign-in</th><th /></tr></thead>
        <tbody>
          {(list.data?.people || []).map((p) => (
            <tr key={p.id}>
              <td>{p.name || p.email}<div className="sub">{p.email} · {typeLabel(p.account_type)}</div>
                <span className="chips">{p.locked && <span className="chip bad">locked</span>}{p.disabled && <span className="chip bad">disabled</span>}</span></td>
              <td className="sub">{p.orgs.map((o) => o.org + " (" + (ROLE_LABEL[o.role] || o.role) + ")").join(", ")}</td>
              <td>{fmtDate(p.last_login_at) || "never"}</td>
              <td className="row">
                <button onClick={() => void run(() => api.post(base + "/people/" + p.id + "/reset-email"), "Password reset email sent to " + p.email + ".")}>Send reset email</button>
                {p.locked && <button onClick={() => void run(() => api.post(base + "/people/" + p.id + "/unlock"), "Sign-in unlocked.")}>Unlock</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Joins({ base }: { base: string }) {
  const list = useLoad(() => api.get<{ requests: JoinRow[] }>(base + "/join-requests"), [base]);
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  async function decide(r: JoinRow, ok: boolean) {
    setError("");
    try {
      const b = "/api/orgs/" + r.org_id + "/join-requests/" + r.id;
      await (ok ? api.post(b + "/approve", { role: roles[r.id] || "member" }) : api.post(b + "/deny"));
      await list.reload();
    } catch (e) { setError(errText(e)); }
  }
  const rows = list.data?.requests || [];
  return (
    <div className="card stack">
      <ErrorBox error={error || list.error} />
      {rows.length === 0 && <p className="sub">Nothing waiting.</p>}
      {rows.length > 0 && (
        <table>
          <thead><tr><th>Person</th><th>Organization</th><th>School email</th><th>Role</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.name || r.email}<div className="sub">{r.email}{r.message ? " · " + r.message : ""}</div></td>
                <td>{r.org}<div className="sub">{r.school}</div></td><td className="mono">{r.school_email}</td>
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

function Staff({ base, district }: { base: string; district: boolean }) {
  const guard = useSudo();
  const list = useLoad(() => api.get<{ admins: RoleRow[]; schools: { id: string; name: string; staff_domains: string[] }[] }>(base + "/admins"), [base]);
  const [email, setEmail] = useState("");
  const [school, setSchool] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const schools = list.data?.schools || [];
  useEffect(() => { if (!school && schools[0]) setSchool(schools[0].id); }, [schools, school]);
  async function run(fn: () => Promise<unknown>, done: string) {
    setMsg(""); setError("");
    try { await guard(fn); setMsg(done); await list.reload(); } catch (e) { if (errText(e) !== "cancelled") setError(errText(e)); }
  }
  const chosen = schools.find((s) => s.id === school);
  return (
    <div className="stack">
      <div className="card stack">
        <h2>IT staff</h2>
        <table>
          <tbody>
            {(list.data?.admins || []).map((r) => (
              <tr key={r.id}>
                <td>{r.name || r.email}<div className="sub">{r.email} · verified {r.staff_email}</div></td>
                <td>{r.scope === "district" ? "District IT" : "College IT"}<div className="sub">{r.target}</div></td>
                <td>{district && r.scope === "school" && <button className="danger" onClick={() => void run(() => api.del(base + "/admins/" + r.id), "Role removed.")}>Remove</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {msg && <div className="alert ok" role="status">{msg}</div>}
        <ErrorBox error={error || list.error} />
      </div>
      {district ? (
        <div className="card stack">
          <h2>Add college IT</h2>
          <p className="sub" style={{ margin: 0 }}>The person needs a Live Minutes account and a confirmed staff email at that college{chosen?.staff_domains.length ? " (" + chosen.staff_domains.map((d) => "@" + d).join(", ") + ")" : ""}. Student emails do not qualify.</p>
          <div className="row">
            <select value={school} onChange={(e) => setSchool(e.target.value)}>{schools.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
            <input type="email" style={{ flex: 1 }} value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Their Live Minutes sign-in email" placeholder="Their Live Minutes sign-in email" />
            <button className="primary" disabled={!email || !school} onClick={() => void run(async () => { await api.post(base + "/admins", { email, school_id: school }); setEmail(""); }, "College IT role granted.")}>Grant</button>
          </div>
        </div>
      ) : (
        <p className="sub">College IT roles are granted by district IT or the platform owner.</p>
      )}
    </div>
  );
}

function Colleges({ base }: { base: string }) {
  const guard = useSudo();
  const list = useLoad(() => api.get<{ district: { name: string; staff_domains: string[] }; schools: SchoolRow[] }>(base + "/schools"), [base]);
  const [edits, setEdits] = useState<Record<string, { domains: string; staff: string }>>({});
  const [add, setAdd] = useState({ name: "", domains: "", staff: "" });
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const split = (v: string) => v.split(/[\s,]+/).map((d) => d.trim()).filter(Boolean);
  async function run(fn: () => Promise<unknown>, done: string) {
    setMsg(""); setError("");
    try { await guard(fn); setMsg(done); await list.reload(); } catch (e) { if (errText(e) !== "cancelled") setError(errText(e)); }
  }
  return (
    <div className="stack">
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error || list.error} />
      <div className="card stack">
        <h2>Colleges</h2>
        <p className="sub" style={{ margin: 0 }}>Member domains let students and staff join organizations. Staff domains are the only ones that qualify someone for an IT role.</p>
        <table>
          <thead><tr><th>College</th><th>Member email domains</th><th>Staff domains</th><th /></tr></thead>
          <tbody>
            {(list.data?.schools || []).map((sch) => {
              const e = edits[sch.id] || { domains: sch.domains.join(", "), staff: sch.staff_domains.join(", ") };
              return (
                <tr key={sch.id}>
                  <td>{sch.name}{!sch.active && <div className="sub">hidden</div>}</td>
                  <td><input value={e.domains} onChange={(x) => setEdits({ ...edits, [sch.id]: { ...e, domains: x.target.value } })} /></td>
                  <td><input value={e.staff} onChange={(x) => setEdits({ ...edits, [sch.id]: { ...e, staff: x.target.value } })} /></td>
                  <td><button onClick={() => void run(() => api.patch(base + "/schools/" + sch.id, { domains: split(e.domains), staff_domains: split(e.staff) }), "Saved.")}>Save</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <h3>Add a college</h3>
        <div className="grid-3">
          <label>Name<input value={add.name} onChange={(e) => setAdd({ ...add, name: e.target.value })} /></label>
          <label>Member domains<input value={add.domains} placeholder="student.college.edu, college.edu" onChange={(e) => setAdd({ ...add, domains: e.target.value })} /></label>
          <label>Staff domains<input value={add.staff} placeholder="college.edu" onChange={(e) => setAdd({ ...add, staff: e.target.value })} /></label>
        </div>
        <div className="row"><button className="primary" disabled={!add.name || !add.domains} onClick={() => void run(async () => {
          await api.post(base + "/schools", { name: add.name, domains: split(add.domains), staff_domains: split(add.staff) });
          setAdd({ name: "", domains: "", staff: "" });
        }, "College added.")}>Add college</button></div>
      </div>
    </div>
  );
}

function ActivityLog({ base }: { base: string }) {
  const list = useLoad(() => api.get<{ events: AuditRow[] }>(base + "/activity"), [base]);
  return (
    <div className="card stack">
      <ErrorBox error={list.error} />
      <table>
        <thead><tr><th>When</th><th>What</th><th>Who</th><th>Organization</th></tr></thead>
        <tbody>
          {(list.data?.events || []).map((e, i) => (
            <tr key={i}><td>{fmtDate(e.at)}</td><td className="mono">{e.action}</td><td>{e.user || <span className="sub">system</span>}</td><td>{e.org}</td></tr>
          ))}
        </tbody>
      </table>
      {list.data && list.data.events.length === 0 && <p className="sub">No activity in the last 90 days.</p>}
    </div>
  );
}
