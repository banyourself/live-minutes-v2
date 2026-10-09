import { useEffect, useState } from "react";
import { useExamples } from "../examples";
import { SudoProvider, useSudo } from "./admin/sudo";
import { Link, useSearchParams } from "react-router-dom";
import { api, can, ROLE_LABEL, ROLES, type AIConn, type Org, type Role } from "../api";
import { useSession } from "../session";
import { ErrorBox, errText, fmtDate, useLoad } from "../ui";
import { AddAiForm, ConnList, TaskPanel, UsagePanel } from "../components/AiPanels";
import Officers from "./Officers";
import ZoomChecklist from "../components/ZoomChecklist";
import { UsageMeter, type Usage } from "../components/Assistant";

interface Member { id: string; email: string; name: string; role: Role; effective_role: Role; positions: string[] }
interface Invite { id: string; email: string; role: Role; expired: boolean }
interface CaptureToken { id: string; label: string; created_at: number; last_used_at: number | null }
interface JoinReq { id: string; name: string; email: string; school_email: string; message: string; created_at: number }
interface AuditEvent { at: number; action: string; user: string; detail: Record<string, unknown> }

export default function Settings() {
  const { org, refresh } = useSession();
  const [params, setParams] = useSearchParams();
  const owner = can(org!.role, "owner");
  const member = can(org!.role, "member");
  const solo = !!org!.personal;
  const tabs: [string, string][] = member ? [["org", "General"], ...(solo ? [] : [["members", "Members"], ["officers", "Officers"]] as [string, string][]),
    ["ai", "AI"], ["zoom", "Zoom"], ["capture", "Capture devices"], ...(owner ? [["audit", "Activity log"] as [string, string]] : [])] : [["org", "General"]];
  const asked = params.get("tab") || "";
  const tab = tabs.some(([k]) => k === asked) ? asked : "org";
  const setTab = (k: string) => setParams({ tab: k }, { replace: true });
  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker">Administration</div>
          <h1>Settings</h1>
          <p className="sub">{org!.name} · {solo ? "Personal workspace" : org!.district}</p>
        </div>
      </div>
      <div className="tabs" role="group" aria-label="Settings sections">
        {tabs.map(([k, label]) => <button key={k} className={tab === k ? "on" : ""} aria-pressed={tab === k} onClick={() => setTab(k)}>{label}</button>)}
      </div>
      <p className="sub" style={{ marginTop: -6 }}>Your own password, notifications, and AI are under <Link to="/account">My account</Link>.</p>
      {tab === "ai" && <AISettings orgId={org!.id} role={org!.role} solo={solo} />}
      {tab === "org" && <div className="stack"><OrgSettings orgId={org!.id} owner={owner} onSaved={() => void refresh()} /><SudoProvider><DeleteOrg orgId={org!.id} /></SudoProvider></div>}
      {tab === "members" && <Members orgId={org!.id} owner={owner} />}
      {tab === "officers" && <Officers orgId={org!.id} />}
      {tab === "zoom" && <div className="stack"><ZoomSettings orgId={org!.id} role={org!.role} /><ZoomChecklist orgId={org!.id} /></div>}
      {tab === "capture" && <Capture orgId={org!.id} />}
      {tab === "audit" && owner && <Audit orgId={org!.id} />}
    </>
  );
}

