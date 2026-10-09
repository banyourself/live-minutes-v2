import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, type Me } from "../api";
import { useSession } from "../session";
import { ErrorBox, errText } from "../ui";
import Login from "./Login";

export default function Invite() {
  const { token = "" } = useParams();
  const fallback = location.pathname.split("/invite/")[1] || "";
  const invite = token || fallback;
  const { me, refresh, setOrgId } = useSession();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [personal, setPersonal] = useState(false);

  useEffect(() => {
    api.get<{ personal: boolean }>("/api/auth/invites/" + encodeURIComponent(invite))
      .then((r) => setPersonal(r.personal)).catch(() => undefined);
  }, [invite]);

  if (!me) return <Login inviteToken={invite} />;

  async function accept() {
    setBusy(true);
    try {
      const data = await api.post<Me>("/api/auth/invites/accept", { token: invite });
      await refresh();
      const joined = data.orgs[data.orgs.length - 1];
      if (joined) setOrgId(joined.id);
      navigate("/dashboard");
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <div className="card stack">
        <h1>{personal ? "Your own workspace" : "Join organization"}</h1>
        <p className="sub">Signed in as {me.user.email}. {personal ? "Accept the invitation to add your private workspace." : "Accept the invitation to join."}</p>
        <ErrorBox error={error} />
        <div className="row">
          <button className="primary" disabled={busy} onClick={() => void accept()}>Accept invitation</button>
          <button onClick={() => navigate("/dashboard")}>Not now</button>
        </div>
      </div>
    </div>
  );
}
