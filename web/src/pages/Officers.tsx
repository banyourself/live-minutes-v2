import { useState } from "react";
import { api } from "../api";
import { useSession } from "../session";
import { ErrorBox, errText, useLoad } from "../ui";

interface Position {
  id: string; name: string; rank: number; access: string; permissions: string[]; account_types: string[];
  max_holders: number; holders: number; can_edit: boolean; can_assign: boolean;
}
interface Term {
  id: string; position_id: string; position: string; rank: number; user_id: string; name: string; email: string;
  starts_at: number; ends_at: number | null; remove_at_end: boolean; state: string; ended_at: number | null;
  end_reason: string; can_end: boolean; can_change: boolean;
}
interface Overview {
  positions: Position[]; terms: Term[]; history: Term[];
  settings: { owners_manage_officers: boolean; require_review: boolean };
  permission_labels: { id: string; label: string }[];
  me: { can_edit_permissions: boolean; above: boolean; edit_rank: number | null; permissions: string[]; access: string; positions: string[] };
}
interface Member { id: string; user_id: string; email: string; name: string }

const ACCESS: Record<string, string> = {
  owner: "Owner: settings, members, and everything below",
  secretary: "Secretary: run meetings, edit and approve minutes",
  member: "Member: capture captions and download minutes",
  viewer: "Viewer: read only"
};
const TYPES: [string, string][] = [["student", "Student"], ["faculty", "Faculty"], ["staff", "Staff"], ["it", "IT"]];
const LENGTHS: [string, string][] = [["permanent", "Permanent"], ["6", "6 months"], ["12", "1 year"], ["24", "2 years"], ["date", "Until a date"]];

function dayStart(v: string) {
  return new Date(v + "T00:00").getTime() / 1000;
}

function today() {
  const d = new Date();
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}

function endFrom(start: number, length: string, until: string) {
  if (length === "permanent") return null;
  if (length === "date") return until ? dayStart(until) + 86399 : NaN;
  const d = new Date(start * 1000);
  d.setMonth(d.getMonth() + Number(length));
  return d.getTime() / 1000;
}

function day(ts: number | null) {
  return ts ? new Date(ts * 1000).toLocaleDateString(undefined, { dateStyle: "medium" }) : "";
}

