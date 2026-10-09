import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorBox, useLoad } from "../ui";

interface Item { key: string; label: string; why: string; required: boolean; where: string; link: string; ok: boolean | null }
interface Checklist { checked: boolean; note: string; items: Item[]; ready: boolean }

export function useZoomChecklist(orgId: string) {
  return useLoad(() => api.get<Checklist>("/api/orgs/" + orgId + "/zoom/checklist"), [orgId]);
}

export function ZoomWarning({ orgId }: { orgId: string }) {
  const data = useZoomChecklist(orgId);
  const missing = (data.data?.items || []).filter((i) => i.required && i.ok === false);
  if (!data.data?.checked || missing.length === 0) return null;
  return (
    <div className="alert warn" role="status">
      Your Zoom account is not set to {missing.map((i) => i.label.toLowerCase()).join(", ")}, so imports may come in without
      {missing.some((i) => i.key === "audio_transcript") ? " a transcript" : " everything"}.{" "}
      <Link to="/settings?tab=zoom">See the Zoom checklist</Link>
    </div>
  );
}

export default function ZoomChecklist({ orgId }: { orgId: string }) {
  const data = useZoomChecklist(orgId);
  const d = data.data;
  return (
    <div className="card stack" style={{ maxWidth: 760 }}>
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Zoom setup checklist</h2>
        <button disabled={data.loading} onClick={() => void data.reload()}>{data.loading ? "Checking…" : "Check again"}</button>
      </div>
      {d && !d.checked && (
        <p className="sub" style={{ margin: 0 }}>{d.note || "Connect Zoom above and Live Minutes checks these for you."} Until then, sign in at
          zoom.us with the account that hosts your meetings and turn these on yourself.</p>
      )}
      {d?.ready && <div className="alert ok" role="status">Your Zoom is ready. Each recording imports with its transcript and chat.</div>}
      <ul className="checklist">
        {(d?.items || []).map((i) => (
          <li key={i.key} className={i.ok === true ? "ok" : i.ok === false ? "bad" : ""}>
            <span className="check-mark" aria-hidden="true">{i.ok === true ? "✓" : i.ok === false ? "✕" : "•"}</span>
            <div>
              <strong>{i.label}</strong> <span className="chip">{i.required ? "Needed" : "Recommended"}</span>
              <span className="sr-only">{i.ok === true ? "On" : i.ok === false ? "Off" : "Not checked"}</span>
              <div className="sub">{i.why}</div>
              {i.ok !== true && <div className="sub">In Zoom: {i.where}. <a href={i.link} target="_blank" rel="noopener noreferrer">Open Zoom settings</a></div>}
            </div>
          </li>
        ))}
      </ul>
      <p className="sub" style={{ margin: 0 }}>After changing a setting in Zoom, come back and press Check again. Settings apply to meetings recorded after the change.</p>
      <ErrorBox error={data.error} />
    </div>
  );
}
