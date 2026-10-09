import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorBox, errText, fmtDate, useLoad } from "../ui";

interface Note { id: string; kind: string; title: string; body: string; link: string; org: string; created_at: number; read: boolean }

const KIND: Record<string, string> = {
  draft_ready: "Draft", review_needed: "Review", review_done: "Review", reminder: "Reminder", digest: "Weekly", officer: "Officer", app_connected: "Connected app"
};

export function useUnread() {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let alive = true;
    const load = () => api.get<{ unread: number }>("/api/me/notifications/count").then((r) => { if (alive) setCount(r.unread); }).catch(() => undefined);
    void load();
    const t = window.setInterval(load, 60000);
    const onRead = () => void load();
    window.addEventListener("lm-notifications", onRead);
    return () => { alive = false; window.clearInterval(t); window.removeEventListener("lm-notifications", onRead); };
  }, []);
  return count;
}

export default function Notifications() {
  const data = useLoad(() => api.get<{ notifications: Note[]; unread: number }>("/api/me/notifications"), []);
  const [error, setError] = useState("");

  async function read(body: { ids?: string[]; all?: boolean }) {
    setError("");
    try {
      await api.post("/api/me/notifications/read", body);
      window.dispatchEvent(new Event("lm-notifications"));
      await data.reload();
    } catch (e) {
      setError(errText(e));
    }
  }

  const rows = data.data?.notifications || [];
  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker">Inbox</div>
          <h1>Notifications</h1>
          <p className="sub">Drafts, reviews, reminders, and officer changes. Choose which ones also come by email under My account.</p>
        </div>
        {(data.data?.unread || 0) > 0 && <button onClick={() => void read({ all: true })}>Mark all read</button>}
      </div>
      <ErrorBox error={error || data.error} />
      <div className="card">
        {rows.length === 0 ? <div className="empty">Nothing yet.</div> : rows.map((n) => (
          <div key={n.id} className={"request-row note" + (n.read ? "" : " unread")} style={{ marginTop: 10 }}>
            <div className="row spread">
              <strong>{n.link ? <Link to={n.link} onClick={() => { if (!n.read) void read({ ids: [n.id] }); }}>{n.title}</Link> : n.title}</strong>
              <span className="row"><span className="chip">{KIND[n.kind] || n.kind}</span>{!n.read && <span className="chip accent">New</span>}</span>
            </div>
            <div className="sub">{n.org ? n.org + " · " : ""}{fmtDate(n.created_at)}</div>
            <div className="prewrap" style={{ fontFamily: "inherit", fontSize: "0.95rem", background: "none", border: 0, padding: "4px 0 0" }}>{n.body}</div>
            {!n.read && <button className="link" onClick={() => void read({ ids: [n.id] })}>Mark read</button>}
          </div>
        ))}
      </div>
    </>
  );
}

export function NotificationSettings() {
  const data = useLoad(() => api.get<{ email: Record<string, boolean>; digest_weekday: number; labels: { id: string; label: string }[]; days: string[] }>("/api/me/notification-prefs"), []);
  const [error, setError] = useState("");
  async function save(body: object) {
    setError("");
    try { data.setData(await api.put("/api/me/notification-prefs", body)); } catch (e) { setError(errText(e)); }
  }
  const d = data.data;
  return (
    <div className="card stack" id="notifications">
      <h2>Notifications</h2>
      <p className="sub" style={{ margin: 0 }}>Everything shows up under Notifications. Choose which ones also come by email.</p>
      {d && d.labels.map((l) => (
        <label key={l.id} className="setting-row">
          <span>{l.label}</span>
          <input type="checkbox" checked={d.email[l.id]} onChange={(e) => void save({ email: { [l.id]: e.target.checked } })} />
        </label>
      ))}
      {d && (
        <label>Weekly summary day
          <select value={d.digest_weekday} onChange={(e) => void save({ digest_weekday: Number(e.target.value) })}>
            {d.days.map((name, i) => <option key={name} value={i}>{name}</option>)}
          </select>
        </label>
      )}
      <ErrorBox error={error || data.error} />
    </div>
  );
}