export default function Officers({ orgId }: { orgId: string }) {
  const base = "/api/orgs/" + orgId;
  const data = useLoad(() => api.get<Overview>(base + "/officers"), [base]);
  const members = useLoad(() => api.get<{ members: Member[] }>(base + "/members"), [base]);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  async function run(fn: () => Promise<unknown>, done: string) {
    setError(""); setMsg("");
    try {
      await fn();
      setMsg(done);
      await data.reload();
    } catch (e) {
      setError(errText(e));
    }
  }

  const d = data.data;
  if (!d) return <ErrorBox error={data.error} />;
  const assignable = d.positions.filter((p) => p.can_assign);
  const labels = Object.fromEntries(d.permission_labels.map((x) => [x.id, x.label]));

  return (
    <div className="stack">
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error} />
      <div className="card stack">
        <h2>Current officers</h2>
        {d.me.positions.length > 0 && <p className="sub" style={{ margin: 0 }}>You hold: {d.me.positions.join(", ")}.</p>}
        {d.terms.length === 0 ? <div className="empty">No officers yet.</div> : (
          <table>
            <thead><tr><th>Position</th><th>Person</th><th>Term</th><th /></tr></thead>
            <tbody>
              {d.terms.map((t) => (
                <TermRow key={t.id} t={t} base={base} run={run} />
              ))}
            </tbody>
          </table>
        )}
      </div>
      {assignable.length > 0 && <AssignForm base={base} positions={assignable} members={members.data?.members || []} run={run} />}
      <PositionsCard d={d} base={base} labels={labels} run={run} />
      {d.history.length > 0 && (
        <div className="card">
          <details>
            <summary>Past terms ({d.history.length})</summary>
            <table style={{ marginTop: 10 }}>
              <thead><tr><th>Position</th><th>Person</th><th>Served</th><th>Ended</th></tr></thead>
              <tbody>
                {d.history.map((t) => (
                  <tr key={t.id}>
                    <td>{t.position}</td>
                    <td>{t.name || t.email}</td>
                    <td className="sub">{day(t.starts_at)} to {day(t.ended_at)}</td>
                    <td className="sub">{t.end_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </div>
      )}
    </div>
  );
}

function TermRow({ t, base, run }: { t: Term; base: string; run: (fn: () => Promise<unknown>, done: string) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [length, setLength] = useState(t.ends_at ? "date" : "permanent");
  const [until, setUntil] = useState(t.ends_at ? new Date(t.ends_at * 1000).toISOString().slice(0, 10) : "");
  const [remove, setRemove] = useState(t.remove_at_end);
  const { me } = useSession();
  const mine = t.user_id === me?.user.id;

  async function save() {
    const end = endFrom(Math.max(t.starts_at, Date.now() / 1000), length, until);
    await run(() => api.patch(base + "/terms/" + t.id, { ends_at: end, remove_at_end: remove }), "Term updated.");
    setEditing(false);
  }

  return (
    <tr>
      <td><strong>{t.position}</strong></td>
      <td>{t.name || t.email}<div className="sub">{t.email}</div></td>
      <td>
        {editing ? (
          <div className="stack">
            <select value={length} onChange={(e) => setLength(e.target.value)}>
              {LENGTHS.map(([k, l]) => <option key={k} value={k}>{l}{k !== "permanent" && k !== "date" ? " from today" : ""}</option>)}
            </select>
            {length === "date" && <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} />}
            <label className="row" style={{ textTransform: "none", letterSpacing: "normal" }}>
              <input type="checkbox" checked={remove} onChange={(e) => setRemove(e.target.checked)} /> Remove from the organization when it ends
            </label>
          </div>
        ) : (
          <>
            {t.state === "upcoming" && <span className="chip accent">Starts {day(t.starts_at)}</span>}{" "}
            <span className="sub">Since {day(t.starts_at)}</span>
            <div>{t.ends_at ? "Until " + day(t.ends_at) : "Permanent"}{t.remove_at_end && <span className="sub"> · leaves the organization after</span>}</div>
          </>
        )}
      </td>
      <td className="row">
        {editing ? (
          <>
            <button className="primary" onClick={() => void save()}>Save</button>
            <button onClick={() => setEditing(false)}>Cancel</button>
          </>
        ) : (
          <>
            {t.can_change && <button onClick={() => setEditing(true)}>Change term</button>}
            {t.can_end && (
              <button className="danger" onClick={() => {
                if (confirm(mine ? "Step down as " + t.position + "?" : "End " + (t.name || t.email) + "'s term as " + t.position + " now?"))
                  void run(() => api.post(base + "/terms/" + t.id + "/end"), "Term ended.");
              }}>{mine ? "Step down" : "End term"}</button>
            )}
          </>
        )}
      </td>
    </tr>
  );
}

function AssignForm({ base, positions, members, run }: {
  base: string; positions: Position[]; members: Member[]; run: (fn: () => Promise<unknown>, done: string) => Promise<void>;
}) {
  const [who, setWho] = useState("");
  const [pos, setPos] = useState("");
  const [start, setStart] = useState(today());
  const [length, setLength] = useState("12");
  const [until, setUntil] = useState("");
  const [remove, setRemove] = useState(false);
  const chosen = positions.find((p) => p.id === pos);

  async function assign() {
    const startTs = start === today() ? null : dayStart(start);
    const end = endFrom(startTs ?? Date.now() / 1000, length, until);
    if (Number.isNaN(end)) return;
    await run(() => api.post(base + "/terms", { position_id: pos, user_id: who, starts_at: startTs, ends_at: end, remove_at_end: remove }),
      "Position assigned.");
    setWho("");
  }

  return (
    <div className="card stack">
      <h2>Assign a position</h2>
      <div className="grid-2">
        <label>Person
          <select value={who} onChange={(e) => setWho(e.target.value)}>
            <option value="">Choose a member…</option>
            {members.map((m) => <option key={m.user_id} value={m.user_id}>{m.name ? m.name + " (" + m.email + ")" : m.email}</option>)}
          </select>
        </label>
        <label>Position
          <select value={pos} onChange={(e) => setPos(e.target.value)}>
            <option value="">Choose a position…</option>
            {positions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <label>Starts<input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label>Term
          <select value={length} onChange={(e) => setLength(e.target.value)}>
            {LENGTHS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        {length === "date" && <label>Ends on<input type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></label>}
      </div>
      <label className="setting-row">
        <span>Remove them from the organization when the term ends</span>
        <input type="checkbox" checked={remove} onChange={(e) => setRemove(e.target.checked)} />
      </label>
      {chosen && chosen.account_types.length > 0 && (
        <p className="sub" style={{ margin: 0 }}>{chosen.name} is only for {chosen.account_types.map((t) => TYPES.find((x) => x[0] === t)?.[1] || t).join(" or ")} accounts
          with a confirmed school email.</p>
      )}
      <p className="sub" style={{ margin: 0 }}>Access from a position ends on its own when the term ends.</p>
      <div className="row"><button className="primary" disabled={!who || !pos || (length === "date" && !until)} onClick={() => void assign()}>Assign</button></div>
    </div>
  );
}

function PositionsCard({ d, base, labels, run }: {
  d: Overview; base: string; labels: Record<string, string>; run: (fn: () => Promise<unknown>, done: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState<string>("");
  const editor = d.me.can_edit_permissions;
  const ceiling = d.me.edit_rank ?? 0;
  return (
    <div className="card stack">
      <h2>Positions and permissions</h2>
      <p className="sub" style={{ margin: 0 }}>
        Higher-ranked positions manage lower ones. Only advisors, college IT, district IT, and the platform owner can change
        positions and what they can do{editor && !d.me.above ? ", and only for positions ranked below their own" : ""}.
      </p>
      <table>
        <thead><tr><th>Position</th><th>Rank</th><th>Access</th><th>Can also</th><th>Who can hold it</th><th /></tr></thead>
        <tbody>
          {d.positions.map((p) => editing === p.id ? (
            <tr key={p.id}><td colSpan={6}>
              <PositionForm initial={p} labels={labels} allowed={d.me.permissions} ceiling={ceiling} myAccess={d.me.access}
                onCancel={() => setEditing("")}
                onSave={async (v) => { await run(() => api.patch(base + "/positions/" + p.id, v), p.name + " saved."); setEditing(""); }} />
            </td></tr>
          ) : (
            <tr key={p.id}>
              <td><strong>{p.name}</strong><div className="sub">{p.holders} holding{p.max_holders ? " of " + p.max_holders : ""}</div></td>
              <td className="mono">{p.rank}</td>
              <td className="sub">{(ACCESS[p.access] || p.access).split(":")[0]}</td>
              <td><div className="chips">{p.permissions.length ? p.permissions.map((x) => <span key={x} className="chip" title={labels[x]}>{x.replace("_", " ")}</span>) : <span className="sub">nothing extra</span>}</div></td>
              <td className="sub">{p.account_types.length ? p.account_types.map((t) => TYPES.find((x) => x[0] === t)?.[1] || t).join(", ") : "Any member"}</td>
              <td className="row">
                {p.can_edit && <button onClick={() => setEditing(p.id)}>Edit</button>}
                {p.can_edit && <button className="danger" onClick={() => {
                  if (confirm("Remove the " + p.name + " position? Everyone holding it loses it now.")) void run(() => api.del(base + "/positions/" + p.id), p.name + " removed.");
                }}>Remove</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {editor && (editing === "new" ? (
        <PositionForm labels={labels} allowed={d.me.permissions} ceiling={ceiling} myAccess={d.me.access} onCancel={() => setEditing("")}
          onSave={async (v) => { await run(() => api.post(base + "/positions", v), v.name + " added."); setEditing(""); }} />
      ) : <div className="row"><button onClick={() => setEditing("new")}>Add a position</button></div>)}
      {editor && <OfficerSettings base={base} settings={d.settings} run={run} />}
      {!editor && (
        <p className="sub" style={{ margin: 0 }}>
          {d.settings.owners_manage_officers ? "Organization owners can assign and end terms for positions below Advisor." :
            "Organization owners need an officer position to assign positions."}{" "}
          {d.settings.require_review ? "Minutes need review before approval when someone holds a reviewing position." : "Review before approval is optional."}
        </p>
      )}
    </div>
  );
}

interface PositionValue { name: string; rank: number; access: string; permissions: string[]; account_types: string[]; max_holders: number }

function PositionForm({ initial, labels, allowed, ceiling, myAccess, onSave, onCancel }: {
  initial?: Position; labels: Record<string, string>; allowed: string[]; ceiling: number; myAccess: string;
  onSave: (v: PositionValue) => Promise<void>; onCancel: () => void;
}) {
  const [v, setV] = useState<PositionValue>({
    name: initial?.name || "", rank: initial?.rank ?? Math.min(50, ceiling - 1), access: initial?.access || "member",
    permissions: initial?.permissions || [], account_types: initial?.account_types || [], max_holders: initial?.max_holders || 0
  });
  const order = ["viewer", "member", "secretary", "owner"];
  const toggle = (k: "permissions" | "account_types", x: string) =>
    setV({ ...v, [k]: v[k].includes(x) ? v[k].filter((y) => y !== x) : [...v[k], x] });
  return (
    <div className="stack" style={{ padding: "8px 0" }}>
      <div className="grid-2">
        <label>Name<input value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} placeholder="Historian" /></label>
        <label>Rank (higher manages lower{ceiling < 1000000 ? "; below " + ceiling : ""})
          <input type="number" min={1} max={Math.min(999, ceiling - 1)} value={v.rank} onChange={(e) => setV({ ...v, rank: Number(e.target.value) })} />
        </label>
        <label>Access in Live Minutes
          <select value={v.access} onChange={(e) => setV({ ...v, access: e.target.value })}>
            {order.filter((a) => order.indexOf(a) <= order.indexOf(myAccess)).map((a) => <option key={a} value={a}>{ACCESS[a]}</option>)}
          </select>
        </label>
        <label>How many people can hold it at once (0 for no limit)
          <input type="number" min={0} max={500} value={v.max_holders} onChange={(e) => setV({ ...v, max_holders: Number(e.target.value) })} />
        </label>
      </div>
      <div>
        <div className="lbl">Can also</div>
        {Object.entries(labels).map(([k, l]) => (
          <label key={k} className="setting-row">
            <span>{l}</span>
            <input type="checkbox" checked={v.permissions.includes(k)} disabled={!allowed.includes(k)} onChange={() => toggle("permissions", k)} />
          </label>
        ))}
      </div>
      <div>
        <div className="lbl">Only these account types (none checked means any member)</div>
        <div className="row">
          {TYPES.map(([k, l]) => (
            <label key={k} className="row" style={{ textTransform: "none", letterSpacing: "normal" }}>
              <input type="checkbox" checked={v.account_types.includes(k)} onChange={() => toggle("account_types", k)} /> {l}
            </label>
          ))}
        </div>
      </div>
      <div className="row">
        <button className="primary" disabled={!v.name.trim()} onClick={() => void onSave(v)}>Save</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

function OfficerSettings({ base, settings, run }: {
  base: string; settings: Overview["settings"]; run: (fn: () => Promise<unknown>, done: string) => Promise<void>;
}) {
  return (
    <div>
      <label className="setting-row">
        <span>Organization owners can assign and end terms for positions below Advisor</span>
        <input type="checkbox" checked={settings.owners_manage_officers}
          onChange={(e) => void run(() => api.put(base + "/officer-settings", { owners_manage_officers: e.target.checked }), "Saved.")} />
      </label>
      <label className="setting-row">
        <span>Minutes need review before approval when someone holds a reviewing position</span>
        <input type="checkbox" checked={settings.require_review}
          onChange={(e) => void run(() => api.put(base + "/officer-settings", { require_review: e.target.checked }), "Saved.")} />
      </label>
      <p className="sub" style={{ marginBottom: 0 }}>Changes apply right away.</p>
    </div>
  );
}
