import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorBox, useLoad } from "../ui";
import { holidayOn, isoDay } from "../holidays";

interface Item { kind: string; text: string; link: string }
interface Section { org_id: string; org: string; items: Item[] }

const GROUPS: [string, string][] = [["review", "Waiting for your review"], ["waiting", "Waiting for approval"], ["upcoming", "Coming up"],
  ["held", "Met this week"], ["approved", "Minutes approved"], ["funding", "Funding"]];

export default function Week() {
  const data = useLoad(() => api.get<{ orgs: Section[] }>("/api/me/week"), []);
  const orgs = data.data?.orgs || [];
  const today = new Date();
  const ahead = Array.from({ length: 8 }, (_, i) => new Date(today.getFullYear(), today.getMonth(), today.getDate() + i, 12))
    .map((d) => ({ name: holidayOn(isoDay(d)), label: d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }) }))
    .filter((h) => h.name);
  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker">Summary</div>
          <h1>This week</h1>
          <p className="sub">The last seven days and the next seven for each of your organizations. To get this by email too, turn it on under My account, Notifications.</p>
        </div>
      </div>
      <ErrorBox error={data.error} />
      {ahead.length > 0 && (
        <div className="alert warn" role="status" style={{ marginBottom: 12 }}>
          Holiday{ahead.length === 1 ? "" : "s"} in the next seven days: {ahead.map((h) => h.name + " on " + h.label).join("; ")}. Many colleges are closed.
        </div>
      )}
      {data.loading ? <div className="empty">Loading…</div> : orgs.length === 0 ? <div className="card"><div className="empty">Nothing happened this week, and nothing is scheduled for the next seven days.</div></div> : orgs.map((o) => (
        <section key={o.org_id} className="card stack" aria-labelledby={"week-" + o.org_id}>
          <h2 id={"week-" + o.org_id}>{o.org}</h2>
          {GROUPS.map(([kind, label]) => {
            const items = o.items.filter((i) => i.kind === kind);
            if (!items.length) return null;
            return (
              <div key={kind}>
                <h3>{label}</h3>
                <ul className="week-list">
                  {items.map((i, n) => {
                    const [first, ...rest] = i.text.split("\n");
                    return (
                      <li key={n}>
                        {i.link ? <Link to={i.link}>{first}</Link> : first}
                        {rest.length > 0 && <div className="prewrap" style={{ fontFamily: "inherit", fontSize: "0.95rem" }}>{rest.join("\n")}</div>}
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </section>
      ))}
    </>
  );
}
