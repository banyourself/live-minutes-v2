import { useState, type FormEvent } from "react";
import { encode } from "uqr";
import { api } from "../api";
import { useSudo } from "../pages/admin/sudo";
import { useSession } from "../session";
import { ErrorBox, errText, fmtDate, useLoad } from "../ui";

interface Setup { secret: string; uri: string }
interface SessionRow { id: string; user_agent: string; created_at: number; last_seen_at: number | null; current: boolean }

function QrCode({ text }: { text: string }) {
  const qr = encode(text, { border: 2, ecc: "M" });
  const path = qr.data.flatMap((row, y) => row.map((on, x) => (on ? "M" + x + " " + y + "h1v1h-1z" : ""))).join("");
  return (
    <svg viewBox={"0 0 " + qr.size + " " + qr.size} width={208} height={208} role="img"
      aria-label="QR code to add Live Minutes to your authenticator app" style={{ background: "#fff", shapeRendering: "crispEdges" }}>
      <path d={path} fill="#000" />
    </svg>
  );
}

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const text = codes.join("\n");
  return (
    <div className="stack">
      <div className="alert warn">Save these recovery codes somewhere safe, such as a password manager. Each one signs you in once if you lose
        your phone. They are shown only now.</div>
      <div className="token-box mono" style={{ whiteSpace: "pre" }}>{text}</div>
      <div className="row">
        <button onClick={() => void navigator.clipboard.writeText(text)}>Copy codes</button>
        <a className="btn" download="live-minutes-recovery-codes.txt" href={"data:text/plain;charset=utf-8," + encodeURIComponent(text + "\n")}>Download</a>
        <button className="primary" onClick={onDone}>I saved them</button>
      </div>
    </div>
  );
}

export function TwoStepCard() {
  const { me, refresh } = useSession();
  const guard = useSudo();
  const on = !!me?.user.two_factor;
  const [setup, setSetup] = useState<Setup | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [code, setCode] = useState("");
  const [mode, setMode] = useState<"" | "off" | "codes">("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function run(fn: () => Promise<void>) {
    setBusy(true); setError(""); setMsg("");
    try {
      await fn();
    } catch (e) {
      if (errText(e) !== "cancelled") setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  const start = () => run(async () => {
    setSetup(await guard(() => api.post<Setup>("/api/auth/two-factor/setup")));
    setCode("");
  });

  async function enable(e: FormEvent) {
    e.preventDefault();
    await run(async () => {
      const r = await api.post<{ recovery_codes: string[] }>("/api/auth/two-factor/enable", { code });
      setSetup(null);
      setCode("");
      setCodes(r.recovery_codes);
      await refresh();
    });
  }

  async function confirm(e: FormEvent) {
    e.preventDefault();
    await run(async () => {
      if (mode === "off") {
        await guard(() => api.post("/api/auth/two-factor/disable", { code }));
        setMsg("Two-step sign-in is off.");
      } else {
        const r = await guard(() => api.post<{ recovery_codes: string[] }>("/api/auth/two-factor/recovery-codes", { code }));
        setCodes(r.recovery_codes);
      }
      setMode("");
      setCode("");
      await refresh();
    });
  }

  if (!me?.user.has_password) {
    return (
      <div className="card stack">
        <h2>Two-step sign-in</h2>
        <p className="sub">Set a password first. Your school sign-in uses your school's own security, such as its own two-step check.</p>
      </div>
    );
  }

  return (
    <div className="card stack">
      <h2>Two-step sign-in</h2>
      {codes ? (
        <RecoveryCodes codes={codes} onDone={() => setCodes(null)} />
      ) : setup ? (
        <form className="stack" onSubmit={enable}>
          <p className="sub">Scan this code with an authenticator app, such as Google Authenticator, Microsoft Authenticator, 1Password, or
            your phone's built-in passwords app. Or enter the key by hand.</p>
          <QrCode text={setup.uri} />
          <div className="token-box mono">{setup.secret.replace(/(.{4})/g, "$1 ").trim()}</div>
          <label>The 6-digit code your app shows
            <input inputMode="numeric" autoComplete="one-time-code" maxLength={8} value={code} onChange={(e) => setCode(e.target.value)} />
          </label>
          <div className="row">
            <button className="primary" disabled={busy || code.replace(/\D/g, "").length !== 6}>Turn on</button>
            <button type="button" onClick={() => setSetup(null)}>Cancel</button>
          </div>
        </form>
      ) : on ? (
        <>
          <p>On. Signing in with your password also asks for a code from your authenticator app.</p>
          <p className="sub">{me.user.recovery_codes_left} recovery codes left.</p>
          {mode ? (
            <form className="stack" onSubmit={confirm}>
              <label>{mode === "off" ? "Enter a code from your app to turn two-step sign-in off" : "Enter a code from your app to make new recovery codes"}
                <input autoComplete="one-time-code" maxLength={16} value={code} onChange={(e) => setCode(e.target.value)} />
              </label>
              <div className="row">
                <button className={mode === "off" ? "danger" : "primary"} disabled={busy || !code.trim()}>{mode === "off" ? "Turn off" : "Make new codes"}</button>
                <button type="button" onClick={() => { setMode(""); setCode(""); }}>Cancel</button>
              </div>
            </form>
          ) : (
            <div className="row">
              <button onClick={() => setMode("codes")}>New recovery codes</button>
              <button className="danger" onClick={() => setMode("off")}>Turn off</button>
            </div>
          )}
        </>
      ) : (
        <>
          <p className="sub">Protect your account with a code from an authenticator app, so a stolen password alone cannot sign in.</p>
          <div className="row"><button className="primary" disabled={busy} onClick={() => void start()}>Set up two-step sign-in</button></div>
        </>
      )}
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error} />
    </div>
  );
}

function device(agent: string) {
  const a = agent.toLowerCase();
  const browser = a.includes("edg/") ? "Edge" : a.includes("chrome/") ? "Chrome" : a.includes("firefox/") ? "Firefox" : a.includes("safari/") ? "Safari" : "";
  const system = a.includes("windows") ? "Windows" : a.includes("iphone") || a.includes("ipad") ? "iPhone or iPad" : a.includes("android") ? "Android"
    : a.includes("mac os") ? "Mac" : a.includes("linux") ? "Linux" : "";
  return [browser, system].filter(Boolean).join(" on ") || "Unknown device";
}

export function SessionsCard({ onEverywhere }: { onEverywhere: () => void }) {
  const list = useLoad(() => api.get<{ sessions: SessionRow[] }>("/api/auth/sessions"), []);
  const [error, setError] = useState("");
  return (
    <div className="card stack">
      <h2>Where you are signed in</h2>
      {(list.data?.sessions || []).map((s) => (
        <div key={s.id} className="row spread motion">
          <span>{device(s.user_agent)}{s.current && <strong> · this device</strong>}<br />
            <span className="sub">Signed in {fmtDate(s.created_at)} · last active {fmtDate(s.last_seen_at || s.created_at)}</span></span>
          {!s.current && <button onClick={async () => {
            try { await api.del("/api/auth/sessions/" + s.id); await list.reload(); } catch (e) { setError(errText(e)); }
          }}>Sign out</button>}
        </div>
      ))}
      <p className="sub">If you see a device you do not recognize, sign it out and change your password.</p>
      <div className="row"><button onClick={onEverywhere}>Sign out everywhere</button></div>
      <ErrorBox error={error || list.error} />
    </div>
  );
}
