import { useEffect, useState } from "react";
import MoneyInput from "./MoneyInput";
import AiApps from "./AiApps";
import { api, type AIConn, type Provider } from "../api";
import { ErrorBox, errText, useLoad } from "../ui";

export type AiScope = "platform" | "district" | "school" | "org" | "user";

interface Share { id: string; target_scope: string; target_id: string; target: string }
export interface ShareTarget { scope: string; id: string; name: string }
interface TaskRow { task: string; label: string; connection_id: string | null; prompt: string; inherited: { prompt: string; from: string; ai: { label: string; from: string } | null }; default_prompt: string }
interface Usage {
  tokens: number; cents: number; calls: number; unpriced_calls: number;
  by_task: { task: string; tokens: number; cents: number; calls: number }[];
  by_model: { provider: string; model: string; tokens: number; cents: number; calls: number }[];
  orgs: { id: string; name: string; school: string; tokens: number; cents: number; limit_tokens: number | null; limit_cents: number | null }[];
  can_set_limits: boolean;
}

const OWNER: Record<string, string> = { district: "District", school: "College", org: "Organization", user: "Personal", platform: "Built in" };
const FROM: Record<string, string> = { default: "Live Minutes default", platform: "platform", district: "district", school: "college", org: "organization" };
export const money = (cents: number) => cents > 0 && cents < 1 ? "under $0.01"
  : (cents / 100).toLocaleString(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });

type Method = [string, string, string];
const CLAUDE: Method = ["claude", "My Claude or ChatGPT plan", "Connect Claude or ChatGPT to Live Minutes. No key, uses your own plan."];
const OPENROUTER: Method = ["openrouter", "Sign in with OpenRouter", "One click. Reaches Claude, GPT, Gemini, and more, billed to OpenRouter."];
const MODEL_HINT: Record<string, string> = { anthropic: "claude-sonnet-5", openrouter: "a model ID from openrouter.ai/models; end it with :free for a free model", huggingface: "a model ID from huggingface.co/models, such as owner/model-name" };
const KEY: Method = ["key", "API key or local AI", "Paste a key from Claude, OpenAI, Gemini, and others, or use LM Studio or Ollama."];
const GET_KEY: Record<string, [string, string, string?]> = {
  anthropic: ["https://platform.claude.com/settings/keys", "Get a Claude API key"],
  openrouter: ["https://openrouter.ai/settings/keys", "Get an OpenRouter key"],
  openai: ["https://platform.openai.com/api-keys", "Get an OpenAI API key"],
  groq: ["https://console.groq.com/keys", "Get a Groq API key"],
  xai: ["https://console.x.ai/team/default/api-keys", "Get an xAI API key"],
  gemini: ["https://aistudio.google.com/apikey", "Get a Gemini API key"],
  huggingface: ["https://huggingface.co/settings/tokens", "Get a Hugging Face token",
    "Opens in a new tab. Create a fine-grained token with \"Make calls to Inference Providers\" turned on, then paste it below."],
  lmstudio: ["https://lmstudio.ai/download", "Download LM Studio"],
  ollama: ["https://ollama.com/download", "Download Ollama"],
};

