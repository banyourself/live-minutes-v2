import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import AccountTypePicker, { typeLabel } from "../components/AccountType";
import { AddAiForm, ConnList, TaskPanel } from "../components/AiPanels";
import PasswordRules, { passwordOk } from "../components/PasswordRules";
import type { AIConn } from "../api";
import { useSession } from "../session";
import { ErrorBox, errText, fmtDate, useLoad } from "../ui";
import { AuthCard } from "./Login";
import { SessionsCard, TwoStepCard } from "../components/Security";
import { SudoProvider } from "./admin/sudo";
import { NotificationSettings } from "./Notifications";

function tokenFrom(prefix: string) {
  return location.pathname.split(prefix)[1]?.split(/[?#/]/)[0] || "";
}

export function Verify() {
  const { refresh } = useSession();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [ask, setAsk] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const started = useRef(false);

  async function confirmWith(pw: string) {
    setBusy(true);
    setError("");
    try {
      await api.post("/api/auth/verify", { token: tokenFrom("/verify/"), password: pw });
      await refresh();
      navigate("/dashboard", { replace: true });
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        if (pw) setError("that password is not right");
        setAsk(true);
      } else {
        setError(errText(e));
      }
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void confirmWith("");
  });

  if (ask) {
    return (
      <AuthCard title="Confirm your email" sub="Enter the password you chose when you signed up. This makes sure the account is yours.">
        <form className="stack" onSubmit={(e) => { e.preventDefault(); void confirmWith(password); }}>
          <label>Password
            <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </label>
          <ErrorBox error={error} />
          <button className="primary" disabled={busy || !password}>{busy ? "Confirming…" : "Confirm email"}</button>
        </form>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Confirming your email" sub={error ? undefined : "One moment…"}>
      <ErrorBox error={error} />
      {error && <button onClick={() => navigate("/dashboard", { replace: true })}>Continue</button>}
    </AuthCard>
  );
}

export function Reset() {
  const { refresh } = useSession();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setError("the two passwords do not match");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const r = await api.post<{ status?: string }>("/api/auth/reset", { token: tokenFrom("/reset/"), password });
      if (r.status === "sign_in") {
        location.replace("/login?reset=1");
        return;
      }
      await refresh();
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Choose a new password" sub="This signs you out on every other device.">
      <form className="stack" onSubmit={submit}>
        <label>New password
          <input type="password" required minLength={12} maxLength={256} value={password}
            onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
        </label>
        <PasswordRules password={password} />
        <label>Type it again
          <input type="password" required minLength={12} maxLength={256} value={confirm}
            onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
        </label>
        <ErrorBox error={error} />
        <button className="primary" disabled={busy || !passwordOk(password)} style={{ justifyContent: "center" }}>
          {busy ? "Saving…" : "Save password"}
        </button>
      </form>
    </AuthCard>
  );
}

export function ChooseType() {
  const { me, refresh, logout } = useSession();
  const [value, setValue] = useState("");
  const [error, setError] = useState("");

  async function save() {
    setError("");
    try {
      await api.post("/api/auth/account-type", { account_type: value });
      await refresh();
    } catch (e) {
      setError(errText(e));
    }
  }

  return (
    <AuthCard title="Who are you?" sub="This decides which email you confirm with your college and what you can do here. You can change it later under My account.">
      <AccountTypePicker value={value} onChange={setValue} personal={!!me?.user.personal_open || !!me?.orgs.some((o) => o.personal)} />
      <ErrorBox error={error} />
      <div className="row">
        <button className="primary" disabled={!value} onClick={() => void save()}>Continue</button>
        <button onClick={() => void logout()}>Sign out</button>
      </div>
    </AuthCard>
  );
}

function TypeSettings({ tick }: { tick: number }) {
  const { me, refresh } = useSession();
  const [value, setValue] = useState(me!.user.account_type);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const options = useLoad(() => api.get<{ allowed: string[]; needs: Record<string, string> }>("/api/auth/account-type"), [tick, me!.user.account_type]);
  const losing = me!.user.admin_scopes.length > 0 && !["staff", "it"].includes(value);
  const needs = value !== me!.user.account_type && options.data && !options.data.allowed.includes(value) ? options.data.needs[value] : "";

  async function save() {
    setMsg(""); setError("");
    if (losing && !confirm("Switching to " + typeLabel(value) + " removes your IT roles. Continue?")) return;
    try {
      await api.post("/api/auth/account-type", { account_type: value });
      await refresh();
      setMsg("Saved.");
    } catch (e) {
      setError(errText(e));
    }
  }

  return (
    <div className="card stack">
      <h2>Account type</h2>
      <p className="sub" style={{ margin: 0 }}>Currently {typeLabel(me!.user.account_type)}. Students confirm a student email; faculty, staff, and IT confirm a work email. Only Staff and IT can hold IT roles. Personal accounts get their own private workspace.</p>
      <AccountTypePicker value={value} onChange={setValue} personal={!!me!.user.personal_open || me!.user.account_type === "personal" || me!.orgs.some((o) => o.personal)} />
      {losing && <div className="alert warn">Switching away from Staff or IT removes your IT roles.</div>}
      {needs && <div className="alert">To switch to {typeLabel(value)}, first confirm your {needs} email from your college under School and
        work emails. Then press Save. Your account type stays {typeLabel(me!.user.account_type)} until then.</div>}
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error} />
      <div className="row"><button className="primary" disabled={value === me!.user.account_type || !!needs} onClick={() => void save()}>Save</button></div>
    </div>
  );
}

