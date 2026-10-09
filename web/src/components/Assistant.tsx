import { useEffect, useRef, useState } from "react";
import { useExamples } from "../examples";
import { Link } from "react-router-dom";
import { api, can } from "../api";
import { useSession } from "../session";
import { errText } from "../ui";
import Icon from "./Icon";

export interface Usage {
  tokens: number; cents: number; limit_tokens: number | null; limit_cents: number | null; since: number; resets_at: number;
  mine_tokens: number; mine_cents: number; blocked: string;
}
interface Action { id: string; kind: string; title: string; lines: string[]; status: string; result: string; link: string; expires_at?: number }
interface Status { org: string; ai: { label: string; model: string } | null; usage: Usage; pending: Action[] }
interface Reply { reply: string; actions: Action[]; notes: string[]; pages: { path: string; label: string }[]; usage: Usage }
interface Turn { role: "user" | "assistant"; content: string; actions?: Action[]; notes?: string[]; pages?: Reply["pages"] }

const STATUS: Record<string, [string, string]> = {
  pending: ["Waiting for you", "warn"], running: ["Working", "accent"], done: ["Done", "ok"], failed: ["Did not work", "bad"],
  cancelled: ["Cancelled", ""], expired: ["Expired", ""], blocked: ["Not allowed", "bad"]
};

const tokens = (n: number) => n >= 1_000_000 ? (n / 1_000_000).toFixed(1) + "M" : n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n);
const dollars = (c: number) => "$" + (c / 100).toFixed(2);
const day = (ts: number) => new Date(ts * 1000).toLocaleDateString(undefined, { month: "long", day: "numeric", timeZone: "UTC" });

export function UsageMeter({ usage }: { usage: Usage }) {
  const parts: { label: string; used: number; cap: number }[] = [];
  if (usage.limit_tokens) parts.push({ label: tokens(usage.tokens) + " of " + tokens(usage.limit_tokens) + " tokens", used: usage.tokens, cap: usage.limit_tokens });
  if (usage.limit_cents) parts.push({ label: dollars(usage.cents) + " of " + dollars(usage.limit_cents), used: usage.cents, cap: usage.limit_cents });
  return (
    <div className="as-usage">
      {parts.length === 0 && <div className="sub">This month: {tokens(usage.tokens)} tokens{usage.cents ? ", about " + dollars(usage.cents) : ""}. No monthly limit is set.</div>}
      {parts.map((p) => {
        const pct = Math.min(100, Math.round((p.used / p.cap) * 100));
        return (
          <div key={p.label}>
            <div className="as-usage-row"><span>This month: {p.label}</span><span>{pct}%</span></div>
            <div className={"as-bar" + (pct >= 90 ? " hot" : "")} role="progressbar" aria-label={"AI use: " + p.label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}><i style={{ width: pct + "%" }} /></div>
          </div>
        );
      })}
      <div className="sub">You used {tokens(usage.mine_tokens)} tokens{usage.mine_cents ? " (" + dollars(usage.mine_cents) + ")" : ""}. Resets {day(usage.resets_at)}.</div>
      {usage.blocked && <div className="alert bad" role="alert">{usage.blocked}</div>}
    </div>
  );
}

