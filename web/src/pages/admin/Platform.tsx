import { useState } from "react";
import MoneyInput from "../../components/MoneyInput";
import { api } from "../../api";
import { ErrorBox, errText, fmtDate, useLoad } from "../../ui";
import { useSudo } from "./sudo";

interface RoleRow { id: string; scope: string; target_id: string; target: string; email: string; name: string; staff_email: string; created_at: number }
interface Area { id: string; name: string; staff_domains: string[]; district_id?: string }

export function ItRoles() {
  const guard = useSudo();
  const data = useLoad(() => api.get<{ roles: RoleRow[]; districts: Area[]; schools: Area[] }>("/api/admin/roles"), []);
  const [scope, setScope] = useState("district");
  const [target, setTarget] = useState("");
  const [email, setEmail] = useState("");
  const [staff, setStaff] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const d = data.data;
  const options = scope === "district" ? d?.districts || [] : d?.schools || [];
  const split = (v: string) => v.split(/[\s,]+/).map((x) => x.trim()).filter(Boolean);

  async function run(fn: () => Promise<unknown>, done: string) {
    setMsg(""); setError("");
    try { await guard(fn); setMsg(done); await data.reload(); } catch (e) { if (errText(e) !== "cancelled") setError(errText(e)); }
  }

  return (
    <div className="stack">
      <div className="card stack">
        <h2>Role levels</h2>
        <table>
          <tbody>
            <tr><td><strong>Platform owner</strong></td><td className="sub">You. Everything on the server, including billing, settings, and deleting accounts.</td></tr>
            <tr><td><strong>District IT</strong></td><td className="sub">One district: its colleges, organizations, people, and college IT. Granted by the platform owner.</td></tr>
            <tr><td><strong>College IT</strong></td><td className="sub">One college: its organizations, people, and join requests. Granted by district IT or the platform owner.</td></tr>
            <tr><td><strong>Organization owner</strong></td><td className="sub">One organization's settings and members.</td></tr>
          </tbody>
        </table>
        <p className="sub" style={{ margin: 0 }}>IT roles need a confirmed staff email on that district's or college's staff domains. Nobody can grant a role to themselves or above their own level.</p>
      </div>
      <div className="card stack">
        <h2>IT staff</h2>
        {msg && <div className="alert ok" role="status">{msg}</div>}
        <ErrorBox error={error || data.error} />
        <table>
          <thead><tr><th>Person</th><th>Role</th><th>Granted</th><th /></tr></thead>
          <tbody>
            {(d?.roles || []).map((r) => (
              <tr key={r.id}>
                <td>{r.name || r.email}<div className="sub">{r.email} · verified {r.staff_email}</div></td>
                <td>{r.scope === "district" ? "District IT" : "College IT"}<div className="sub">{r.target}</div></td>
                <td>{fmtDate(r.created_at)}</td>
                <td><button className="danger" onClick={() => void run(() => api.del("/api/admin/roles/" + r.id), "Role removed.")}>Remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {d && d.roles.length === 0 && <p className="sub">No IT staff yet.</p>}
        <h3>Grant a role</h3>
        <div className="row wrap">
          <select value={scope} onChange={(e) => { setScope(e.target.value); setTarget(""); }}>
            <option value="district">District IT</option><option value="school">College IT</option>
          </select>
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">Choose…</option>
            {options.map((o) => <option key={o.id} value={o.id}>{o.name}{o.staff_domains.length ? "" : " (no staff domains yet)"}</option>)}
          </select>
          <input type="email" style={{ flex: 1, minWidth: 220 }} value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Their Live Minutes sign-in email" placeholder="Their Live Minutes sign-in email" />
          <button className="primary" disabled={!target || !email} onClick={() => void run(async () => {
            await api.post("/api/admin/roles", { email, scope, target_id: target }); setEmail("");
          }, "Role granted.")}>Grant</button>
        </div>
      </div>
      <div className="card stack">
        <h2>District staff domains</h2>
        <p className="sub" style={{ margin: 0 }}>Email domains that only district employees have, such as cccd.edu. College staff domains are set on the Schools tab.</p>
        <table>
          <tbody>
            {(d?.districts || []).map((x) => {
              const v = staff[x.id] ?? x.staff_domains.join(", ");
              return (
                <tr key={x.id}>
                  <td>{x.name}</td>
                  <td><input value={v} onChange={(e) => setStaff({ ...staff, [x.id]: e.target.value })} aria-label="Staff email domains" placeholder="district.edu" /></td>
                  <td><button onClick={() => void run(() => api.patch("/api/admin/districts/" + x.id, { staff_domains: split(v) }), "Saved.")}>Save</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface Plan { id: string; name: string; description: string; price_cents: number; interval: string; seat_limit: number | null; active: boolean }
interface Sub { id: string; plan_id: string; plan: string; scope: string; target_id: string; target: string; status: string; seats: number | null;
  used_seats: number; price_cents: number; interval: string; monthly_cents: number; started_at: number; renews_at: number | null; notes: string }
interface Billing {
  payments_connected: boolean;
  summary: { mrr_cents: number; arr_cents: number; counts: Record<string, number>; renewals_30d: number; renewals_30d_cents: number; by_plan: { plan: string; mrr_cents: number }[] };
  plans: Plan[];
  subscriptions: Sub[];
  targets: Record<string, { id: string; name: string }[]>;
}

const money = (cents: number) => (cents / 100).toLocaleString(undefined, { style: "currency", currency: "USD" });

export function BillingPanel() {
  const guard = useSudo();
  const data = useLoad(() => api.get<Billing>("/api/admin/billing"), []);
  const [plan, setPlan] = useState({ name: "", price: "", interval: "year", seats: "", description: "" });
  const [sub, setSub] = useState({ plan_id: "", scope: "school", target_id: "", status: "active", renews: "" });
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const d = data.data;
  async function run(fn: () => Promise<unknown>, done: string) {
    setMsg(""); setError("");
    try { await guard(fn); setMsg(done); await data.reload(); } catch (e) { if (errText(e) !== "cancelled") setError(errText(e)); }
  }
  if (!d) return <ErrorBox error={data.error} />;
  const s = d.summary;
  return (
    <div className="stack">
      {!d.payments_connected && <div className="alert warn">Payments are not connected yet, so nobody is charged. These records track plans and contracts by hand until a processor such as Stripe is added.</div>}
      <div className="stat-grid">
        <div className="stat"><span className="stat-label">Monthly recurring revenue</span><span className="stat-num">{money(s.mrr_cents)}</span></div>
        <div className="stat"><span className="stat-label">Annual run rate</span><span className="stat-num">{money(s.arr_cents)}</span></div>
        <div className="stat"><span className="stat-label">Active subscriptions</span><span className="stat-num">{s.counts.active || 0}</span>
          <span className="stat-sub">{s.counts.trial || 0} trials · {s.counts.past_due || 0} past due · {s.counts.canceled || 0} canceled</span></div>
        <div className={"stat" + (s.renewals_30d ? " attention" : "")}><span className="stat-label">Renewing in 30 days</span><span className="stat-num">{s.renewals_30d}</span>
          <span className="stat-sub">{money(s.renewals_30d_cents)}</span></div>
      </div>
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error} />
      <div className="card stack">
        <h2>Subscriptions</h2>
        <table>
          <thead><tr><th>Customer</th><th>Plan</th><th>Price</th><th>Seats</th><th>Status</th><th>Renews</th></tr></thead>
          <tbody>
            {d.subscriptions.map((x) => (
              <tr key={x.id}>
                <td>{x.target}<div className="sub">{x.scope === "school" ? "college" : x.scope === "org" ? "organization" : "district"}</div></td>
                <td>{x.plan}</td>
                <td>{money(x.price_cents)}<span className="sub"> / {x.interval}</span></td>
                <td>{x.used_seats}{x.seats ? " of " + x.seats : ""}</td>
                <td><select value={x.status} onChange={(e) => void run(() => api.patch("/api/admin/subscriptions/" + x.id, { status: e.target.value }), "Status updated.")}>
                  {["trial", "active", "past_due", "canceled"].map((st) => <option key={st} value={st}>{st.replace("_", " ")}</option>)}
                </select></td>
                <td>{x.renews_at ? fmtDate(x.renews_at) : <span className="sub">not set</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {d.subscriptions.length === 0 && <p className="sub">No subscriptions yet.</p>}
        <h3>Add a subscription</h3>
        <div className="row wrap">
          <select value={sub.plan_id} onChange={(e) => setSub({ ...sub, plan_id: e.target.value })}>
            <option value="">Plan…</option>{d.plans.filter((p) => p.active).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <select value={sub.scope} onChange={(e) => setSub({ ...sub, scope: e.target.value, target_id: "" })}>
            <option value="district">District</option><option value="school">College</option><option value="org">Organization</option>
          </select>
          <select value={sub.target_id} onChange={(e) => setSub({ ...sub, target_id: e.target.value })}>
            <option value="">Customer…</option>{(d.targets[sub.scope] || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <select value={sub.status} onChange={(e) => setSub({ ...sub, status: e.target.value })}>
            <option value="trial">trial</option><option value="active">active</option>
          </select>
          <input type="date" value={sub.renews} onChange={(e) => setSub({ ...sub, renews: e.target.value })} />
          <button className="primary" disabled={!sub.plan_id || !sub.target_id} onClick={() => void run(() => api.post("/api/admin/subscriptions", {
            plan_id: sub.plan_id, scope: sub.scope, target_id: sub.target_id, status: sub.status,
            renews_at: sub.renews ? new Date(sub.renews + "T12:00:00").getTime() / 1000 : null
          }), "Subscription added.")}>Add</button>
        </div>
      </div>
      <div className="card stack">
        <h2>Plans</h2>
        <table>
          <thead><tr><th>Plan</th><th>Price</th><th>Seats</th><th>Revenue now</th></tr></thead>
          <tbody>
            {d.plans.map((p) => (
              <tr key={p.id}>
                <td>{p.name}{!p.active && <span className="sub"> · retired</span>}<div className="sub">{p.description}</div></td>
                <td>{money(p.price_cents)} / {p.interval}</td>
                <td>{p.seat_limit ?? "unlimited"}</td>
                <td>{money(s.by_plan.find((b) => b.plan === p.name)?.mrr_cents || 0)} / month</td>
              </tr>
            ))}
          </tbody>
        </table>
        <h3>Add a plan</h3>
        <div className="row wrap">
          <input value={plan.name} onChange={(e) => setPlan({ ...plan, name: e.target.value })} aria-label="Plan name" placeholder="Plan name" />
          <MoneyInput style={{ width: 140 }} value={plan.price} onChange={(v) => setPlan({ ...plan, price: v })} label="Price in dollars" placeholder="500.00" />
          <select value={plan.interval} onChange={(e) => setPlan({ ...plan, interval: e.target.value })}><option value="month">per month</option><option value="year">per year</option></select>
          <input type="number" min={1} style={{ width: 120 }} value={plan.seats} onChange={(e) => setPlan({ ...plan, seats: e.target.value })} aria-label="Seats" placeholder="Seats" />
          <input style={{ flex: 1, minWidth: 200 }} value={plan.description} onChange={(e) => setPlan({ ...plan, description: e.target.value })} aria-label="What the plan includes" placeholder="What it includes" />
          <button className="primary" disabled={!plan.name || plan.price === ""} onClick={() => void run(async () => {
            await api.post("/api/admin/plans", { name: plan.name, description: plan.description, price_cents: Math.round(Number(plan.price) * 100),
              interval: plan.interval, seat_limit: plan.seats ? Number(plan.seats) : null });
            setPlan({ name: "", price: "", interval: "year", seats: "", description: "" });
          }, "Plan added.")}>Add plan</button>
        </div>
      </div>
    </div>
  );
}
