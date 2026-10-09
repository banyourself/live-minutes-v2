import { useState } from "react";
import { api } from "../../api";
import { ErrorBox, errText, fmtDate, useLoad } from "../../ui";
import { TYPES, typeLabel } from "../../components/AccountType";
import { useSudo } from "./sudo";

export interface UserRow {
  id: string; email: string; name: string; account_type: string; verified: boolean; verified_via: string; admin: boolean; disabled: boolean;
  has_password: boolean; two_factor?: boolean; created_at: number; last_login_at: number | null; orgs: number;
  failed_15m: number; failed_24h: number; locked: boolean;
}

interface UserDetail extends UserRow {
  memberships: { membership_id: string; org_id: string; org: string; school: string; role: string }[];
  school_emails: { email: string; verified: boolean }[];
  identities: { provider: string; email: string; last_used_at: number | null }[];
  sessions: { created_at: number; last_seen_at: number | null; expires_at: number; user_agent: string }[];
  events: { at: number; action: string; ip: string; detail: Record<string, unknown> }[];
}

export function Chips({ u }: { u: UserRow }) {
  return (
    <span className="chips">
      {u.admin && <span className="chip accent">platform owner</span>}
      {!u.verified && <span className="chip warn">unconfirmed</span>}
      {u.disabled && <span className="chip bad">disabled</span>}
      {u.locked && <span className="chip bad">locked</span>}
      {!u.has_password && <span className="chip">SSO only</span>}
    </span>
  );
}