export function VerifyPending() {
  const { me, logout } = useSession();
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function resend() {
    setError("");
    setMsg("");
    try {
      await api.post("/api/auth/verify/resend");
      setMsg("A new link is on its way to " + me!.user.email + ".");
    } catch (e) {
      setError(errText(e));
    }
  }

  return (
    <AuthCard title="Confirm your email" sub={"Open the link we sent to " + me!.user.email + " to finish setting up your account."}>
      <ErrorBox error={error} />
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <div className="row">
        <button className="primary" onClick={() => void resend()}>Send a new link</button>
        <button onClick={() => void logout()}>Sign out</button>
      </div>
    </AuthCard>
  );
}

const ACCOUNT_TABS: [string, string][] = [["profile", "Profile"], ["security", "Security"], ["notifications", "Notifications and calendar"], ["ai", "AI"]];

export function AccountSettings() {
  const { me, logout } = useSession();
  const [params, setParams] = useSearchParams();
  const asked = params.get("tab") || (params.has("openrouter") || params.has("openrouter_error") ? "ai" : "");
  const tab = ACCOUNT_TABS.some(([k]) => k === asked) ? asked : "profile";
  const [proofs, setProofs] = useState(0);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function change(e: FormEvent) {
    e.preventDefault();
    setError("");
    setMsg("");
    try {
      await api.post("/api/auth/password", { current, new: next });
      setCurrent("");
      setNext("");
      setMsg("Password changed. Other devices and connected apps were signed out.");
    } catch (err) {
      setError(errText(err));
    }
  }

  async function emailLink() {
    setError("");
    setMsg("");
    try {
      await api.post("/api/auth/password-link");
      setMsg("Check your email for a link to set your password. It works for 10 minutes.");
    } catch (err) {
      setError(errText(err));
    }
  }

  async function everywhere() {
    if (!confirm("Sign out on every computer and phone, including this one?")) return;
    setError("");
    try {
      await api.post("/api/auth/logout-all");
      await logout().catch(() => undefined);
      location.href = "/";
    } catch (err) {
      setError(errText(err));
    }
  }

  return (
    <>
    <div className="page-head">
      <div>
        <div className="kicker">Your account</div>
        <h1>My account</h1>
        <p className="sub">{me!.user.name ? me!.user.name + " · " : ""}{me!.user.email}</p>
      </div>
    </div>
    <div className="tabs" role="group" aria-label="Account sections">
      {ACCOUNT_TABS.map(([k, label]) => <button key={k} className={tab === k ? "on" : ""} aria-pressed={tab === k}
        onClick={() => setParams({ tab: k }, { replace: true })}>{label}</button>)}
    </div>
    {tab === "notifications" && <div className="grid-2"><NotificationSettings /><CalendarFeed /></div>}
    {tab === "ai" && <div className="grid-2"><MyAi /></div>}
    {tab === "profile" && (
    <div className="grid-2">
      <TypeSettings tick={proofs} />
      <SchoolEmails onChange={() => setProofs((n) => n + 1)} />
    </div>
    )}
    {tab === "security" && (
    <SudoProvider>
    <div className="grid-2">
      {!me!.user.has_password ? (
        <div className="card stack">
          <h2>Set a password</h2>
          <p className="sub">Signed in as {me!.user.email} with school sign-in. To add a password, we email you a link so only you can set it.</p>
          <ErrorBox error={error} />
          {msg && <div className="alert ok" role="status">{msg}</div>}
          <div className="row"><button className="primary" onClick={() => void emailLink()}>Email me a link</button></div>
        </div>
      ) : (
        <form className="card stack" onSubmit={change}>
          <h2>Change password</h2>
          <p className="sub">Signed in as {me!.user.email}.</p>
          <label>Current password
            <input type="password" required value={current} onChange={(e) => setCurrent(e.target.value)}
              autoComplete="current-password" />
          </label>
          <label>New password
            <input type="password" required minLength={12} maxLength={256} value={next}
              onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
          </label>
          <PasswordRules password={next} email={me!.user.email} name={me!.user.name} />
          <ErrorBox error={error} />
          {msg && <div className="alert ok" role="status">{msg}</div>}
          <div className="row"><button className="primary" disabled={!passwordOk(next, me!.user.email, me!.user.name)}>Save password</button></div>
        </form>
      )}
      <TwoStepCard />
      <SessionsCard onEverywhere={() => void everywhere()} />
    </div>
    </SudoProvider>
    )}
    </>
  );
}

