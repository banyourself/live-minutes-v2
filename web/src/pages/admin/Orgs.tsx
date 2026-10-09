import { useState } from "react";
import { api, ROLE_LABEL, ROLES } from "../../api";
import { ErrorBox, errText, fmtDate, useLoad } from "../../ui";
import { useSudo } from "./sudo";

interface OrgRow { id: string; name: string; school: string; school_id: string | null; district: string; created_at: number; owners: string[]; members: number; meetings: number }
interface OrgDetail {
  id: string; name: string; school: string; school_id: string | null; district: string; created_at: number;
  members: { membership_id: string; user_id: string; email: string; name: string; role: string }[];
  meetings: { id: string; title: string; status: string; created_at: number }[];
}

export function Orgs() {
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState("");
  const list = useLoad(() => api.get<{ total: number; orgs: OrgRow[] }>("/api/admin/orgs?limit=200&q=" + encodeURIComponent(search)), [search]);

  return (
    <div className="stack">
      <PersonalInvite onSent={() => void list.reload()} />
      <div className="card stack">
        <form className="row" onSubmit={(e) => { e.preventDefault(); setSearch(q); }}>
          <input style={{ flex: 1 }} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search organizations" placeholder="Search organizations, schools, districts" />
          <button className="primary">Search</button>
        </form>
        <ErrorBox error={list.error} />
        <table>
          <thead><tr><th>Organization</th><th>Owners</th><th>Members</th><th>Meetings</th><th>Created</th></tr></thead>
          <tbody>
            {(list.data?.orgs || []).map((o) => (
              <tr key={o.id} className={"clickable" + (selected === o.id ? " on" : "")} onClick={() => setSelected(o.id)}>
                <td>{o.name}<div className="sub">{o.school ? o.school + " · " : ""}{o.district}{!o.school_id && " · not linked to an official college"}</div></td>
                <td className="sub">{o.owners.join(", ") || "none"}</td>
                <td>{o.members}</td>
                <td>{o.meetings}</td>
                <td>{fmtDate(o.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <span className="sub">{list.data?.total || 0} organizations</span>
      </div>
      {selected && <OrgPanel id={selected} onChanged={() => void list.reload()} onGone={() => { setSelected(""); void list.reload(); }} />}
    </div>
  );
}

function PersonalInvite({ onSent }: { onSent: () => void }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    setBusy(true); setMsg(""); setError("");
    try {
      const r = await api.post<{ email: string; link: string; emailed: boolean }>("/api/admin/personal-invites", { email, name });
      setMsg(r.emailed ? "Invitation emailed to " + r.email + "." : "Email is off on this server. Send this link yourself: " + r.link);
      setEmail(""); setName("");
      onSent();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card stack">
      <h2 style={{ margin: 0 }}>Invite someone to a personal workspace</h2>
      <p className="sub" style={{ margin: 0 }}>They get their own private workspace for their own meetings, with full access, and can connect their own Zoom account. No school or district is needed.</p>
      <div className="row wrap">
        <input type="email" style={{ flex: 2 }} value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Email to invite" placeholder="Email address" />
        <input style={{ flex: 1 }} value={name} onChange={(e) => setName(e.target.value)} aria-label="Their name (optional)" placeholder="Their name (optional)" />
        <button className="primary" disabled={busy || !email} onClick={() => void send()}>Send invitation</button>
      </div>
      {msg && <div className="alert ok" role="status" style={{ wordBreak: "break-all" }}>{msg}</div>}
      <ErrorBox error={error} />
    </div>
  );
}

function OrgPanel({ id, onChanged, onGone }: { id: string; onChanged: () => void; onGone: () => void }) {
  const guard = useSudo();
  const d = useLoad(() => api.get<OrgDetail>("/api/admin/orgs/" + id), [id]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [moveTo, setMoveTo] = useState("");
  const dirs = useLoad(() => api.get<{ districts: { id: string; name: string; schools: { id: string; name: string }[] }[] }>("/api/admin/directory"), []);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const o = d.data;

  async function run(fn: () => Promise<unknown>, done: string) {
    setMsg(""); setError("");
    try {
      await guard(fn);
      setMsg(done);
      await d.reload();
      onChanged();
    } catch (e) {
      if (errText(e) !== "cancelled") setError(errText(e));
    }
  }

  if (!o) return <div className="card"><ErrorBox error={d.error} /></div>;
  const base = "/api/orgs/" + o.id;

  return (
    <div className="card stack">
      <div>
        <h2 style={{ margin: 0 }}>{o.name}</h2>
        <div className="sub">{o.school ? o.school + " · " : ""}{o.district} · created {fmtDate(o.created_at)}</div>
      </div>
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error} />
      <h3>Members</h3>
      <table>
        <tbody>
          {o.members.map((m) => (
            <tr key={m.membership_id}>
              <td>{m.name || m.email}<div className="sub">{m.email}</div></td>
              <td>
                <select value={m.role} onChange={(e) => void run(() => api.patch(base + "/members/" + m.membership_id, { role: e.target.value }), "Role changed.")}>
                  {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                </select>
              </td>
              <td><button className="danger" onClick={() => { if (confirm("Remove " + m.email + " from " + o.name + "?")) void run(() => api.del(base + "/members/" + m.membership_id), "Member removed."); }}>Remove</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="row">
        <input type="email" style={{ flex: 1 }} value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Email of the person to add" placeholder="Add someone who already has an account" />
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          {["member", "secretary", "viewer", "owner"].map((r) => <option key={r}>{r}</option>)}
        </select>
        <button disabled={!email} onClick={() => void run(async () => { await api.post("/api/admin/orgs/" + o.id + "/members", { email, role }); setEmail(""); }, "Member added.")}>Add</button>
      </div>
      <h3>Official college</h3>
      <div className="row wrap">
        <select value={moveTo || o.school_id || ""} onChange={(e) => setMoveTo(e.target.value)}>
          {!o.school_id && <option value="">Not linked</option>}
          {(dirs.data?.districts || []).flatMap((d) => d.schools.map((x) => <option key={x.id} value={x.id}>{x.name} ({d.name})</option>))}
        </select>
        <button disabled={!moveTo || moveTo === o.school_id} onClick={() => void run(() => api.patch("/api/admin/orgs/" + o.id + "/school", { school_id: moveTo }), "Moved.")}>Move</button>
      </div>
      <h3>Meetings ({o.meetings.length})</h3>
      {o.meetings.length === 0 && <p className="sub">None yet.</p>}
      {o.meetings.slice(0, 20).map((m) => <div key={m.id}>{m.title} <span className="sub">· {m.status} · {fmtDate(m.created_at)}</span></div>)}
      <div className="row">
        <button className="danger" onClick={() => {
          const typed = prompt("Type the organization name to delete it, its meetings, templates, and files forever:");
          if (typed === o.name) {
            void (async () => {
              try { await guard(() => api.del("/api/admin/orgs/" + o.id)); onGone(); }
              catch (e) { if (errText(e) !== "cancelled") setError(errText(e)); }
            })();
          } else if (typed !== null) setError("The name did not match, so nothing was deleted.");
        }}>Delete organization</button>
      </div>
    </div>
  );
}
