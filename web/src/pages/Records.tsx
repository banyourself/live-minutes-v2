import { useState, type FormEvent } from "react";
import { useExamples } from "../examples";
import MoneyInput from "../components/MoneyInput";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useSession } from "../session";
import { ErrorBox, errText, fmtClock, fmtDate, useLoad } from "../ui";

interface Hit {
  meeting_id: string; title: string; meeting_date: string; status: string; kind: string; label: string;
  snippet: string; seq: number | null; t: number | null; n?: number;
}

function source(h: Hit) {
  return "/meetings/" + h.meeting_id + (h.kind === "transcript" && h.seq !== null ? "?line=" + h.seq : "");
}

const KIND: Record<string, string> = { minutes: "Minutes", motion: "Motion", transcript: "Transcript" };

function HitRow({ h }: { h: Hit }) {
  return (
    <div className="request-row">
      <div className="row spread">
        <Link to={source(h)}><strong>{h.n ? "[" + h.n + "] " : ""}{h.title}</strong></Link>
        <span className="row">
          <span className="chip">{KIND[h.kind] || h.kind}</span>
          {h.status !== "approved" && <span className="chip warn">Not approved</span>}
        </span>
      </div>
      <div className="sub">{h.meeting_date}{h.label && h.kind !== "motion" ? " · " + h.label : ""}{h.t !== null && h.kind === "transcript" ? " · " + fmtClock(h.t) : ""}</div>
      <div style={{ marginTop: 4 }}>{h.snippet}</div>
    </div>
  );
}

function Cited({ text }: { text: string }) {
  const parts = text.split(/(\[\d+\])/g);
  return <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{parts.map((p, i) => /^\[\d+\]$/.test(p)
    ? <a key={i} href={"#src-" + p.slice(1, -1)}>{p}</a> : <span key={i}>{p}</span>)}</p>;
}

export function SearchPage() {
  const { org } = useSession();
  const ex = useExamples();
  const base = "/api/orgs/" + org!.id;
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<{ answer: string; sources: Hit[]; note?: string; ai?: string } | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function find(e: FormEvent) {
    e.preventDefault();
    setError(""); setBusy("search");
    try { setHits((await api.get<{ results: Hit[] }>(base + "/search?q=" + encodeURIComponent(q))).results); }
    catch (err) { setError(errText(err)); }
    finally { setBusy(""); }
  }

  async function ask(e: FormEvent) {
    e.preventDefault();
    setError(""); setBusy("ask"); setAnswer(null);
    try { setAnswer(await api.post(base + "/ask", { question })); }
    catch (err) { setError(errText(err)); }
    finally { setBusy(""); }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker">Records</div>
          <h1>Search</h1>
          <p className="sub">Search every meeting's minutes, motions, and transcript, or ask a question and get an answer with links to where it came from.</p>
        </div>
      </div>
      <ErrorBox error={error} />
      <div className="grid-2" style={{ alignItems: "start" }}>
        <form className="card stack" onSubmit={find}>
          <h2>Search</h2>
          <div className="row">
            <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search minutes, motions, and transcripts" placeholder={ex.search} style={{ flex: 1 }} />
            <button className="primary" disabled={busy !== "" || q.trim().length < 2}>{busy === "search" ? "Searching…" : "Search"}</button>
          </div>
          {hits !== null && (hits.length === 0 ? <div className="empty">No matches.</div> : (
            <div className="stack">{hits.map((h, i) => <HitRow key={i} h={h} />)}</div>
          ))}
        </form>
        <form className="card stack" onSubmit={ask}>
          <h2>Ask about past meetings</h2>
          <div className="row">
            <input value={question} onChange={(e) => setQuestion(e.target.value)} aria-label="Question about past meetings" placeholder={ex.question} style={{ flex: 1 }} />
            <button className="primary" disabled={busy !== "" || question.trim().length < 5}>{busy === "ask" ? "Thinking…" : "Ask"}</button>
          </div>
          <p className="sub" style={{ margin: 0 }}>The AI only sees the excerpts listed under its answer. Check the sources before relying on it.</p>
          {answer && (
            <div className="stack">
              {answer.note ? <div className="alert">{answer.note}</div> : <div className="alert ok" role="status"><Cited text={answer.answer} /></div>}
              {answer.ai && <div className="sub">Answered by {answer.ai}</div>}
              {answer.sources.map((h) => <div key={h.n} id={"src-" + h.n}><HitRow h={h} /></div>)}
            </div>
          )}
        </form>
      </div>
    </>
  );
}

interface Person { name: string; yes: number; no: number; abstain: number; absent: number; present: number; moved: number; seconded: number }
interface HistoryRow { meeting_id: string; title: string; meeting_date: string; status: string; motion: string; result: string; vote: string; moved: boolean; seconded: boolean }