export function AddAiForm({ scope, scopeId, onAdded }: { scope: AiScope; scopeId: string; onAdded: () => void }) {
  const cat = useLoad(() => api.get<{ providers: Provider[] }>("/api/providers"), []);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [url, setUrl] = useState("");
  const [label, setLabel] = useState("");
  const [error, setError] = useState("");
  const [method, setMethod] = useState("");
  const providers = cat.data?.providers || [];
  const chosen = providers.find((p) => p.id === provider);
  const groups: [string, (p: Provider) => boolean][] = [
    ["API key", (p) => p.needs_key], ["Local", (p) => p.local], ["Other", (p) => !p.needs_key && !p.local]];

  async function add() {
    setError("");
    try {
      await api.post("/api/ai/connections", { scope, scope_id: scopeId, provider, model, api_key: key, base_url: url, label });
      setProvider(""); setModel(""); setKey(""); setUrl(""); setLabel("");
      onAdded();
    } catch (e) {
      setError(errText(e));
    }
  }

  const methods: Method[] = [
    ...(scope === "user" ? [CLAUDE] : []), ...(scope !== "platform" ? [OPENROUTER] : []), KEY];
  const pick = methods.length === 1 ? "key" : method;

  return (
    <div className="card stack">
      <h2>{scope === "user" ? "Connect your own AI" : "Add an AI"}</h2>
      {methods.length > 1 && (
        <div className="type-grid method-grid">
          {methods.map(([id, name, hint]) => (
            <button key={id} type="button" aria-pressed={pick === id} className={"type-card" + (pick === id ? " on" : "")}
              onClick={() => setMethod(pick === id ? "" : id)}>
              <strong>{name}</strong>
              <span>{hint}</span>
            </button>
          ))}
        </div>
      )}
      {pick === "claude" && <AiApps />}
      {pick === "openrouter" && (
        <div className="stack" style={{ gap: 8 }}>
          <p className="sub" style={{ margin: 0 }}>Sign in to OpenRouter and approve Live Minutes. OpenRouter makes a key for you, and Live Minutes stores it encrypted.</p>
          <div className="row">
            <a className="btn primary" href={"/api/ai/openrouter/start?scope=" + scope + "&scope_id=" + encodeURIComponent(scopeId)}>Connect with OpenRouter</a>
          </div>
        </div>
      )}
      {pick === "key" && <p className="sub" style={{ margin: 0 }}>Each AI is billed to its own key. Keys are encrypted and never shown again after saving.</p>}
      {pick === "key" && groups.map(([name, match]) => {
        const list = providers.filter(match);
        if (!list.length) return null;
        return (
          <div key={name}>
            <h3>{name}</h3>
            <div className="choice">
              {list.map((p) => (
                <button key={p.id} type="button" className={provider === p.id ? "on" : ""} aria-pressed={provider === p.id} onClick={() => { setProvider(p.id); setUrl(""); }}>{p.label}</button>
              ))}
            </div>
          </div>
        );
      })}
      {pick === "key" && chosen && (
        <div className="stack">
          {GET_KEY[chosen.id] && (
            <div className="row">
              <a className="btn" href={GET_KEY[chosen.id][0]} target="_blank" rel="noopener noreferrer">{GET_KEY[chosen.id][1]}</a>
              <span className="sub">{GET_KEY[chosen.id][2] || (chosen.local ? "Opens in a new tab. Install it, start its server, then fill in the model below." : "Opens in a new tab. Create a key there, then paste it below.")}</span>
            </div>
          )}
          <label>Name<input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={chosen.label} autoComplete="off" /></label>
          <label>Model<input value={model} onChange={(e) => setModel(e.target.value)} placeholder={MODEL_HINT[chosen.id] || "model name from your provider"}
            autoComplete="off" spellCheck={false} data-1p-ignore data-lpignore="true" data-bwignore /></label>
          {(chosen.needs_key || chosen.id === "custom") && (
            <label>{chosen.needs_key ? "API key" : "API key (if the server needs one)"}<input type="password" name="ai-api-key" value={key} onChange={(e) => setKey(e.target.value)}
              autoComplete="new-password" spellCheck={false} data-1p-ignore data-lpignore="true" data-bwignore className="mono" /></label>
          )}
          {(chosen.needs_base_url || chosen.local) && (
            <label>Server URL<input value={url} onChange={(e) => setUrl(e.target.value)} placeholder={chosen.default_base_url || "https://…/v1"} /></label>
          )}
          <ErrorBox error={error} />
          <div className="row"><button className="primary" disabled={!model} onClick={() => void add()}>Save</button></div>
        </div>
      )}
    </div>
  );
}