export function Users() {
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [type, setType] = useState("");
  const [selected, setSelected] = useState("");
  const list = useLoad(() => api.get<{ total: number; users: UserRow[] }>(
    "/api/admin/users?q=" + encodeURIComponent(search) + "&type=" + type + "&offset=" + offset + "&limit=50"), [search, offset, type]);
  const rows = list.data?.users || [];
  const total = list.data?.total || 0;

  return (
    <div className="stack">
      <div className="card stack">
        <form className="row" onSubmit={(e) => { e.preventDefault(); setOffset(0); setSearch(q); }}>
          <select value={type} onChange={(e) => { setOffset(0); setType(e.target.value); }}>
            <option value="">Everyone</option>
            {TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            <option value="none">No type yet</option>
          </select>
          <input style={{ flex: 1 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by email or name" />
          <button className="primary">Search</button>
        </form>
        <ErrorBox error={list.error} />
        <table>
          <thead><tr><th>Person</th><th>Type</th><th>Status</th><th>Orgs</th><th>Last sign-in</th><th>Joined</th></tr></thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} className={"clickable" + (selected === u.id ? " on" : "")} onClick={() => setSelected(u.id)}>
                <td>{u.name || u.email}<div className="sub">{u.email}</div></td>
                <td>{typeLabel(u.account_type)}</td>
                <td><Chips u={u} />{u.failed_24h > 0 && <div className="sub">{u.failed_24h} failed sign-ins today</div>}</td>
                <td>{u.orgs}</td>
                <td>{fmtDate(u.last_login_at) || "never"}</td>
                <td>{fmtDate(u.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <span className="sub">{total} {total === 1 ? "person" : "people"}</span>
          <span className="row">
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button>
            <button disabled={offset + 50 >= total} onClick={() => setOffset(offset + 50)}>Next</button>
          </span>
        </div>
      </div>
      {selected && <UserPanel id={selected} onChanged={() => void list.reload()} onGone={() => { setSelected(""); void list.reload(); }} />}
    </div>
  );
}

function UserPanel({ id, onChanged, onGone }: { id: string; onChanged: () => void; onGone: () => void }) {
  const guard = useSudo();
  const d = useLoad(() => api.get<UserDetail>("/api/admin/users/" + id), [id]);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [link, setLink] = useState("");
  const u = d.data;

  async function run(fn: () => Promise<unknown>, done: string) {
    setMsg(""); setError(""); setLink("");
    try {
      await guard(fn);
      setMsg(done);
      await d.reload();
      onChanged();
    } catch (e) {
      if (errText(e) !== "cancelled") setError(errText(e));
    }
  }

  if (!u) return <div className="card"><ErrorBox error={d.error} /></div>;
  const base = "/api/admin/users/" + u.id;

  return (
    <div className="card stack">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 style={{ margin: 0 }}>{u.name || u.email}</h2>
          <div className="sub">{u.email} · {typeLabel(u.account_type)} · joined {fmtDate(u.created_at)} · confirmed by {u.verified_via || "nothing yet"}</div>
          <Chips u={u} />
        </div>
      </div>
      {msg && <div className="alert ok" role="status">{msg}</div>}
      {link && (
        <div className="stack">
          <p className="sub" style={{ margin: 0 }}>One-time link, valid for 10 minutes. Send it to them privately.</p>
          <div className="token-box mono">{link}</div>
          <div className="row"><button onClick={() => void navigator.clipboard.writeText(link)}>Copy link</button></div>
        </div>
      )}
      <ErrorBox error={error} />
      <div className="row wrap">
        <button onClick={() => void run(() => api.post(base + "/reset-email"), "Password reset email sent.")}>Email a reset link</button>
        <button onClick={() => void (async () => {
          setMsg(""); setError("");
          try { const r = await guard(() => api.post<{ link: string }>(base + "/reset-link")); setLink(r.link); }
          catch (e) { if (errText(e) !== "cancelled") setError(errText(e)); }
        })()}>Create one-time reset link</button>
        {u.locked && <button onClick={() => void run(() => api.post(base + "/unlock"), "Account unlocked.")}>Unlock sign-in</button>}
        {u.two_factor && <button onClick={() => {
          if (confirm("Turn off two-step sign-in for " + u.email + "? Do this only after confirming who they are, for example a lost phone.")) {
            void run(() => api.post(base + "/two-factor/reset"), "Two-step sign-in turned off and every device signed out.");
          }
        }}>Turn off two-step sign-in</button>}
        <button onClick={() => void run(() => api.post(base + "/signout"), "Signed out on every device.")}>Sign out everywhere</button>
        {!u.verified && <button onClick={() => void run(() => api.post(base + "/verify"), "Email marked as confirmed.")}>Mark email confirmed</button>}
        <button className={u.admin ? "" : "danger"} onClick={() => {
          if (u.admin || confirm("Make " + u.email + " a platform owner? They will control every district, college, organization, account, setting, and billing record.")) {
            void run(() => api.post(base + "/admin", { on: !u.admin }), u.admin ? "Platform owner access removed." : "Now a platform owner.");
          }
        }}>
          {u.admin ? "Remove platform owner" : "Make platform owner"}
        </button>
        <button className={u.disabled ? "" : "danger"} onClick={() => void run(() => api.post(base + "/disabled", { on: !u.disabled }), u.disabled ? "Account enabled." : "Account disabled and signed out.")}>
          {u.disabled ? "Enable account" : "Disable account"}
        </button>
        <button className="danger" onClick={() => {
          if (confirm("Delete " + u.email + "? This removes their account and memberships and cannot be undone.")) {
            void (async () => {
              try { await guard(() => api.del(base)); onGone(); }
              catch (e) { if (errText(e) !== "cancelled") setError(errText(e)); }
            })();
          }
        }}>Delete account</button>
      </div>

      <div className="grid-2">
        <div className="stack">
          <h3>Organizations</h3>
          {u.memberships.length === 0 && <p className="sub">None.</p>}
          {u.memberships.map((m) => <div key={m.membership_id}>{m.org} <span className="sub">· {m.school} · {m.role}</span></div>)}
          <h3>School emails</h3>
          {u.school_emails.length === 0 && <p className="sub">None.</p>}
          {u.school_emails.map((s) => <div key={s.email} className="mono">{s.email} <span className="sub">{s.verified ? "verified" : "not verified"}</span></div>)}
          <h3>School sign-in</h3>
          {u.identities.length === 0 && <p className="sub">Not linked.</p>}
          {u.identities.map((i) => <div key={i.provider + i.email}>{i.provider} <span className="sub">· {i.email} · {fmtDate(i.last_used_at)}</span></div>)}
        </div>
        <div className="stack">
          <h3>Active sessions ({u.sessions.length})</h3>
          {u.sessions.slice(0, 8).map((s, i) => (
            <div key={i} className="sub">{fmtDate(s.last_seen_at || s.created_at)} · {s.user_agent.slice(0, 70) || "unknown device"}</div>
          ))}
          <h3>Sign-in failures</h3>
          <div className="sub">{u.failed_15m} in the last 15 minutes, {u.failed_24h} today</div>
        </div>
      </div>
      <details>
        <summary className="sub">Recent activity ({u.events.length})</summary>
        <table>
          <tbody>
            {u.events.map((e, i) => (
              <tr key={i}><td>{fmtDate(e.at)}</td><td className="mono">{e.action}</td><td className="mono">{e.ip}</td></tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
