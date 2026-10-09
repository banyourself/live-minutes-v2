import { useEffect, useState } from "react";
import { api } from "../../api";
import { ErrorBox, errText, fmtDate, useLoad } from "../../ui";
import { useSudo } from "./sudo";

interface LibTemplate { id: string; name: string; description: string; filename: string; mode: string; uses: number; created_at: number; owner: string }

export function LibraryPanel({ base, district }: { base: string; district: boolean }) {
  const list = useLoad(() => api.get<{ templates: LibTemplate[] }>(base + "/library"), [base]);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function add() {
    if (!file) return;
    setBusy(true); setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("name", name || file.name.replace(/\.[^.]+$/, ""));
      form.append("description", description);
      await api.post(base + "/library", form);
      setFile(null); setName(""); setDescription("");
      await list.reload();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(t: LibTemplate) {
    if (!confirm("Remove " + t.name + " from the library? Organizations that already copied it keep their copy.")) return;
    setError("");
    try { await api.del(base + "/library/" + t.id); await list.reload(); } catch (e) { setError(errText(e)); }
  }

  const rows = list.data?.templates || [];
  return (
    <div className="grid-3">
      <div className="card">
        <h2>{district ? "District" : "College"} template library</h2>
        <p className="sub">Every organization {district ? "in the district" : "at the college"} can copy these into its own templates and change its copy.</p>
        {rows.length === 0 ? <div className="empty">No shared templates yet.</div> : (
          <table>
            <thead><tr><th>Template</th><th>Copies</th><th>Added</th><th /></tr></thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id}>
                  <td><strong>{t.name}</strong><div className="sub">{t.description || t.filename}</div></td>
                  <td className="mono">{t.uses}</td>
                  <td className="sub">{fmtDate(t.created_at)}</td>
                  <td><button className="danger" onClick={() => void remove(t)}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <ErrorBox error={error || list.error} />
      </div>
      <div className="card stack">
        <h2>Add a template</h2>
        <label>File (.docx keeps its format; .pdf, .txt, or .md become a clean template from their topics)
          <input type="file" accept=".docx,.pdf,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </label>
        <label>Name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="Student government agenda" /></label>
        <label>Description<input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Brown Act order of business" /></label>
        <div className="row"><button className="primary" disabled={!file || busy} onClick={() => void add()}>{busy ? "Adding…" : "Add to library"}</button></div>
      </div>
    </div>
  );
}

interface SsoData {
  microsoft_tenants: string[]; google_domains: string[]; auto_setup: boolean; redirect_uri: string;
  google_redirect_uri: string; microsoft_app: boolean; google_app: boolean; client_id: string;
}

export function SchoolSignIn({ base }: { base: string }) {
  const guard = useSudo();
  const data = useLoad(() => api.get<SsoData>(base + "/sso"), [base]);
  const [form, setForm] = useState({ tenants: "", domains: "", auto: true });
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (data.data) setForm({ tenants: data.data.microsoft_tenants.join("\n"), domains: data.data.google_domains.join("\n"), auto: data.data.auto_setup });
  }, [data.data]);

  async function save() {
    setMsg(""); setError("");
    const split = (v: string) => v.split(/[\s,]+/).filter(Boolean);
    try {
      data.setData(await guard(() => api.put<SsoData>(base + "/sso", { microsoft_tenants: split(form.tenants), google_domains: split(form.domains), auto_setup: form.auto })));
      setMsg("Saved. People from these directories can sign in now.");
    } catch (e) {
      if (errText(e) !== "cancelled") setError(errText(e));
    }
  }

  const d = data.data;
  return (
    <div className="grid-3" style={{ alignItems: "start" }}>
      <div className="card stack">
        <h2>School sign-in</h2>
        <p className="sub" style={{ margin: 0 }}>Let students and staff sign in with their school Microsoft or Google account. With automatic setup on,
          their account is created the first time they sign in, their school email is confirmed for the matching college, and they are marked as a
          student or staff based on the email's domain. They still request or get invited to organizations.</p>
        <label>Microsoft Entra tenant IDs, one per line
          <textarea rows={3} value={form.tenants} onChange={(e) => setForm({ ...form, tenants: e.target.value })} placeholder="00000000-0000-0000-0000-000000000000" className="mono" />
        </label>
        <label>Google Workspace domains, one per line
          <textarea rows={2} value={form.domains} onChange={(e) => setForm({ ...form, domains: e.target.value })} placeholder="coastline.edu" className="mono" />
        </label>
        <label className="setting-row">
          <span>Set up accounts automatically on first sign-in</span>
          <input type="checkbox" checked={form.auto} onChange={(e) => setForm({ ...form, auto: e.target.checked })} />
        </label>
        {msg && <div className="alert ok" role="status">{msg}</div>}
        <ErrorBox error={error || data.error} />
        <div className="row"><button className="primary" onClick={() => void save()}>Save</button></div>
      </div>
      <div className="card stack">
        <h2>For your identity team</h2>
        {d && (
          <>
            <div><strong>Microsoft</strong>: {d.microsoft_app ? "the Live Minutes app is registered on this server." : "this server does not have a Microsoft app yet; ask the platform owner."}</div>
            {d.client_id && <div className="sub">Application (client) ID: <span className="mono">{d.client_id}</span></div>}
            <div className="sub">Redirect URI: <span className="mono" style={{ wordBreak: "break-all" }}>{d.redirect_uri}</span></div>
            <div className="sub">Grant admin consent for the app in your tenant, and find the tenant ID under Microsoft Entra ID, Overview.</div>
            <div style={{ marginTop: 6 }}><strong>Google</strong>: {d.google_app ? "Google sign-in is turned on for this server." : "Google sign-in is not set up on this server."}</div>
            <div className="sub">Only accounts whose Workspace domain is listed here get automatic setup; other Google accounts sign in as usual.</div>
          </>
        )}
      </div>
    </div>
  );
}