function EditConn({ conn, onDone }: { conn: AIConn; onDone: (saved: boolean) => void }) {
  const usesUrl = ["custom", "lmstudio", "ollama"].includes(conn.provider);
  const [label, setLabel] = useState(conn.label);
  const [model, setModel] = useState(conn.model);
  const [key, setKey] = useState("");
  const [url, setUrl] = useState(conn.base_url);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    setBusy(true);
    setError("");
    try {
      const body: Record<string, string> = { label, model };
      if (key.trim()) body.api_key = key;
      if (usesUrl) body.base_url = url;
      await api.patch("/api/ai/connections/" + conn.id, body);
      onDone(true);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      {GET_KEY[conn.provider] && !usesUrl && (
        <div className="row">
          <a className="btn" href={GET_KEY[conn.provider][0]} target="_blank" rel="noopener noreferrer">{GET_KEY[conn.provider][1]}</a>
        </div>
      )}
      <label>Name<input value={label} onChange={(e) => setLabel(e.target.value)} autoComplete="off" /></label>
      <label>Model<input value={model} onChange={(e) => setModel(e.target.value)} autoComplete="off" spellCheck={false}
        data-1p-ignore data-lpignore="true" data-bwignore /></label>
      <label>{conn.has_key ? "New API key" : usesUrl ? "API key (if the server needs one)" : "API key"}
        <input type="password" name="ai-api-key" value={key} onChange={(e) => setKey(e.target.value)}
          placeholder={conn.has_key ? "Leave blank to keep the key ending " + conn.api_key.replace(/[^A-Za-z0-9]/g, "").slice(-4) : ""}
          autoComplete="new-password" spellCheck={false} data-1p-ignore data-lpignore="true" data-bwignore className="mono" /></label>
      {usesUrl && (
        <label>Server URL<input value={url} onChange={(e) => setUrl(e.target.value)} autoComplete="off" spellCheck={false} />
          {conn.has_key && <span className="sub">Changing the address needs the API key again.</span>}</label>
      )}
      <ErrorBox error={error} />
      <div className="row">
        <button className="primary" disabled={busy || !model.trim()} onClick={() => void save()}>{busy ? "Saving…" : "Save changes"}</button>
        <button onClick={() => onDone(false)}>Cancel</button>
      </div>
    </div>
  );
}