function ActionCard({ a, onChange }: { a: Action; onChange: (a: Action) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [label, cls] = STATUS[a.status] || [a.status, ""];
  async function act(what: "approve" | "cancel") {
    setBusy(true); setError("");
    try { onChange(await api.post<Action>("/api/assistant/actions/" + a.id + "/" + what)); } catch (e) { setError(errText(e)); } finally { setBusy(false); }
  }
  return (
    <div className={"as-action " + a.status}>
      <div className="as-action-head"><strong>{a.title}</strong><span className={"badge " + cls}>{label}</span></div>
      {a.lines.length > 0 && <ul>{a.lines.map((l) => <li key={l}>{l}</li>)}</ul>}
      {a.result && <p className="sub" style={{ margin: 0 }}>{a.result}</p>}
      {error && <div className="alert bad" role="alert">{error}</div>}
      {a.status === "pending" && (
        <div className="row">
          <button className="primary" disabled={busy} onClick={() => void act("approve")}>Approve</button>
          <button disabled={busy} onClick={() => void act("cancel")}>Cancel</button>
        </div>
      )}
      {a.status === "done" && a.link && <Link to={a.link}>Open it</Link>}
    </div>
  );
}

export default function Assistant() {
  const { org } = useSession();
  const ex = useExamples();
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const trigger = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const orgId = org?.id || "";

  useEffect(() => { setTurns([]); setStatus(null); }, [orgId]);
  useEffect(() => {
    if (new URLSearchParams(location.search).get("assistant") === "open") setOpen(true);
  }, []);
  useEffect(() => {
    if (!orgId || !org || !can(org.role, "member")) return;
    const load = () => api.get<Status>("/api/assistant/status?org_id=" + orgId).then((s) => {
      setStatus(s);
      setTurns((t) => {
        const shown = new Set(t.flatMap((x) => (x.actions || []).map((a) => a.id)));
        const fresh = s.pending.filter((a) => !shown.has(a.id));
        return fresh.length ? [...t, { role: "assistant", content: "These suggestions are waiting for you to approve.", actions: fresh }] : t;
      });
    }).catch((e) => setError(errText(e)));
    void load();
    const t = window.setInterval(() => void load(), open ? 15000 : 60000);
    return () => window.clearInterval(t);
  }, [open, orgId]);
  useEffect(() => { if (open) input.current?.focus(); }, [open]);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [turns, busy]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (!org || !can(org.role, "member")) return null;
  const waiting = turns.flatMap((t) => t.actions || []).filter((a) => a.status === "pending").length;

  function update(a: Action) {
    setTurns((all) => all.map((t) => t.actions ? { ...t, actions: t.actions.map((x) => x.id === a.id ? a : x) } : t));
  }

  async function send() {
    const msg = text.trim();
    if (!msg || busy) return;
    const next: Turn[] = [...turns, { role: "user", content: msg }];
    setTurns(next); setText(""); setBusy(true); setError("");
    try {
      const r = await api.post<Reply>("/api/assistant/chat", {
        org_id: orgId, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        messages: next.slice(-16).map((t) => ({ role: t.role, content: t.content }))
      });
      setTurns([...next, { role: "assistant", content: r.reply, actions: r.actions, notes: r.notes, pages: r.pages }]);
      setStatus((s) => s ? { ...s, usage: r.usage } : s);
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
      input.current?.focus();
    }
  }

  return (
    <>
      <button ref={trigger} type="button" className="as-float primary" aria-expanded={open} aria-controls="assistant" onClick={() => setOpen(!open)}>
        <Icon name={open ? "close" : "chat"} />{open ? "Close" : "Assistant"}
        {!open && waiting > 0 && <span className="as-badge" aria-label={waiting + " waiting for approval"}>{waiting}</span>}
      </button>
      {open && (
        <section className="as-panel" id="assistant" role="dialog" aria-label="Live Minutes assistant">
          <div className="as-head">
            <div>
              <div className="as-title">Assistant</div>
              <div className="sub">{org.name}{status?.ai ? " · " + status.ai.label : ""}</div>
            </div>
            <button className="link" onClick={() => { setOpen(false); trigger.current?.focus(); }}>Close</button>
          </div>
          {status && <UsageMeter usage={status.usage} />}
          {status && !status.ai && (
            <div className="alert warn">
              No AI is set up for this chat here. You can still use Claude or ChatGPT: connect Live Minutes under{" "}
              <Link to="/account?tab=ai">My account, AI</Link>, then ask it, for example, "{ex.appAsk}" Its suggestions
              show up here for you to approve. {org?.personal ? "You can also add an AI for this chat under Settings, AI."
              : "A secretary can also add an AI for this chat under Settings, AI."}
            </div>
          )}
          <div className="as-log" aria-live="polite">
            {turns.length === 0 && (
              <div className="sub">
                Ask a question or ask for a change, like {ex.assistantAsk}. You review every change and press Approve before anything happens. The
                assistant can only do what you can do, cannot delete or remove anything, and cannot see other people's
                contact details.
              </div>
            )}
            {turns.map((t, i) => (
              <div key={i} className={"as-msg " + t.role}>
                <div className="as-who">{t.role === "user" ? "You" : "Assistant"}</div>
                <div className="as-text">{t.content}</div>
                {(t.actions || []).map((a, j) => a.id ? <ActionCard key={a.id} a={a} onChange={update} />
                  : <div key={j} className="as-action blocked"><div className="as-action-head"><strong>{a.title}</strong><span className="badge bad">Not allowed</span></div><p className="sub" style={{ margin: 0 }}>{a.result}</p></div>)}
                {(t.notes || []).map((n) => <div key={n} className="alert">{n}</div>)}
                {(t.pages || []).length > 0 && <div className="row">{t.pages!.map((p) => <Link key={p.path} to={p.path}>{p.label}</Link>)}</div>}
              </div>
            ))}
            {busy && <div className="sub">Thinking…</div>}
            <div ref={end} />
          </div>
          {error && <div className="alert bad" role="alert">{error}</div>}
          <form className="as-form" onSubmit={(e) => { e.preventDefault(); void send(); }}>
            <label className="sr-only" htmlFor="assistant-input">Message the assistant</label>
            <textarea id="assistant-input" ref={input} rows={2} maxLength={2000} value={text} placeholder="Ask or request a change"
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }} />
            <button className="primary" type="submit" disabled={busy || !text.trim() || !!status?.usage.blocked || (!!status && !status.ai)}>Send</button>
          </form>
        </section>
      )}
    </>
  );
}
