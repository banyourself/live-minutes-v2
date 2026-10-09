import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api } from "../api";
import AccountTypePicker from "../components/AccountType";
import PasswordRules, { passwordOk } from "../components/PasswordRules";
import Turnstile from "../components/Turnstile";
import { Link } from "react-router-dom";
import { LegalLinks } from "./legal-links";
import { useSession } from "../session";
import { ErrorBox, errText } from "../ui";

interface SsoInfo {
  providers: { id: string; label: string }[];
  signup: boolean;
  personal?: boolean;
  mail: boolean;
  turnstile_site_key: string;
}

type Mode = "login" | "signup" | "forgot" | "sent";

const desktopApp = navigator.userAgent.includes(" LiveMinutesDesktop/");

const USES: { id: "personal" | "school"; label: string; hint: string }[] = [
  { id: "personal", label: "Personal", hint: "Your own meetings outside school, in a private workspace. No organization needed." },
  { id: "school", label: "School", hint: "Students, faculty, staff, and IT at a college or district." }
];

export function AuthCard({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <div className="auth">
      <div className="card stack">
        <div className="punch" aria-hidden="true"><i /><i /><i /></div>
        <div className="auth-head">
          <div>
            <div className="kicker">Records office</div>
            <div className="brand" style={{ padding: 0, marginTop: 6 }}>
              <img src="/favicon.svg" alt="" width={30} height={30} />
              Live Minutes
            </div>
          </div>
          <span className="stamp">Authorized only</span>
        </div>
        <div>
          <h1>{title}</h1>
          {sub && <p className="sub">{sub}</p>}
        </div>
        {children}
        <p className="sub" style={{ textAlign: "center", margin: 0 }}><LegalLinks /></p>
      </div>
    </div>
  );
}

