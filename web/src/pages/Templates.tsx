import { useState } from "react";
import { api, can, type Org, type Outline, type Template } from "../api";
import { useSession } from "../session";
import { ErrorBox, errText, fmtDate, useLoad } from "../ui";
import TemplateDesigner, { blankDesign, downloadFile, Paper, withDefaults, type Design } from "../components/TemplateDesigner";

const SCHOOL_ONLY = ["student-government", "board", "executive", "finance"];

interface Builtin { key: string; name: string; description: string; topics: string[]; design: Design }
type Open = { id: string; name: string; outline: Outline | null; example?: string };
type Editing = { id?: string; source?: string; heading: string; design: Design };

export default function Templates() {
  const { org } = useSession();
  const base = "/api/orgs/" + org!.id;
  const list = useLoad(() => api.get<{ templates: Template[] }>(base + "/templates"), [base]);
  const info = useLoad(() => api.get<Org>(base), [base]);
  const library = useLoad(() => api.get<{ templates: { id: string; name: string; description: string; owner: string; mode: string }[] }>(base + "/library"), [base]);
  const builtin = useLoad(() => api.get<{ templates: Builtin[]; options: { fonts: string[] } }>("/api/templates/builtin"), []);
  const [open, setOpen] = useState<Open | null>(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");
  const [editing, setEditing] = useState<Editing | null>(null);
  const editable = can(org!.role, "secretary");

  async function run(label: string, fn: () => Promise<unknown>, done = "") {
    setBusy(label); setError(""); setMsg("");
    try { await fn(); if (done) setMsg(done); await Promise.all([list.reload(), info.reload(), library.reload()]); }
    catch (e) { setError(errText(e)); }
    finally { setBusy(""); }
  }

  function upload(file: File, purpose: "template" | "example") {
    const form = new FormData();
    form.append("file", file);
    form.append("name", file.name.replace(/\.[^.]+$/, ""));
    form.append("purpose", purpose);
    return run(purpose, () => api.post(base + "/templates", form), purpose === "example" ? "Example added. The AI will copy its style." : "Template added.");
  }

  async function view(t: Template) {
    setError("");
    try {
      const r = await api.get<{ outline: Outline | null; example?: string }>("/api/templates/" + t.id + "/outline");
      setOpen({ id: t.id, name: t.name, outline: r.outline, example: r.example });
    } catch (e) {
      setError(errText(e));
    }
  }

  const title = org!.name + " Minutes";
  const fromBuiltin = (b: Builtin): Design => withDefaults({ ...b.design, name: b.name, title });

  async function edit(t: Template) {
    setError("");
    try {
      const r = await api.get<{ design: Design }>("/api/templates/" + t.id + "/design");
      setEditing({ id: t.id, heading: "Edit " + t.name, design: r.design });
    } catch (e) {
      setError(errText(e));
    }
  }

  async function saveDesign(d: Design) {
    const e = editing!;
    if (e.id) await api.put("/api/templates/" + e.id + "/design", d);
    else await api.post(base + "/templates/design", { ...d, source: e.source || "" });
    setEditing(null);
    setMsg(e.id ? "Template saved. New drafts use it." : d.name + " template added.");
    await Promise.all([list.reload(), info.reload()]);
    if (e.id && open?.id === e.id) setOpen(null);
  }

  function download(t: Template) {
    setError("");
    downloadFile("/api/templates/" + t.id + "/file", undefined, t.filename).catch((e) => setError(errText(e)));
  }

  function remove(t: Template) {
    if (!confirm("Delete " + t.name + "?")) return;
    void run("delete", async () => {
      await api.del("/api/templates/" + t.id);
      if (open?.id === t.id) setOpen(null);
    }, "Deleted.");
  }

  const templates = list.data?.templates || [];
  const blanks = templates.filter((t) => t.purpose !== "example");
  const examples = templates.filter((t) => t.purpose === "example");
  const shared = library.data?.templates || [];
  const o = info.data;
  const chooser = (title: string, field: "default_template_id" | "example_template_id", rows: Template[], none: string) => (
    <label>{title}
      <select value={o?.[field] || ""} disabled={!editable} onChange={(e) => void run("pick", () => api.patch(base, { [field]: e.target.value }), "Saved.")}>
        <option value="">{none}</option>
        {rows.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
      </select>
    </label>
  );

  const fileButton = (label: string, purpose: "template" | "example", primary: boolean) => (
    <label className={"btn" + (primary ? " primary" : "")} style={{ display: "inline-flex" }}>
      {busy === purpose ? "Uploading…" : label}
      <input type="file" hidden accept=".docx,.pdf,.txt,.md" disabled={!!busy}
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f, purpose); }} />
    </label>
  );

  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker">File cabinet</div>
          <h1>Templates</h1>
          <p className="sub">A template is the blank structure the AI fills in. An example is a finished set of minutes the AI copies the style of.
            A .docx keeps its styles and numbering; a list of topics becomes a clean new template.</p>
        </div>
        {editable && <div className="row">{fileButton("Upload example", "example", false)}{fileButton("Upload template", "template", true)}</div>}
      </div>
      {msg && <div className="alert ok" role="status" style={{ marginBottom: 12 }}>{msg}</div>}
      <ErrorBox error={error || list.error} />
      {editing && (
        <TemplateDesigner start={editing.design} heading={editing.heading} saveLabel={editing.id ? "Save changes" : "Add this template"}
          onSave={saveDesign} onClose={() => setEditing(null)} fonts={builtin.data?.options.fonts} />
      )}
      {editable && (
        <div className="card" style={{ marginBottom: 18 }}>
          <h2>Start from a built-in template</h2>
          <p className="sub">Each one is a different style. Open one to change any wording, alignment, font, color, or section, then add it.</p>
          <div className="builtin-grid">
            {(builtin.data?.templates || []).slice().sort((a, b) => org!.personal ? Number(SCHOOL_ONLY.includes(a.key)) - Number(SCHOOL_ONLY.includes(b.key)) : 0).map((b) => (
              <div key={b.key} className="builtin-card">
                <button type="button" className="builtin-thumb" aria-label={"Preview and customize " + b.name}
                  onClick={() => setEditing({ source: b.key, heading: "Customize: " + b.name, design: fromBuiltin(b) })}>
                  <Paper d={fromBuiltin(b)} mini />
                </button>
                <strong>{b.name}</strong>
                <span className="sub">{b.description}</span>
                <div className="row">
                  <button disabled={!!busy} onClick={() => setEditing({ source: b.key, heading: "Customize: " + b.name, design: fromBuiltin(b) })}>Customize</button>
                  <button disabled={!!busy} onClick={() => void run("builtin", () => api.post(base + "/templates/builtin/" + b.key), b.name + " template added.")}>Use as is</button>
                </div>
              </div>
            ))}
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button onClick={() => setEditing({ heading: "Build your own template", design: blankDesign("", title) })}>Build your own from scratch</button>
          </div>
        </div>
      )}
      <div className="grid-3">
        <div className="stack">
          <div className="card">
            <h2>Templates to fill in</h2>
            {blanks.length === 0 ? <div className="empty">No templates yet. Upload one, or start from a built-in one.</div> : (
              <table>
                <thead><tr><th>Name</th><th>Type</th><th>Added</th><th /></tr></thead>
                <tbody>
                  {blanks.map((t) => (
                    <tr key={t.id} className={open?.id === t.id ? "on" : ""}>
                      <td><button className="link" onClick={() => void view(t)}>{t.name}</button><div className="sub">{t.filename}</div>
                        {o?.default_template_id === t.id && <span className="chip accent">Default</span>}</td>
                      <td>{t.mode === "generated" ? <span className="badge accent">From topics</span> : <span className="badge">Your format</span>}</td>
                      <td className="sub">{fmtDate(t.created_at)}</td>
                      <td><div className="row" style={{ justifyContent: "flex-end" }}>
                        <button onClick={() => download(t)}>Download</button>
                        {editable && t.editable && <button onClick={() => void edit(t)}>Edit</button>}
                        {editable && <button className="danger" onClick={() => remove(t)}>Delete</button>}
                      </div></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="card">
            <h2>Examples for the AI to follow</h2>
            <p className="sub">Upload minutes your organization already approved and liked. The AI matches their tone, length, and wording, never their facts.</p>
            {examples.length === 0 ? <div className="empty">No examples yet. Without one, the AI uses the Live Minutes standard style: one short, factual bullet per agenda item.</div> : (
              <table>
                <tbody>
                  {examples.map((t) => (
                    <tr key={t.id}>
                      <td><button className="link" onClick={() => void view(t)}>{t.name}</button><div className="sub">{t.filename}</div>
                        {o?.example_template_id === t.id && <span className="chip accent">In use</span>}</td>
                      <td className="sub">{fmtDate(t.created_at)}</td>
                      <td>{editable && <button className="danger" onClick={() => remove(t)}>Delete</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="card stack">
            <h2>Defaults</h2>
            <div className="grid-2">
              {chooser("Template for new meetings", "default_template_id", blanks, "Ask each time")}
              {chooser("Example the AI follows", "example_template_id", examples, examples.length ? "The newest example" : "Live Minutes standard style")}
            </div>
          </div>
        </div>
        <div className="stack">
          <div className="card">
            <h2>{open ? open.name : "What the AI can fill"}</h2>
            {!open ? <p className="sub">Choose a template to see its agenda slots, or an example to see the text the AI learns from.</p> : open.outline === null ? (
              <div className="stack">
                <p className="sub" style={{ margin: 0 }}>This is an example. The AI reads this text for style only:</p>
                <div className="prewrap" style={{ maxHeight: 420, overflowY: "auto" }}>{open.example}</div>
              </div>
            ) : (
              <div className="stack">
                <div><h3>Agenda topics</h3>{open.outline.slots.map((s, i) => <div key={i} className="tline">{s}</div>)}</div>
                {open.outline.roll_call.length > 0 && <div><h3>Roll call</h3>{open.outline.roll_call.map((s, i) => <div key={i} className="tline">{s}</div>)}</div>}
                {open.outline.report_lines.length > 0 && <div><h3>Reports</h3>{open.outline.report_lines.map((s, i) => <div key={i} className="tline">{s}</div>)}</div>}
                {open.outline.slots.some((s) => s.length > 90) && (
                  <div className="alert warn">Some slots are long paragraphs, which usually means this file is a filled-in set of minutes. Upload it as an example instead,
                    and use a blank agenda or a built-in template to fill in.</div>
                )}
              </div>
            )}
          </div>
          {shared.length > 0 && (
            <div className="card">
              <h2>Shared by your college and district</h2>
              {shared.map((t) => (
                <div key={t.id} className="request-row" style={{ marginTop: 8 }}>
                  <div className="row spread">
                    <strong>{t.name}</strong>
                    {editable && <button disabled={!!busy} onClick={() => void run("lib", () => api.post(base + "/library/" + t.id + "/use"), t.name + " added.")}>Use</button>}
                  </div>
                  <div className="sub">{t.owner}{t.description ? " · " + t.description : ""}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