function AISettings({ orgId, role, solo }: { orgId: string; role: Role; solo: boolean }) {
  const conns = useLoad(() => api.get<{ connections: AIConn[]; personal_allowed: boolean }>("/api/ai/available?org_id=" + orgId), [orgId]);
  const editable = can(role, "secretary");
  const usage = useLoad(() => can(role, "member") ? api.get<{ usage: Usage }>("/api/assistant/status?org_id=" + orgId) : Promise.resolve(null), [orgId, role]);
  return (
    <div className="stack">
      {usage.data && !editable && (
        <div className="card stack">
          <h2>AI use and limits</h2>
          <UsageMeter usage={usage.data.usage} />
        </div>
      )}
      <div className="grid-2">
        <ConnList title={solo ? "AIs this workspace can use" : "AIs this organization can use"} connections={conns.data?.connections || []}
          onChanged={() => void conns.reload()} empty={solo ? "No AI yet. Add one." : "No AI yet. Add one, or ask your college IT to share one."} />
        {editable && <AddAiForm scope="org" scopeId={orgId} onAdded={() => void conns.reload()} />}
      </div>
      <div className="alert">Using ChatGPT, Codex, Claude, or another AI app you already pay for? Those connect to your own account, not
        to {solo ? "this workspace" : "this organization"}, so they are not listed here. See them, and disconnect them, under{" "}
        <Link to="/account?tab=ai">My account, AI</Link>. You also get a notification and an email each time a new app connects.</div>
      {conns.data && !conns.data.personal_allowed && <div className="alert warn">Your district or college turned off personal AI keys for organizations here.</div>}
      {editable && <TaskPanel scope="org" scopeId={orgId} />}
      {editable && <UsagePanel scope="org" scopeId={orgId} />}
    </div>
  );
}

function DeleteOrg({ orgId }: { orgId: string }) {
  const { org, refresh } = useSession();
  const solo = !!org?.personal;
  const guard = useSudo();
  const o = useLoad(() => api.get<Org>("/api/orgs/" + orgId), [orgId]);
  const [error, setError] = useState("");
  if (!o.data?.can_delete) return null;
  const name = o.data.name;
  async function remove() {
    const typed = prompt("This permanently deletes " + name + " with all of its meetings, recordings, and minutes. Type the " + (solo ? "workspace" : "organization") + "'s name to confirm.");
    if (!typed) return;
    setError("");
    try {
      await guard(() => api.del("/api/orgs/" + orgId + "?confirm=" + encodeURIComponent(typed)));
      await refresh();
      location.assign("/dashboard");
    } catch (e) {
      setError(errText(e));
    }
  }
  return (
    <div className="card stack danger-zone" style={{ maxWidth: 820 }}>
      <h2>Delete this {solo ? "workspace" : "organization"}</h2>
      <p className="sub" style={{ margin: 0 }}>{solo ? "Deleting removes every meeting, recording, transcript, and minutes file in your personal workspace. It cannot be undone."
        : "Your college or district IT lets organizations like this one be deleted by positions that have that permission. Deleting removes every meeting, recording, transcript, minutes file, and member. It cannot be undone."}</p>
      <div className="row"><button className="danger" onClick={() => void remove()}>Delete {solo ? "workspace" : "organization"}</button></div>
      <ErrorBox error={error} />
    </div>
  );
}