export default function Login({ inviteToken = "" }: { inviteToken?: string }) {
  const { refresh } = useSession();
  const [mode, setMode] = useState<Mode>(inviteToken || new URLSearchParams(location.search).get("mode") === "signup" ? "signup" : "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [accountType, setAccountType] = useState("");
  const [use, setUse] = useState<"" | "personal" | "school">("");
  const [agree, setAgree] = useState(false);
  const [error, setError] = useState(new URLSearchParams(location.search).get("error") || "");
  const [busy, setBusy] = useState(false);
  const [sso, setSso] = useState<SsoInfo>({ providers: [], signup: true, mail: false, turnstile_site_key: "" });
  const [captcha, setCaptcha] = useState("");
  const [resetCaptcha, setResetCaptcha] = useState(0);
  const onToken = useCallback((t: string) => setCaptcha(t), []);
  const [personalInvite, setPersonalInvite] = useState(false);
  const [secondStep, setSecondStep] = useState(new URLSearchParams(location.search).get("two_factor") === "1");
  const [code, setCode] = useState("");
  const notice = new URLSearchParams(location.search).get("reset") === "1"
    ? "Your password was changed. Sign in with your new password and a code from your authenticator app." : "";

  useEffect(() => {
    api.get<SsoInfo>("/api/auth/sso").then(setSso).catch(() => undefined);
  }, []);

  useEffect(() => {
    const heading = secondStep ? "Sign in"
      : ({ login: "Sign in", signup: "Create your account", forgot: "Reset your password", sent: "Check your email" } as Record<Mode, string>)[mode];
    document.title = heading + " · Live Minutes";
  }, [mode, secondStep]);

  useEffect(() => {
    if (!inviteToken) return;
    api.get<{ personal: boolean }>("/api/auth/invites/" + encodeURIComponent(inviteToken))
      .then((r) => { if (r.personal) { setPersonalInvite(true); setAccountType("personal"); } })
      .catch(() => undefined);
  }, [inviteToken]);

  function go(next: Mode) {
    setMode(next);
    setError("");
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "login") {
        const r = await api.post<{ status?: string }>("/api/auth/login", { email, password, captcha });
        if (r.status === "two_factor") {
          setSecondStep(true);
          setPassword("");
          return;
        }
        await refresh();
      } else if (mode === "signup") {
        const r = await api.post<{ status?: string }>("/api/auth/signup", { email, password, name, account_type: accountType, invite_token: inviteToken, captcha, accept_terms: agree });
        if (r.status === "check_email") {
          setMode("sent");
        } else {
          await refresh();
          if (inviteToken) history.replaceState(null, "", "/dashboard");
        }
      } else if (mode === "forgot") {
        await api.post("/api/auth/forgot", { email, captcha });
        setMode("sent");
      }
    } catch (err) {
      setError(errText(err));
      setResetCaptcha((n) => n + 1);
    } finally {
      setBusy(false);
    }
  }

  async function finishSecondStep(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api.post<{ next?: string }>("/api/auth/login/two-factor", { code });
      const next = r.next && r.next !== "/" && r.next !== "/dashboard" ? r.next : "";
      if (next) {
        location.assign(next);
        return;
      }
      history.replaceState(null, "", location.pathname === "/login" ? "/dashboard" : location.pathname);
      await refresh();
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  if (secondStep) {
    return (
      <AuthCard title="Two-step sign-in" sub="Enter the 6-digit code from your authenticator app, or one of your recovery codes.">
        <form className="stack" onSubmit={finishSecondStep}>
          <label>Code
            <input autoFocus autoComplete="one-time-code" inputMode="text" maxLength={16} value={code} onChange={(e) => setCode(e.target.value)} />
          </label>
          <ErrorBox error={error} />
          <button className="primary" style={{ justifyContent: "center" }} disabled={busy || !code.trim()}>{busy ? "Checking…" : "Sign in"}</button>
        </form>
        <p className="sub" style={{ textAlign: "center", margin: 0 }}>
          <button className="link" onClick={() => { setSecondStep(false); setCode(""); setError(""); history.replaceState(null, "", location.pathname); }}>Back to sign in</button>
        </p>
      </AuthCard>
    );
  }

  if (mode === "sent") {
    return (
      <AuthCard title="Check your email" sub={"If " + (email || "that address") + " can use Live Minutes, a link is on its way. It may take a minute, and it can land in spam."}>
        <button onClick={() => go("login")}>Back to sign in</button>
      </AuthCard>
    );
  }

  const title = mode === "login" ? "Sign in" : mode === "signup" ? "Create your account" : "Reset your password";
  const sub = mode === "forgot" ? "Enter your email and we will send a link to choose a new password." :
    inviteToken ? (personalInvite ? "You were invited to your own private Live Minutes workspace. Create an account with the invited email."
      : "You were invited to an organization. Create an account with the invited email.") :
      location.pathname === "/zoom/connect" ? "Sign in to finish connecting your Zoom account." :
        "AI meeting minutes in your organization's own format.";
  const ssoNext = inviteToken ? "?next=" + encodeURIComponent("/invite/" + inviteToken)
    : location.pathname === "/connect" ? "?next=" + encodeURIComponent("/connect" + location.search) : "";

  return (
    <AuthCard title={title} sub={sub}>
      {mode !== "forgot" && sso.providers.length > 0 && (
        <>
          <div className="stack">
            {sso.providers.map((p) => (
              <a key={p.id} className="btn" style={{ justifyContent: "center" }} href={"/api/auth/sso/" + p.id + "/start" + ssoNext}>
                Continue with {p.label}
              </a>
            ))}
          </div>
          <p className="sub" style={{ margin: 0, textAlign: "center" }}>By continuing, you confirm you are 13 or older and agree to the <Link to="/terms">Terms of use</Link> and <Link to="/privacy">Privacy policy</Link>.</p>
          <div className="divider">or</div>
        </>
      )}
      <form className="stack" onSubmit={submit}>
        {mode === "signup" && (
          <>
            {!personalInvite && !inviteToken && sso.personal && (
              <div className="stack" style={{ gap: 6 }}>
                <span className="lbl" style={{ margin: 0 }}>I will use Live Minutes for</span>
                <div className="type-grid" role="radiogroup" aria-label="How you will use Live Minutes">
                  {USES.map((u) => (
                    <button key={u.id} type="button" role="radio" aria-checked={use === u.id}
                      className={"type-card" + (use === u.id ? " on" : "")}
                      onClick={() => { setUse(u.id); setAccountType(u.id === "personal" ? "personal" : ""); }}>
                      <strong>{u.label}</strong>
                      <span>{u.hint}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {!personalInvite && (use === "school" || inviteToken || !sso.personal) && (
              <div className="stack" style={{ gap: 6 }}>
                <span className="lbl" style={{ margin: 0 }}>I am</span>
                <AccountTypePicker value={accountType} onChange={setAccountType} />
              </div>
            )}
            <label>Name<input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></label>
          </>
        )}
        <label>Email
          <input type="email" required maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)}
            autoComplete="email" />
        </label>
        {mode === "signup" && !inviteToken && use === "personal" && (
          <p className="sub" style={{ margin: 0 }}>Any email works. Your private workspace is ready as soon as you confirm it.</p>
        )}
        {mode === "signup" && !inviteToken && use !== "personal" && (
          <p className="sub" style={{ margin: 0 }}>A personal email is fine. You verify your school email later, when you join or create an organization.</p>
        )}
        {mode !== "forgot" && (
          <label>Password
            <input type="password" required minLength={mode === "signup" ? 12 : 1} maxLength={256} value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"} />
          </label>
        )}
        {mode === "signup" && <PasswordRules password={password} email={email} name={name} />}
        {mode === "signup" && (
          <label className="row" style={{ textTransform: "none", letterSpacing: "normal", alignItems: "flex-start" }}>
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} required style={{ marginTop: 4 }} />
            <span>I am 13 or older, and I agree to the <Link to="/terms" target="_blank">Terms of use</Link> and the <Link to="/privacy" target="_blank">Privacy policy</Link>.</span>
          </label>
        )}
        {notice && mode === "login" && <div className="alert ok" role="status">{notice}</div>}
        <Turnstile siteKey={sso.turnstile_site_key} action={mode === "signup" ? "signup" : mode === "forgot" ? "forgot" : "login"} onToken={onToken} resetKey={resetCaptcha} />
        <ErrorBox error={error} />
        <button className="primary" style={{ justifyContent: "center" }}
          disabled={busy || (!!sso.turnstile_site_key && !captcha) || (mode === "signup" && (!passwordOk(password, email, name) || !accountType || !agree))}>
          {busy ? "Please wait…" : mode === "login" ? "Sign in" : mode === "signup" ? "Create account" : "Send reset link"}
        </button>
      </form>
      {mode === "login" && sso.mail && (
        <p className="sub" style={{ textAlign: "center", margin: 0 }}>
          <button className="link" onClick={() => go("forgot")}>Forgot your password?</button>
        </p>
      )}
      {mode === "forgot" && (
        <p className="sub" style={{ textAlign: "center", margin: 0 }}>
          <button className="link" onClick={() => go("login")}>Back to sign in</button>
        </p>
      )}
      {mode !== "forgot" && (sso.signup || inviteToken) && (
        <p className="sub" style={{ textAlign: "center", margin: 0 }}>
          {mode === "login" ? "New here? " : "Already have an account? "}
          <button className="link" onClick={() => go(mode === "login" ? "signup" : "login")}>
            {mode === "login" ? "Create an account" : "Sign in"}
          </button>
        </p>
      )}
      {mode === "login" && desktopApp && (
        <p className="sub" style={{ textAlign: "center", margin: 0 }}>
          New to the desktop app?{" "}
          <button className="link" onClick={() => location.assign("/desktop/tour")}>Take the welcome tour</button>
        </p>
      )}
    </AuthCard>
  );
}