export function ConnList({ connections, onChanged, targets = [], title = "AIs", empty = "No AI here yet." }: {
  connections: AIConn[]; onChanged: () => void; targets?: ShareTarget[]; title?: string; empty?: string;
}) {
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [pick, setPick] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState("");

  async function run(fn: () => Promise<unknown>, done = "") {
    setError(""); setMsg("");
    try { await fn(); if (done) setMsg(done); onChanged(); } catch (e) { setError(errText(e)); }
  }

  async function test(id: string) {
    setMsg("Testing…");
    try {
      const r = await api.post<{ ok: boolean; reply?: string; error?: string }>("/api/ai/connections/" + id + "/test");
      setMsg(r.ok ? "It works. The model replied: " + r.reply : "Test failed: " + r.error);
    } catch (e) {
      setMsg("Test failed: " + errText(e));
    }
  }

  return (
    <div className="card stack">
      <h2>{title}</h2>
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error} />
      {connections.length === 0 && <p className="sub">{empty}</p>}
      {connections.map((c) => (
        <div key={c.id} className="stack request-row">
          <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <strong>{c.label}</strong> <span className="chip">{OWNER[c.owner_scope] || c.owner_scope}{c.owner ? ": " + c.owner : ""}</span>
              <div className="sub mono">{c.free ? "Runs on the Live Minutes server · free, no key · slower, with a progress bar" : c.provider + " · " + c.model + (c.has_key ? " · key " + c.api_key : "")}</div>
            </div>
            {c.can_manage && (
              <span className="row">
                <button onClick={() => void test(c.id)}>Test</button>
                <button aria-expanded={editing === c.id} onClick={() => { setEditing(editing === c.id ? "" : c.id); setMsg(""); setError(""); }}>Edit</button>
                <button className="danger" onClick={() => { if (confirm("Remove " + c.label + "? Anything using it will need another AI.")) void run(() => api.del("/api/ai/connections/" + c.id), "Removed."); }}>Remove</button>
              </span>
            )}
          </div>
          {c.can_manage && editing === c.id && (
            <EditConn key={c.id + c.model + c.label + c.base_url} conn={c} onDone={(saved) => {
              setEditing("");
              if (saved) { setMsg("Saved. Choose Test to check it."); onChanged(); }
            }} />
          )}
          {c.can_manage && c.shares && (
            <div className="stack" style={{ gap: 6 }}>
              <span className="sub">Shared with: {c.shares.length ? "" : "nobody yet"}</span>
              <div className="chips">
                {c.shares.map((s: Share) => (
                  <span key={s.id} className="chip">{s.target} <button className="link" onClick={() => void run(() => api.del("/api/ai/shares/" + s.id))}>×</button></span>
                ))}
              </div>
              <div className="row">
                <select value={pick[c.id] || ""} onChange={(e) => setPick({ ...pick, [c.id]: e.target.value })}>
                  <option value="">Share with…</option>
                  {(c.owner_scope === "district" ? [{ scope: "district_all", id: "", name: "Every college in the district" }] : [{ scope: "school_all", id: "", name: "Everyone at the college" }])
                    .concat(targets).map((t) => <option key={t.scope + t.id} value={t.scope + ":" + t.id}>{t.name}</option>)}
                </select>
                <button disabled={!pick[c.id]} onClick={() => {
                  const [target_scope, target_id] = pick[c.id].split(":");
                  void run(() => api.post("/api/ai/connections/" + c.id + "/shares", { target_scope, target_id }), "Shared.");
                }}>Share</button>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export function TaskPanel({ scope, scopeId = "", title }: { scope: AiScope; scopeId?: string; title?: string }) {
  const data = useLoad(() => api.get<{ tasks: TaskRow[]; choices: AIConn[]; can_edit_prompts: boolean; context: string }>(
    "/api/ai/tasks?scope=" + scope + "&scope_id=" + scopeId), [scope, scopeId]);
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (data.data) setPrompts(Object.fromEntries(data.data.tasks.map((t) => [t.task, t.prompt])));
  }, [data.data]);

  async function save(task: string, body: Record<string, unknown>, done: string) {
    setMsg(""); setError("");
    try {
      await api.put("/api/ai/tasks", { scope, scope_id: scopeId, task, ...body });
      setMsg(done);
      await data.reload();
    } catch (e) {
      setError(errText(e));
    }
  }

  const d = data.data;
  if (!d) return <ErrorBox error={data.error} />;
  const fallback = (t: TaskRow) => scope === "user" ? "Use what my organization chose"
    : t.inherited.ai ? "Use the default: " + t.inherited.ai.label + " (set by the " + FROM[t.inherited.ai.from] + ")"
    : "Use the Live Minutes default (the first AI this " + (scope === "org" ? "organization" : scope === "school" ? "college" : "district") + " can use)";
  return (
    <div className="card stack">
      <h2>{title || "Which AI does each task"}</h2>
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error} />
      {d.tasks.map((t) => (
        <div key={t.task} className="stack request-row">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <strong>{t.label}</strong>
            {scope !== "platform" && (
              <select value={t.connection_id || ""} onChange={(e) => void save(t.task, e.target.value ? { connection_id: e.target.value } : { clear_connection: true }, "Saved.")}>
                <option value="">{fallback(t)}</option>
                {d.choices.map((c) => <option key={c.id} value={c.id}>{c.label} ({OWNER[c.owner_scope] || c.owner_scope}{c.owner ? ": " + c.owner : ""})</option>)}
              </select>
            )}
          </div>
          {d.can_edit_prompts && (
            <details>
              <summary className="sub">Prompt {t.prompt ? "(customized here)" : "(using the " + FROM[t.inherited.from] + " prompt)"}</summary>
              <textarea rows={4} value={prompts[t.task] ?? ""} placeholder={t.inherited.prompt}
                onChange={(e) => setPrompts({ ...prompts, [t.task]: e.target.value })} />
              <div className="row">
                <button onClick={() => void save(t.task, { prompt: prompts[t.task] || "" }, "Prompt saved.")}>Save prompt</button>
                {t.prompt && <button onClick={() => void save(t.task, { clear_prompt: true }, "Using the " + FROM[t.inherited.from] + " prompt again.")}>Reset</button>}
              </div>
            </details>
          )}
        </div>
      ))}
      {d.can_edit_prompts && (
        <details>
          <summary className="sub">What every AI is told about Live Minutes</summary>
          <pre className="prewrap">{d.context}</pre>
        </details>
      )}
    </div>
  );
}

export function UsagePanel({ scope, scopeId = "" }: { scope: AiScope; scopeId?: string }) {
  const data = useLoad(() => api.get<Usage>("/api/ai/usage?scope=" + scope + "&scope_id=" + scopeId), [scope, scopeId]);
  const [edit, setEdit] = useState<Record<string, { tokens: string; dollars: string }>>({});
  const [error, setError] = useState("");
  const d = data.data;
  if (!d) return <ErrorBox error={data.error} />;

  async function saveLimit(id: string) {
    setError("");
    const e = edit[id];
    try {
      await api.put("/api/ai/limits/" + id, { tokens: e.tokens ? Number(e.tokens) : null, cents: e.dollars ? Math.round(Number(e.dollars) * 100) : null });
      await data.reload();
    } catch (x) {
      setError(errText(x));
    }
  }

  return (
    <div className="card stack">
      <h2>AI use this month</h2>
      <div className="stat-grid">
        <div className="stat"><span className="stat-label">Tokens</span><span className="stat-num">{d.tokens.toLocaleString()}</span><span className="stat-sub">{d.calls} calls</span></div>
        <div className="stat"><span className="stat-label">Estimated cost</span><span className="stat-num">{money(d.cents)}</span>
          {d.unpriced_calls > 0 && <span className="stat-sub">{d.unpriced_calls} calls have no price set yet</span>}</div>
      </div>
      {d.by_task.length > 0 && (
        <table><thead><tr><th>Task</th><th>Tokens</th><th>Cost</th></tr></thead><tbody>
          {d.by_task.map((t) => <tr key={t.task}><td>{t.task}</td><td>{t.tokens.toLocaleString()}</td><td>{money(t.cents)}</td></tr>)}
        </tbody></table>
      )}
      {d.orgs.length > 0 && (
        <>
          <h3>By organization</h3>
          <ErrorBox error={error} />
          <table>
            <thead><tr><th>Organization</th><th>Used</th><th>Monthly limit</th><th /></tr></thead>
            <tbody>
              {d.orgs.map((o) => {
                const e = edit[o.id] || { tokens: o.limit_tokens ? String(o.limit_tokens) : "", dollars: o.limit_cents ? String(o.limit_cents / 100) : "" };
                return (
                  <tr key={o.id}>
                    <td>{o.name}<div className="sub">{o.school}</div></td>
                    <td>{o.tokens.toLocaleString()} tokens<div className="sub">{money(o.cents)}</div></td>
                    <td>{d.can_set_limits ? (
                      <span className="row">
                        <input style={{ width: 120 }} type="number" min={0} aria-label="Monthly token limit" placeholder="tokens" value={e.tokens} onChange={(x) => setEdit({ ...edit, [o.id]: { ...e, tokens: x.target.value } })} />
                        <MoneyInput style={{ width: 120 }} label="Monthly cost limit in dollars" placeholder="50.00" value={e.dollars} onChange={(v) => setEdit({ ...edit, [o.id]: { ...e, dollars: v } })} />
                      </span>
                    ) : (o.limit_tokens ? o.limit_tokens.toLocaleString() + " tokens" : o.limit_cents ? money(o.limit_cents) : "none")}</td>
                    <td>{d.can_set_limits && <button onClick={() => void saveLimit(o.id)}>Save</button>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