function OrgSettings({ orgId, owner, onSaved }: { orgId: string; owner: boolean; onSaved: () => void }) {
  const { me, org } = useSession();
  const ex = useExamples();
  const solo = !!org?.personal;
  const admin = !!me?.user.is_platform_admin;
  const o = useLoad(() => api.get<Org>("/api/orgs/" + orgId), [orgId]);
  const [form, setForm] = useState({ name: "", school: "", style_rules: "", aliases: "", shared: "", domains: "" });
  const [archive, setArchive] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!o.data) return;
    setForm({
      name: o.data.name, school: o.data.school, style_rules: o.data.style_rules,
      aliases: o.data.aliases.map((a) => a.from + " = " + a.to).join("\n"),
      shared: (o.data.shared_accounts || []).map((s) => s.name + ": " + s.people.join(", ")).join("\n"),
      domains: o.data.allowed_domains.join(", ")
    });
    setArchive(!!o.data.public_archive);
  }, [o.data]);

  async function save() {
    setError(""); setMsg("");
    try {
      const aliases = form.aliases.split("\n").map((l) => l.split("=")).filter((p) => p.length === 2 && p[0].trim())
        .map(([from, to]) => ({ from: from.trim(), to: to.trim() }));
      const shared_accounts = form.shared.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
        const at = l.indexOf(":");
        const name = (at < 0 ? l : l.slice(0, at)).trim();
        const people = at < 0 ? [] : l.slice(at + 1).split(",").map((p) => p.trim()).filter(Boolean);
        return { name, people };
      }).filter((s) => s.name);
      await api.patch("/api/orgs/" + orgId, { name: form.name, school: form.school, style_rules: form.style_rules, aliases, shared_accounts,
        public_archive: archive });
      if (admin && !solo) await api.put("/api/orgs/" + orgId + "/domains", { domains: form.domains.split(/[\s,]+/).filter(Boolean) });
      setMsg("Saved.");
      onSaved();
    } catch (e) {
      setError(errText(e));
    }
  }

  const f = (k: keyof typeof form) => ({ value: form[k], disabled: !owner,
    onChange: (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value }) });

  return (
    <div className="card stack" style={{ maxWidth: 820 }}>
      {solo ? <label>Workspace name<input {...f("name")} /></label> : (
        <div className="grid-2">
          <label>Organization name<input {...f("name")} /></label>
          <label>School<input {...f("school")} /></label>
        </div>
      )}
      <p className="sub" style={{ margin: 0 }}>{solo ? "Meetings, recordings, transcripts, and minutes in your personal workspace are private to you. Download the Word file to share minutes."
        : "Meetings, recordings, transcripts, and minutes are private to members of this organization and the college and district staff who manage it. Download the Word file to share approved minutes."}</p>
      <label>Minutes style rules for the AI (leave empty for the default: one condensed bullet per topic)
        <textarea rows={6} {...f("style_rules")} placeholder="Exactly ONE bullet per agenda topic…" />
      </label>
      <label>Name corrections, one per line (caption name = real name)
        <textarea rows={4} {...f("aliases")} placeholder={"Kevan = Kevin\nKevine = Kevin"} />
      </label>
      <label>Shared accounts, one per line (the Zoom name several people speak from: the people who use it)
        <textarea rows={3} {...f("shared")} placeholder={ex.shared} />
      </label>
      <p className="sub" style={{ margin: 0 }}>The AI tells people on a shared account apart from context, such as "This is Kevin" before
        someone speaks or being called on by name, and marks anything it cannot tell with [verify].</p>
      <label className="setting-row">
        <span>Publish approved minutes on a public page<br />
          <span className="sub">Only approved minutes and their plain-language summaries appear, with a Word download. Drafts, recordings,
            transcripts, votes, and members never do. Turn this on only if your organization posts its minutes publicly, as many
            student governments must under open-meeting laws.</span>
          {archive && <><br /><a href={"/archive/" + orgId} target="_blank" rel="noreferrer">Open the public page</a></>}
        </span>
        <input type="checkbox" checked={archive} disabled={!owner} onChange={(e) => setArchive(e.target.checked)} />
      </label>
      {!solo && (
        <label>School email domains that may create accounts on their own (district-wide, set by the platform administrator)
          <input {...f("domains")} disabled={!admin} placeholder="coastline.edu, cccd.edu" />
        </label>
      )}
      <ErrorBox error={error} />
      {msg && <div className="alert ok" role="status">{msg}</div>}
      {owner && <div className="row"><button className="primary" onClick={() => void save()}>Save</button></div>}
    </div>
  );
}

