import { useEffect, useState } from "react";
import { api } from "../api";
import { ErrorBox, errText } from "../ui";

interface Request { client_name: string; return_host: string; known: string; wants_write: boolean; user: string }

export default function Connect() {
  const r = new URLSearchParams(location.search).get("r") || "";
  const [info, setInfo] = useState<Request | null>(null);
  const [write, setWrite] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!r) { setError("This page needs a connection request from an AI app."); return; }
    api.get<Request>("/api/oauth/request?r=" + encodeURIComponent(r))
      .then((d) => { setInfo(d); setWrite(d.wants_write); }).catch((e) => setError(errText(e)));
  }, [r]);

  async function decide(allow: boolean) {
    setBusy(true); setError("");
    try {
      const out = await api.post<{ redirect: string }>("/api/oauth/decide", { r, allow, can_write: write });
      location.assign(out.redirect);
    } catch (e) {
      setError(errText(e));
      setBusy(false);
    }
  }

  const app = info ? (info.known || info.client_name) : "";
  return (
    <div className="auth">
      <div className="card stack" style={{ maxWidth: 520 }}>
        <div className="kicker">Connect an AI app</div>
        <h1 style={{ margin: 0 }}>{info ? "Connect " + app + " to Live Minutes?" : "Connect an AI app"}</h1>
        <ErrorBox error={error} />
        {info && (
          <>
            <p style={{ margin: 0 }}>Signed in as <strong>{info.user}</strong>.</p>
            {info.known ? (
              <p className="sub" style={{ margin: 0 }}>After you choose, you go back to <strong>{info.return_host}</strong>.</p>
            ) : (
              <div className="alert warn">This app calls itself "{info.client_name}" and returns you to <strong>{info.return_host}</strong>.
                Only continue if you started this from an app you trust.</div>
            )}
            <div>
              <h3>It will be able to</h3>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                <li>See your organizations, meetings, transcripts, and minutes, only where you are a member</li>
                <li>Search past minutes</li>
                {write && <li>Save minute drafts for you to review (it can never approve minutes)</li>}
              </ul>
            </div>
            <label className="setting-row">
              <span>Let it save minute drafts</span>
              <input type="checkbox" checked={write} onChange={(e) => setWrite(e.target.checked)} />
            </label>
            <p className="sub" style={{ margin: 0 }}>You can disconnect it any time under My account, Connect your own AI.</p>
            <div className="row">
              <button className="primary" disabled={busy} onClick={() => void decide(true)}>Connect</button>
              <button disabled={busy} onClick={() => void decide(false)}>Cancel</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
