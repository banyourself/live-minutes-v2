import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useSession } from "../session";
import { ErrorBox, errText, useLoad } from "../ui";

interface Pending { host_email: string; expires_at: number; workspaces: { id: string; name: string }[] }

export default function ZoomConnect() {
  const [params] = useSearchParams();
  const denied = params.get("zoom") === "denied";
  const { refresh, setOrgId } = useSession();
  const navigate = useNavigate();
  const pending = useLoad(() => (denied ? Promise.resolve(null) : api.get<Pending>("/api/zoom/pending")), [denied]);
  const [choice, setChoice] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const p = pending.data;

  async function connect(orgId: string) {
    setBusy(true);
    setError("");
    try {
      await api.post("/api/zoom/pending/claim", { org_id: orgId });
      await refresh();
      setOrgId(orgId);
      navigate("/settings?tab=zoom&zoom=connected");
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    setBusy(true);
    try {
      await api.del("/api/zoom/pending");
      navigate("/dashboard");
    } catch (e) {
      setError(errText(e));
      setBusy(false);
    }
  }

  return (
    <div className="card stack" style={{ maxWidth: 640 }}>
      <h1>Connect Zoom</h1>
      {denied ? (
        <p>Zoom was not connected, because access was not allowed. You can try again from Settings, Zoom, whenever you are ready.</p>
      ) : pending.error ? (
        <p className="sub">{pending.error.includes("waiting") ? "No Zoom account is waiting to be connected. Start from Settings, Zoom." : pending.error}</p>
      ) : !p ? (
        <p className="sub">Loading…</p>
      ) : p.workspaces.length === 0 ? (
        <>
          <p>You signed in to Zoom as <strong>{p.host_email}</strong>, but you do not run meetings in any Live Minutes workspace, so there is nowhere to connect it.</p>
          <p className="sub">Ask a workspace owner to give you the Runs meetings role, then connect Zoom from Settings.</p>
          <div className="row"><button disabled={busy} onClick={() => void cancel()}>Cancel and remove access</button></div>
        </>
      ) : (
        <>
          <p>You signed in to Zoom as <strong>{p.host_email}</strong>. Choose the workspace whose meetings this Zoom account hosts.</p>
          <p className="sub">Live Minutes will be able to read this account's cloud recordings, transcripts, chat, and recording settings. It cannot join, record, or change anything in Zoom.</p>
          <div className="stack" role="radiogroup" aria-label="Workspace">
            {p.workspaces.map((w) => (
              <label key={w.id} className="row" style={{ gap: 8 }}>
                <input type="radio" name="workspace" checked={choice === w.id} onChange={() => setChoice(w.id)} />
                {w.name}
              </label>
            ))}
          </div>
          <div className="row">
            <button className="primary" disabled={busy || !choice} onClick={() => void connect(choice)}>Connect Zoom</button>
            <button disabled={busy} onClick={() => void cancel()}>Cancel and remove access</button>
          </div>
        </>
      )}
      <ErrorBox error={error} />
      <p className="sub"><Link to="/help/zoom">How the Zoom app works</Link></p>
    </div>
  );
}