interface SchoolEmail { id: string; email: string; domain: string; verified: boolean }

function SchoolEmails({ onChange }: { onChange: () => void }) {
  const list = useLoad(() => api.get<{ emails: SchoolEmail[] }>("/api/me/school-emails"), []);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function run(fn: () => Promise<unknown>, done: string) {
    setMsg(""); setError("");
    try { await fn(); setMsg(done); await list.reload(); onChange(); } catch (e) { setError(errText(e)); }
  }

  return (
    <div className="card stack">
      <h2>School and work emails</h2>
      <p className="sub" style={{ margin: 0 }}>Confirm a student email to join your college's organizations or to switch to Student. Confirm a
        work email to switch to Faculty, Staff, or IT, or if your district gives you an IT role.</p>
      {(list.data?.emails || []).map((e) => (
        <div key={e.id} className="row" style={{ justifyContent: "space-between" }}>
          <span className="mono">{e.email} <span className="sub">{e.verified ? "confirmed" : "not confirmed"}</span></span>
          <button onClick={() => void run(() => api.del("/api/school-emails/" + e.id), "Removed.")}>Remove</button>
        </div>
      ))}
      <div className="row">
        <input type="email" style={{ flex: 1 }} value={email} maxLength={254} onChange={(e) => { setEmail(e.target.value); setSent(""); }} aria-label="School or work email" placeholder="name@college.edu" />
        <button disabled={!email.includes("@")} onClick={() => void run(async () => {
          const r = await api.post<{ status: string }>("/api/school-emails", { email });
          if (r.status !== "verified") setSent(email.trim().toLowerCase());
        }, "If that address can receive mail, a 6-digit code is on its way.")}>Send code</button>
      </div>
      {sent && (
        <div className="row">
          <input inputMode="numeric" maxLength={6} style={{ maxWidth: 160, letterSpacing: "0.3em" }} value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="123456" />
          <button className="primary" disabled={code.length !== 6} onClick={() => void run(async () => {
            await api.post("/api/school-emails/confirm", { email: sent, code });
            setSent(""); setCode(""); setEmail("");
          }, "Email confirmed.")}>Confirm</button>
        </div>
      )}
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error || list.error} />
    </div>
  );
}

function MyAi() {
  const mine = useLoad(() => api.get<{ connections: AIConn[] }>("/api/ai/owned?scope=user"), []);
  return (
    <div className="stack" style={{ gridColumn: "1 / -1" }}>
      <ConnList title="My AIs" connections={mine.data?.connections || []} onChanged={() => void mine.reload()}
        empty="You have not added your own AI. You can still use the AIs your organizations and college share with you." />
      <AddAiForm scope="user" scopeId="" onAdded={() => void mine.reload()} />
      <TaskPanel scope="user" title="My AI choices for each task" />
    </div>
  );
}

function CalendarFeed() {
  const feed = useLoad(() => api.get<{ enabled: boolean; created_at: number | null; last_used_at: number | null }>("/api/me/calendar-feed"), []);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");

  async function make() {
    setError("");
    try {
      setUrl((await api.post<{ url: string }>("/api/me/calendar-feed")).url);
      await feed.reload();
    } catch (e) {
      setError(errText(e));
    }
  }

  async function off() {
    setError("");
    try {
      await api.del("/api/me/calendar-feed");
      setUrl("");
      await feed.reload();
    } catch (e) {
      setError(errText(e));
    }
  }

  return (
    <div className="card stack">
      <h2>Calendar</h2>
      <p className="sub" style={{ margin: 0 }}>Add your organizations' scheduled meetings, with their Zoom links, to Google Calendar, Outlook,
        or Apple Calendar. Paste the link as a calendar subscription ("From URL" or "Subscribe").</p>
      {url ? (
        <>
          <p className="sub" style={{ margin: 0 }}>Copy it now. It is shown only once. Anyone with this link can see your meeting times and Zoom links.</p>
          <div className="token-box mono">{url}</div>
          <div className="row"><button onClick={() => void navigator.clipboard.writeText(url)}>Copy link</button></div>
        </>
      ) : feed.data?.enabled ? (
        <p style={{ margin: 0 }}>Your calendar link is on{feed.data.last_used_at ? ", last read " + fmtDate(feed.data.last_used_at) : ""}.</p>
      ) : null}
      <ErrorBox error={error || feed.error} />
      <div className="row">
        <button className="primary" onClick={() => void make()}>{feed.data?.enabled ? "Make a new link" : "Make a calendar link"}</button>
        {feed.data?.enabled && <button className="danger" onClick={() => void off()}>Turn off</button>}
      </div>
      {feed.data?.enabled && !url && <p className="sub" style={{ margin: 0 }}>Making a new link stops the old one from working.</p>}
    </div>
  );
}