function Members({ orgId, owner }: { orgId: string; owner: boolean }) {
  const base = "/api/orgs/" + orgId;
  const data = useLoad(() => api.get<{ members: Member[]; invites: Invite[] }>(base + "/members"), [base]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [link, setLink] = useState("");
  const [emailed, setEmailed] = useState("");
  const [error, setError] = useState("");

  async function invite() {
    setError("");
    try {
      const r = await api.post<{ link: string; emailed: boolean }>(base + "/invites", { email, role });
      setLink(r.link); setEmailed(r.emailed ? email : ""); setEmail("");
      await data.reload();
    } catch (e) {
      setError(errText(e));
    }
  }

  async function change(fn: () => Promise<unknown>) {
    setError("");
    try { await fn(); await data.reload(); } catch (e) { setError(errText(e)); }
  }

  return (
    <div className="stack">
      {owner && <JoinRequests base={base} onDone={() => void data.reload()} />}
      {owner && <BulkInvite base={base} onDone={() => void data.reload()} />}
    <div className="grid-3">
      <div className="card">
        <h2>Members</h2>
        <table>
          <thead><tr><th>Person</th><th>Role</th><th /></tr></thead>
          <tbody>
            {(data.data?.members || []).map((m) => (
              <tr key={m.id}>
                <td>{m.name || m.email}<div className="sub">{m.email}</div>
                  {m.positions.length > 0 && <div className="chips">{m.positions.map((p) => <span key={p} className="chip accent">{p}</span>)}</div>}
                </td>
                <td>
                  {owner ? (
                    <select value={m.role} onChange={(e) => void change(() => api.patch(base + "/members/" + m.id, { role: e.target.value }))}>
                      {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                    </select>
                  ) : ROLE_LABEL[m.role]}
                  {m.effective_role !== m.role && <div className="sub">{m.effective_role} while in office</div>}
                </td>
                <td>{owner && <button className="danger" onClick={() => { if (confirm("Remove " + m.email + "?")) void change(() => api.del(base + "/members/" + m.id)); }}>Remove</button>}</td>
              </tr>
            ))}
            {(data.data?.invites || []).map((i) => (
              <tr key={i.id}>
                <td>{i.email}<div className="sub">{i.expired ? "Invite expired; cancel it and invite again" : "Invited, not yet joined"}</div></td>
                <td>{i.role}</td>
                <td>{owner && <button onClick={() => void change(() => api.del(base + "/invites/" + i.id))}>Cancel</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="sub" style={{ marginTop: 10 }}>
          <strong>Full access</strong> is for advisors and presidents: settings, members, officers, and everything else.
          <strong> Runs meetings</strong> is for secretaries: meetings, drafts, and approving minutes. <strong>Members</strong> capture captions
          and download minutes. <strong>Read only</strong> can view. Holding a position under Officers adds its access for the length of
          the term; the Advisor and President positions give full access.
        </p>
      </div>
      {owner && (
        <div className="card stack">
          <h2>Invite someone</h2>
          <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>Role
            <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {["member", "secretary", "viewer", "owner"].map((r) => <option key={r}>{r}</option>)}
            </select>
          </label>
          <ErrorBox error={error} />
          <div className="row"><button className="primary" disabled={!email} onClick={() => void invite()}>Create invite link</button></div>
          {link && (
            <div className="stack">
              <p className="sub">{emailed ? "We emailed this link to " + emailed + ". You can also send it yourself." :
                "Send this link to them."} It works once, for that email address, and expires in a week.</p>
              <div className="token-box mono">{link}</div>
              <button onClick={() => void navigator.clipboard.writeText(link)}>Copy link</button>
            </div>
          )}
        </div>
      )}
    </div>
    </div>
  );
}

function JoinRequests({ base, onDone }: { base: string; onDone: () => void }) {
  const reqs = useLoad(() => api.get<{ requests: JoinReq[] }>(base + "/join-requests"), [base]);
  const [roles, setRoles] = useState<Record<string, Role>>({});
  const [error, setError] = useState("");
  const rows = reqs.data?.requests || [];

  async function decide(id: string, ok: boolean) {
    setError("");
    try {
      if (ok) await api.post(base + "/join-requests/" + id + "/approve", { role: roles[id] || "member" });
      else await api.post(base + "/join-requests/" + id + "/deny");
      await reqs.reload();
      onDone();
    } catch (e) {
      setError(errText(e));
    }
  }

  if (!rows.length) return null;
  return (
    <div className="card stack">
      <h2>Requests to join</h2>
      <p className="sub" style={{ margin: 0 }}>Each person below confirmed a school email at your school. Approve only people you know belong.</p>
      <table>
        <thead><tr><th>Person</th><th>School email</th><th>Role</th><th /></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.name || r.email}<div className="sub">{r.email}{r.message ? " · " + r.message : ""}</div></td>
              <td className="mono">{r.school_email}</td>
              <td>
                <select value={roles[r.id] || "member"} onChange={(e) => setRoles({ ...roles, [r.id]: e.target.value as Role })}>
                  {["member", "secretary", "viewer", "owner"].map((x) => <option key={x}>{x}</option>)}
                </select>
              </td>
              <td className="row">
                <button className="primary" onClick={() => void decide(r.id, true)}>Approve</button>
                <button className="danger" onClick={() => void decide(r.id, false)}>Deny</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ErrorBox error={error} />
    </div>
  );
}

function ZoomSettings({ orgId, role }: { orgId: string; role: Role }) {
  const base = "/api/orgs/" + orgId + "/zoom";
  const [params] = useSearchParams();
  const result = params.get("zoom");
  const z = useLoad(() => api.get<{ available: boolean; connected: boolean; host_email: string; auto_import?: boolean }>(base), [base]);
  const [error, setError] = useState("");
  return (
    <div className="card stack" style={{ maxWidth: 760 }}>
      <h2>Zoom</h2>
      {result === "connected" && z.data?.connected && <div className="alert ok" role="status">Zoom is connected.</div>}
      {result === "denied" && <div className="alert warn" role="status">Zoom was not connected, because access was not allowed.</div>}
      {!z.data?.available ? (
        <p className="sub">The Zoom app is not turned on for this server yet. Until it is, use live captions or import recordings by hand.</p>
      ) : z.data.connected ? (
        <>
          <p>Connected as <strong>{z.data.host_email || "the host account"}</strong>. Recordings and chat files can be imported into meetings.</p>
          <label className="setting-row">
            <span>Import new cloud recordings automatically<br />
              <span className="sub">When this Zoom account finishes a cloud recording, Live Minutes makes a meeting for it, imports its closed
                captions or transcript and chat, and starts the draft if an AI is set up. Secretaries get a notification.</span>
            </span>
            <input type="checkbox" checked={!!z.data.auto_import} disabled={!can(role, "secretary")} onChange={async (e) => {
              try { await api.put(base + "/auto-import", { on: e.target.checked }); await z.reload(); } catch (err) { setError(errText(err)); }
            }} />
          </label>
          <p className="sub">Disconnecting here, or removing Live Minutes from your Zoom account, deletes the saved Zoom sign-in right away.
            Meetings you already imported stay until you delete them.</p>
          {can(role, "secretary") && <div className="row"><button className="danger" onClick={async () => {
            try { await api.del(base); await z.reload(); } catch (e) { setError(errText(e)); }
          }}>Disconnect Zoom</button></div>}
        </>
      ) : (
        <>
          <p className="sub">Sign in with the Zoom account that <strong>hosts</strong> your meetings, such as your own account or your organization's
            shared one. Live Minutes can only read that account's cloud recordings, transcripts, chat, and recording settings. It cannot join,
            record, or change anything. If the account belongs to a school or company, its Zoom admin may need to allow the app first.</p>
          {can(role, "secretary") && <div className="row"><a className="btn primary" href={base + "/connect"}>Connect Zoom</a></div>}
        </>
      )}
      <p className="sub"><Link to="/help/zoom">How the Zoom app works</Link></p>
      <ErrorBox error={error || z.error} />
    </div>
  );
}

function Capture({ orgId }: { orgId: string }) {
  const base = "/api/orgs/" + orgId + "/capture-tokens";
  const list = useLoad(() => api.get<{ tokens: CaptureToken[] }>(base), [base]);
  const [label, setLabel] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  async function run(fn: () => Promise<unknown>) {
    setError("");
    try { await fn(); await list.reload(); } catch (e) { setError(errText(e)); }
  }
  return (
    <div className="stack">
      <ErrorBox error={error || list.error} />
      <div className="grid-3">
        <div className="card">
          <h2>Your capture devices</h2>
          <p className="sub">Tokens let the desktop app or Chrome extension send captions to this organization's open meetings.</p>
          {(list.data?.tokens || []).length === 0 ? <div className="empty">No tokens yet.</div> : (
            <table>
              <thead><tr><th>Device</th><th>Created</th><th>Last used</th><th /></tr></thead>
              <tbody>
                {list.data!.tokens.map((t) => (
                  <tr key={t.id}>
                    <td>{t.label}</td><td className="sub">{fmtDate(t.created_at)}</td><td className="sub">{fmtDate(t.last_used_at) || "never"}</td>
                    <td><button className="danger" onClick={() => { if (confirm("Revoke " + t.label + "? That device stops sending captions.")) void run(() => api.del(base + "/" + t.id)); }}>Revoke</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="card stack">
          <h2>New token</h2>
          <label>Device name<input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Kevin's laptop" /></label>
          <div className="row"><button className="primary" onClick={() => void run(async () => {
            const r = await api.post<{ token: string }>(base, { label });
            setToken(r.token); setLabel("");
          })}>Create token</button></div>
          {token && <><p className="sub">Copy it now. It is shown only once.</p><div className="token-box mono">{token}</div>
            <button onClick={() => void navigator.clipboard.writeText(token)}>Copy</button></>}
          <p className="sub">Server address to enter in the app: <span className="mono">{location.origin}</span></p>
        </div>
      </div>
    </div>
  );
}

function Audit({ orgId }: { orgId: string }) {
  const a = useLoad(() => api.get<{ events: AuditEvent[] }>("/api/orgs/" + orgId + "/audit"), [orgId]);
  return (
    <div className="card">
      <h2>Activity log</h2>
      <table>
        <thead><tr><th>When</th><th>Who</th><th>What</th><th>Details</th></tr></thead>
        <tbody>
          {(a.data?.events || []).map((e, i) => (
            <tr key={i}>
              <td className="sub">{fmtDate(e.at)}</td><td>{e.user}</td><td className="mono">{e.action}</td>
              <td className="sub mono">{Object.entries(e.detail || {}).map(([k, v]) => k + "=" + String(v)).join(" ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BulkInvite({ base, onDone }: { base: string; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [send, setSend] = useState(true);
  const [result, setResult] = useState<{ invited: { row: number; email: string; role: string; link: string }[]; skipped: { row: number; email: string; reason: string }[] } | null>(null);
  const [error, setError] = useState("");

  async function go() {
    setError(""); setResult(null);
    try {
      setResult(await api.post(base + "/invites/bulk", { csv: text, role, send }));
      onDone();
    } catch (e) {
      setError(errText(e));
    }
  }

  if (!open) return <div className="row"><button onClick={() => setOpen(true)}>Invite many people</button></div>;
  return (
    <div className="card stack">
      <h2>Invite many people</h2>
      <p className="sub" style={{ margin: 0 }}>Paste a list or a CSV with columns email, role, name (role and name are optional). Up to 200 at a time.</p>
      <textarea rows={6} className="mono" value={text} onChange={(e) => setText(e.target.value)}
        aria-label="List of people to invite" placeholder={"email,role,name\nkevin@student.example.edu,member,Kevin\nmember@student.example.edu"} />
      <div className="row">
        <label className="row" style={{ textTransform: "none", letterSpacing: "normal" }}>Default role
          <select value={role} onChange={(e) => setRole(e.target.value as Role)} style={{ width: "auto" }}>
            {["member", "secretary", "viewer", "owner"].map((r) => <option key={r}>{r}</option>)}
          </select>
        </label>
        <label className="row" style={{ textTransform: "none", letterSpacing: "normal" }}>
          <input type="checkbox" checked={send} onChange={(e) => setSend(e.target.checked)} /> Email each person their invite
        </label>
      </div>
      <ErrorBox error={error} />
      <div className="row">
        <button className="primary" disabled={!text.trim()} onClick={() => void go()}>Create invites</button>
        <button onClick={() => { setOpen(false); setResult(null); }}>Close</button>
      </div>
      {result && (
        <div className="stack">
          <div className="alert ok" role="status">{result.invited.length} invited{result.skipped.length ? ", " + result.skipped.length + " skipped" : ""}.</div>
          {result.skipped.length > 0 && (
            <table>
              <thead><tr><th>Row</th><th>Email</th><th>Skipped because</th></tr></thead>
              <tbody>{result.skipped.map((x) => <tr key={x.row}><td className="mono">{x.row}</td><td>{x.email}</td><td className="sub">{x.reason}</td></tr>)}</tbody>
            </table>
          )}
          {!send && result.invited.length > 0 && (
            <div className="token-box mono" style={{ whiteSpace: "pre-wrap" }}>{result.invited.map((x) => x.email + "  " + x.link).join("\n")}</div>
          )}
        </div>
      )}
    </div>
  );
}
