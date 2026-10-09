import { useEffect, useState } from "react";
import MoneyInput from "../../components/MoneyInput";
import { api, type AIConn } from "../../api";
import { AddAiForm, ConnList, TaskPanel, UsagePanel, type ShareTarget } from "../../components/AiPanels";
import { ErrorBox, errText, useLoad } from "../../ui";

export function ScopeAi({ scope, scopeId, base }: { scope: "district" | "school"; scopeId: string; base: string }) {
  const owned = useLoad(() => api.get<{ connections: AIConn[] }>("/api/ai/owned?scope=" + scope + "&scope_id=" + scopeId), [scope, scopeId]);
  const targets = useLoad(async (): Promise<ShareTarget[]> => {
    if (scope === "district") {
      const r = await api.get<{ schools: { id: string; name: string }[] }>(base + "/schools");
      return r.schools.map((x) => ({ scope: "school", id: x.id, name: "College: " + x.name }));
    }
    const [orgs, people] = await Promise.all([
      api.get<{ orgs: { id: string; name: string }[] }>(base + "/orgs"),
      api.get<{ people: { id: string; email: string; name: string }[] }>(base + "/people")
    ]);
    return orgs.orgs.map((o) => ({ scope: "org", id: o.id, name: "Organization: " + o.name }))
      .concat(people.people.map((p) => ({ scope: "user", id: p.id, name: "Person: " + (p.name || p.email) })));
  }, [scope, scopeId, base]);
  const policy = useLoad(() => api.get<{ allow_personal_ai: boolean }>("/api/ai/policy?scope=" + scope + "&scope_id=" + scopeId), [scope, scopeId]);
  const [error, setError] = useState("");

  async function setPersonal(on: boolean) {
    setError("");
    try {
      await api.put("/api/ai/policy", { scope, scope_id: scopeId, allow_personal_ai: on });
      await policy.reload();
    } catch (e) {
      setError(errText(e));
    }
  }

  return (
    <div className="stack">
      <div className="grid-2">
        <ConnList title={scope === "district" ? "District AIs" : "College AIs"} connections={owned.data?.connections || []}
          onChanged={() => void owned.reload()} targets={targets.data || []}
          empty={scope === "district" ? "No district AI yet. Add one, then share it with colleges." : "No college AI yet. Add one, then share it with organizations or people."} />
        <AddAiForm scope={scope} scopeId={scopeId} onAdded={() => void owned.reload()} />
      </div>
      <div className="card stack">
        <h2>Personal AI keys</h2>
        <label className="setting-row toggle">
          <span>Let students and staff use their own AI keys in organizations {scope === "district" ? "in this district" : "at this college"}</span>
          <input type="checkbox" checked={policy.data?.allow_personal_ai ?? true} onChange={(e) => void setPersonal(e.target.checked)} />
        </label>
        <p className="sub" style={{ margin: 0 }}>Turn this off when policy requires meeting text to go only to AIs the {scope === "district" ? "district" : "college"} approved.</p>
        <ErrorBox error={error || policy.error} />
      </div>
      <TaskPanel scope={scope} scopeId={scopeId} title={scope === "district" ? "District defaults for each task" : "College defaults for each task"} />
      <UsagePanel scope={scope} scopeId={scopeId} />
    </div>
  );
}

interface Price { id: string; provider: string; model: string; input_per_mtok_cents: number; output_per_mtok_cents: number }

export function PlatformAi() {
  const data = useLoad(() => api.get<{ prices: Price[]; models_in_use: { provider: string; model: string }[] }>("/api/admin/ai-prices"), []);
  const [rows, setRows] = useState<{ provider: string; model: string; input: string; output: string }[]>([]);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!data.data) return;
    const known = data.data.prices.map((p) => ({ provider: p.provider, model: p.model, input: String(p.input_per_mtok_cents / 100), output: String(p.output_per_mtok_cents / 100) }));
    const missing = data.data.models_in_use.filter((m) => !known.some((k) => k.provider === m.provider && k.model === m.model))
      .map((m) => ({ provider: m.provider, model: m.model, input: "", output: "" }));
    setRows([...known, ...missing]);
  }, [data.data]);

  async function save(i: number) {
    setMsg(""); setError("");
    const r = rows[i];
    try {
      await api.put("/api/admin/ai-prices", { provider: r.provider, model: r.model, input_per_mtok_cents: Number(r.input || 0) * 100, output_per_mtok_cents: Number(r.output || 0) * 100 });
      setMsg("Price saved for " + r.model + ".");
      await data.reload();
    } catch (e) {
      setError(errText(e));
    }
  }

  const set = (i: number, k: "provider" | "model" | "input" | "output", v: string) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  return (
    <div className="stack">
      <TaskPanel scope="platform" title="Platform default prompts" />
      <div className="card stack">
        <h2>Model prices</h2>
        <p className="sub" style={{ margin: 0 }}>Enter each model's price in dollars per million tokens from your provider's price page. Costs are estimated from these; models without a price are tracked by tokens only. Use * as the model to cover a whole provider.</p>
        {msg && <div className="alert ok" role="status">{msg}</div>}
        <ErrorBox error={error || data.error} />
        <table>
          <thead><tr><th>Provider</th><th>Model</th><th>Input $ / 1M</th><th>Output $ / 1M</th><th /></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td><input value={r.provider} onChange={(e) => set(i, "provider", e.target.value)} /></td>
                <td><input value={r.model} onChange={(e) => set(i, "model", e.target.value)} /></td>
                <td><MoneyInput value={r.input} onChange={(v) => set(i, "input", v)} label="Input price per million tokens" placeholder="3.00" /></td>
                <td><MoneyInput value={r.output} onChange={(v) => set(i, "output", v)} label="Output price per million tokens" placeholder="15.00" /></td>
                <td><button disabled={!r.provider || !r.model} onClick={() => void save(i)}>Save</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row"><button onClick={() => setRows([...rows, { provider: "anthropic", model: "", input: "", output: "" }])}>Add a price</button></div>
      </div>
      <UsagePanel scope="platform" />
    </div>
  );
}
