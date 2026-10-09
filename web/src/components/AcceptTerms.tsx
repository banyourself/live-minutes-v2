import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useSession } from "../session";
import { ErrorBox, errText } from "../ui";
import { AuthCard } from "../pages/Login";
import { TERMS_DATE } from "../pages/legal-links";

export default function AcceptTerms() {
  const { refresh, logout } = useSession();
  const [agree, setAgree] = useState(false);
  const [error, setError] = useState("");
  async function accept() {
    setError("");
    try { await api.post("/api/auth/accept-terms"); await refresh(); } catch (e) { setError(errText(e)); }
  }
  return (
    <AuthCard title="Terms and privacy" sub={"Live Minutes published its Terms of use and Privacy policy, effective " + TERMS_DATE + "."}>
      <p style={{ margin: 0 }}>They explain what information Live Minutes keeps, how AI providers are used, that you must tell people when a meeting is being
        captured, that you must be 13 or older, how copyright complaints work, and that your college's code of conduct applies. Please read them before you continue.</p>
      <label className="row" style={{ textTransform: "none", letterSpacing: "normal", alignItems: "flex-start" }}>
        <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} style={{ marginTop: 4 }} />
        <span>I am 13 or older, and I agree to the <Link to="/terms" target="_blank">Terms of use</Link> and the <Link to="/privacy" target="_blank">Privacy policy</Link>.</span>
      </label>
      <ErrorBox error={error} />
      <div className="row">
        <button className="primary" disabled={!agree} onClick={() => void accept()}>Continue</button>
        <button className="link" onClick={() => void logout()}>Sign out</button>
      </div>
    </AuthCard>
  );
}
