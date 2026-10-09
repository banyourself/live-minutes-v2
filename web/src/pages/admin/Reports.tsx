import { useState } from "react";
import { api } from "../../api";
import { ErrorBox, useLoad } from "../../ui";

interface Month {
  month: string; meetings: number; approved: number; median_days_to_approve: number | null; active_orgs: number;
  active_people: number; ai_calls: number; ai_tokens: number; ai_cents: number; translations: number;
}
interface OrgRow { org: string; meetings: number; approved: number; ai_cents: number }

const money = (cents: number) => "$" + (cents / 100).toFixed(2);
const label = (m: string) => new Date(m + "-15T12:00:00Z").toLocaleDateString(undefined, { month: "short", year: "numeric" });

export function UsageReport({ url, title }: { url: string; title: string }) {
  const [months, setMonths] = useState(6);
  const [perMeeting, setPerMeeting] = useState(60);
  const data = useLoad(() => api.get<{ months: Month[]; orgs: OrgRow[]; org_count: number }>(url + "?months=" + months), [url, months]);
  const rows = data.data?.months || [];
  const total = rows.reduce((a, r) => ({ meetings: a.meetings + r.meetings, approved: a.approved + r.approved, cents: a.cents + r.ai_cents,
    tokens: a.tokens + r.ai_tokens }), { meetings: 0, approved: 0, cents: 0, tokens: 0 });
  const hours = Math.round((total.approved * perMeeting) / 60);
  return (
    <div className="stack">
      <div className="card stack">
        <div className="row spread">
          <h2 style={{ margin: 0 }}>{title}</h2>
          <div className="row">
            <select value={months} onChange={(e) => setMonths(Number(e.target.value))} style={{ width: "auto" }}>
              {[3, 6, 12, 24].map((n) => <option key={n} value={n}>Last {n} months</option>)}
            </select>
            <a className="btn" href={url + "?months=" + months + "&format=csv"}>CSV</a>
          </div>
        </div>
        <div className="stat-grid">
          <div className="stat"><span className="stat-label">Meetings</span><span className="stat-num">{total.meetings}</span><span className="stat-sub">{data.data?.org_count || 0} organizations</span></div>
          <div className="stat"><span className="stat-label">Minutes approved</span><span className="stat-num">{total.approved}</span></div>
          <div className="stat"><span className="stat-label">Time saved (estimate)</span><span className="stat-num">{hours} h</span>
            <span className="stat-sub">at <input type="number" min={0} max={600} value={perMeeting} onChange={(e) => setPerMeeting(Number(e.target.value))} style={{ width: 64, padding: "2px 6px" }} /> minutes per set of minutes</span></div>
          <div className="stat"><span className="stat-label">AI cost</span><span className="stat-num">{money(total.cents)}</span><span className="stat-sub">{total.tokens.toLocaleString()} tokens</span></div>
        </div>
        <ErrorBox error={data.error} />
        <table>
          <thead><tr><th>Month</th><th>Meetings</th><th>Approved</th><th>Median days to approve</th><th>Active orgs</th><th>Active people</th><th>AI calls</th><th>AI cost</th><th>Translations</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.month}>
                <td>{label(r.month)}</td><td>{r.meetings}</td><td>{r.approved}</td><td>{r.median_days_to_approve ?? ""}</td>
                <td>{r.active_orgs}</td><td>{r.active_people}</td><td>{r.ai_calls}</td><td>{money(r.ai_cents)}</td><td>{r.translations}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="sub" style={{ margin: 0 }}>Time saved is an estimate: approved minutes times the minutes you enter. Active people counts anyone who did something in an organization that month.</p>
      </div>
      {(data.data?.orgs || []).length > 0 && (
        <div className="card">
          <h2>By organization</h2>
          <table>
            <thead><tr><th>Organization</th><th>Meetings</th><th>Approved</th><th>AI cost</th></tr></thead>
            <tbody>{data.data!.orgs.map((o) => <tr key={o.org}><td>{o.org}</td><td>{o.meetings}</td><td>{o.approved}</td><td>{money(o.ai_cents)}</td></tr>)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function ProcurementCard() {
  const docs = useLoad(() => api.get<{ documents: { id: string; title: string }[] }>("/api/procurement"), []);
  return (
    <div className="card stack">
      <h2>Procurement paperwork</h2>
      <p className="sub" style={{ margin: 0 }}>Drafts for your district's review: security questionnaire answers, an accessibility report, a data protection agreement template, and the list of services that handle data. Each is a Markdown file you can paste into your own forms.</p>
      <div className="row">
        {(docs.data?.documents || []).map((d) => <a key={d.id} className="btn" href={"/api/procurement/" + d.id}>{d.title}</a>)}
      </div>
      <ErrorBox error={docs.error} />
    </div>
  );
}