export function VotesPage() {
  const { org } = useSession();
  const base = "/api/orgs/" + org!.id;
  const all = useLoad(() => api.get<{ people: Person[]; motions: number }>(base + "/votes"), [base]);
  const [who, setWho] = useState("");
  const hist = useLoad(() => who ? api.get<{ history: HistoryRow[] }>(base + "/votes?person=" + encodeURIComponent(who)) : Promise.resolve({ history: [] }), [base, who]);
  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker">Records</div>
          <h1>Voting record</h1>
          <p className="sub">Built from the saved motions and votes of each meeting. Correct a meeting's votes under its Motions and votes tab.</p>
        </div>
        <a className="btn" href={base + "/votes.csv"}>Download all (CSV)</a>
      </div>
      <ErrorBox error={all.error || hist.error} />
      <div className="grid-3">
        <div className="card">
          <h2>People</h2>
          {(all.data?.people || []).length === 0 ? <div className="empty">No saved votes yet.</div> : (
            <table>
              <thead><tr><th>Name</th><th>Yes</th><th>No</th><th>Abstain</th><th>Absent</th><th>Moved</th><th>Seconded</th></tr></thead>
              <tbody>
                {all.data!.people.map((p) => (
                  <tr key={p.name} className={who === p.name ? "on" : ""} aria-pressed={who === p.name}>
                    <td><button className="link" onClick={() => setWho(p.name)}>{p.name}</button></td>
                    <td>{p.yes}</td><td>{p.no}</td><td>{p.abstain}</td><td>{p.absent}</td><td>{p.moved}</td><td>{p.seconded}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="sub">{all.data?.motions || 0} saved motions.</p>
        </div>
        <div className="card">
          <div className="row spread">
            <h2 style={{ margin: 0 }}>{who || "Choose a person"}</h2>
            {who && <a className="btn sm" href={base + "/votes.csv?person=" + encodeURIComponent(who)}>CSV</a>}
          </div>
          {who && (hist.data?.history || []).map((h, i) => (
            <div key={i} className="request-row" style={{ marginTop: 10 }}>
              <div className="row spread">
                <Link to={"/meetings/" + h.meeting_id}>{h.title}</Link>
                {h.vote && <span className={"chip " + (h.vote === "yes" ? "ok" : h.vote === "no" ? "bad" : "")}>{h.vote}</span>}
              </div>
              <div className="sub">{h.meeting_date}{h.moved ? " · moved" : ""}{h.seconded ? " · seconded" : ""}{h.result ? " · " + h.result : ""}</div>
              <div>{h.motion}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

interface FundingRow {
  id: string; title: string; requester: string; amount_cents: number; approved_cents: number | null; purpose: string;
  status: string; notes: string; created_at: number; decided_at: number | null; motion_id: string | null;
  motion: { text: string; result: string; meeting_id: string; meeting: string; meeting_date: string } | null;
}
interface MotionOpt { id: string; text: string; result: string; title: string; meeting_date: string }

const money = (c: number | null) => c === null ? "" : "$" + (c / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const STATES: [string, string][] = [["submitted", "Submitted"], ["in_review", "In review"], ["approved", "Approved"], ["denied", "Denied"], ["paid", "Paid"], ["withdrawn", "Withdrawn"]];

export function FundingPage() {
  const { org, me } = useSession();
  const base = "/api/orgs/" + org!.id + "/funding";
  const data = useLoad(() => api.get<{ requests: FundingRow[]; totals: Record<string, number>; can_manage: boolean; motions: MotionOpt[] }>(base), [base]);
  const [form, setForm] = useState({ title: "", requester: "", amount: "", purpose: "" });
  const [error, setError] = useState("");

  async function run(fn: () => Promise<unknown>) {
    setError("");
    try { await fn(); await data.reload(); } catch (e) { setError(errText(e)); }
  }

  const d = data.data;
  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker">Records</div>
          <h1>Funding requests</h1>
          <p className="sub">Track each request from submission to payment, linked to the motion that approved it.</p>
        </div>
        <a className="btn" href={base + ".csv"}>Download (CSV)</a>
      </div>
      <ErrorBox error={error || data.error} />
      {d && (
        <div className="stat-grid" style={{ marginBottom: 18 }}>
          {[["Requested", d.totals.requested], ["Waiting", d.totals.pending], ["Approved", d.totals.approved], ["Paid", d.totals.paid]].map(([l, v]) => (
            <div key={l as string} className="stat"><span className="stat-label">{l}</span><span className="stat-num">{money(v as number)}</span></div>
          ))}
        </div>
      )}
      <div className="grid-3">
        <div className="card">
          <h2>Requests</h2>
          {!d || d.requests.length === 0 ? <div className="empty">No funding requests yet.</div> : d.requests.map((f) => (
            <FundingItem key={f.id} f={f} manage={d.can_manage} mine={f.status === "submitted"} motions={d.motions}
              run={run} url={base + "/" + f.id} me={me?.user.id || ""} />
          ))}
        </div>
        <div className="card stack">
          <h2>New request</h2>
          <label>What it is for<input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Trunk or Treat supplies" /></label>
          <label>Requested by<input value={form.requester} onChange={(e) => setForm({ ...form, requester: e.target.value })} placeholder="Associated Student Government" /></label>
          <label>Amount<MoneyInput value={form.amount} onChange={(v) => setForm({ ...form, amount: v })} label="Amount in dollars" /></label>
          <label>Details<textarea rows={3} value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} /></label>
          <div className="row"><button className="primary" disabled={!form.title.trim() || form.amount === ""}
            onClick={() => void run(async () => { await api.post(base, { ...form, amount: Number(form.amount) }); setForm({ title: "", requester: "", amount: "", purpose: "" }); })}>Submit request</button></div>
          {d && !d.can_manage && <p className="sub" style={{ margin: 0 }}>The treasurer, advisor, or an owner decides on requests.</p>}
        </div>
      </div>
    </>
  );
}

function FundingItem({ f, manage, motions, run, url }: {
  f: FundingRow; manage: boolean; mine: boolean; motions: MotionOpt[]; run: (fn: () => Promise<unknown>) => Promise<void>; url: string; me: string;
}) {
  const [open, setOpen] = useState(false);
  const [approved, setApproved] = useState(f.approved_cents !== null ? String(f.approved_cents / 100) : "");
  const [notes, setNotes] = useState(f.notes);
  const [status, setStatus] = useState(f.status);
  const [motion, setMotion] = useState(f.motion_id || "");
  const dirty = status !== f.status || motion !== (f.motion_id || "") || notes !== f.notes ||
    approved !== (f.approved_cents !== null ? String(f.approved_cents / 100) : "");
  function reset() {
    setStatus(f.status); setMotion(f.motion_id || ""); setNotes(f.notes);
    setApproved(f.approved_cents !== null ? String(f.approved_cents / 100) : "");
  }
  async function save() {
    const body: Record<string, unknown> = { notes };
    if (approved !== "") body.approved_amount = Number(approved);
    if (motion !== (f.motion_id || "")) body.motion_id = motion;
    if (status !== f.status) body.status = status;
    await run(() => api.patch(url, body));
  }
  const cls = f.status === "approved" || f.status === "paid" ? "ok" : f.status === "denied" ? "bad" : f.status === "withdrawn" ? "" : "warn";
  return (
    <div className="request-row" style={{ marginTop: 10 }}>
      <div className="row spread">
        <strong>{f.title}</strong>
        <span className="row"><span className="mono">{money(f.amount_cents)}</span><span className={"chip " + cls}>{STATES.find((s) => s[0] === f.status)?.[1]}</span></span>
      </div>
      <div className="sub">{f.requester ? f.requester + " · " : ""}submitted {fmtDate(f.created_at)}{f.approved_cents !== null ? " · approved " + money(f.approved_cents) : ""}</div>
      {f.purpose && <div style={{ marginTop: 4 }}>{f.purpose}</div>}
      {f.motion && <div className="sub" style={{ marginTop: 4 }}>Motion: <Link to={"/meetings/" + f.motion.meeting_id + "?tab=votes"}>{f.motion.meeting} ({f.motion.meeting_date})</Link>, {f.motion.result || "no result"}. {f.motion.text}</div>}
      {f.notes && !open && <div className="sub">Notes: {f.notes}</div>}
      <div className="row" style={{ marginTop: 6 }}>
        {manage && <button onClick={() => { if (open) reset(); setOpen(!open); }}>{open ? "Close" : "Decide"}</button>}
        {!manage && f.status === "submitted" && <button onClick={() => void run(() => api.patch(url, { status: "withdrawn" }))}>Withdraw</button>}
      </div>
      {manage && open && (
        <div className="stack" style={{ marginTop: 8 }}>
          <label>Approving motion
            <select value={motion} onChange={(e) => setMotion(e.target.value)}>
              <option value="">Not linked</option>
              {motions.map((m) => <option key={m.id} value={m.id}>{m.meeting_date || m.title}: {m.text.slice(0, 80)} ({m.result || "no result"})</option>)}
            </select>
          </label>
          <div className="grid-2">
            <label>Status
              <select value={status} onChange={(e) => setStatus(e.target.value)}>{STATES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
            </label>
            <label>Approved amount<MoneyInput value={approved} onChange={setApproved} label="Approved amount in dollars" /></label>
          </div>
          <label>Notes<textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
          <div className="row">
            <button className="primary" disabled={!dirty} onClick={() => void save()}>Save</button>
            {dirty && <button onClick={reset}>Undo changes</button>}
            {dirty && <span className="badge warn">Not saved</span>}
            <button className="danger" onClick={() => { if (confirm("Delete this request?")) void run(() => api.del(url)); }}>Delete</button>
          </div>
        </div>
      )}
    </div>
  );
}
