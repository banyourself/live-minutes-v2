import { lazy, Suspense, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { SessionProvider, useSession } from "./session";
import { can, ROLE_LABEL } from "./api";
import Login, { AuthCard } from "./pages/Login";
import Meetings from "./pages/Meetings";
import Notifications, { useUnread } from "./pages/Notifications";
import { LegalLinks } from "./pages/legal-links";
import AcceptTerms from "./components/AcceptTerms";
import IdleWarning from "./components/IdleWarning";
import FreeAIProgress from "./components/FreeAIProgress";
import Customize from "./components/Customize";
import Icon from "./components/Icon";

const loadMeetingView = () => import("./pages/MeetingView");
const loadNewMeeting = () => import("./pages/NewMeeting");
const loadSettings = () => import("./pages/Settings");
const loadWeek = () => import("./pages/Week");
const loadRecords = () => import("./pages/Records");
const loadLegal = () => import("./pages/Legal");
const loadAccount = () => import("./pages/Account");

const Onboarding = lazy(() => import("./pages/Onboarding"));
const NewMeeting = lazy(loadNewMeeting);
const MeetingView = lazy(loadMeetingView);
const Templates = lazy(() => import("./pages/Templates"));
const FundingPage = lazy(() => loadRecords().then((m) => ({ default: m.FundingPage })));
const SearchPage = lazy(() => loadRecords().then((m) => ({ default: m.SearchPage })));
const VotesPage = lazy(() => loadRecords().then((m) => ({ default: m.VotesPage })));
const Week = lazy(loadWeek);
const UploadMeeting = lazy(() => import("./pages/UploadMeeting"));
const Recordings = lazy(() => import("./pages/Recordings"));
const Privacy = lazy(() => loadLegal().then((m) => ({ default: m.Privacy })));
const Terms = lazy(() => loadLegal().then((m) => ({ default: m.Terms })));
const Accessibility = lazy(() => loadLegal().then((m) => ({ default: m.Accessibility })));
const Support = lazy(() => loadLegal().then((m) => ({ default: m.Support })));
const ZoomHelp = lazy(() => loadLegal().then((m) => ({ default: m.ZoomHelp })));
const ZoomConnect = lazy(() => import("./pages/ZoomConnect"));
const Download = lazy(() => import("./pages/Download"));
const Settings = lazy(loadSettings);
const Invite = lazy(() => import("./pages/Invite"));
const AccountSettings = lazy(() => loadAccount().then((m) => ({ default: m.AccountSettings })));
const ChooseType = lazy(() => loadAccount().then((m) => ({ default: m.ChooseType })));
const Reset = lazy(() => loadAccount().then((m) => ({ default: m.Reset })));
const Verify = lazy(() => loadAccount().then((m) => ({ default: m.Verify })));
const VerifyPending = lazy(() => loadAccount().then((m) => ({ default: m.VerifyPending })));
const Connect = lazy(() => import("./pages/Connect"));
const Assistant = lazy(() => import("./components/Assistant"));
const AdminHome = lazy(() => import("./pages/admin/AdminHome"));
const Console = lazy(() => import("./pages/admin/Console"));
const Archive = lazy(() => import("./pages/Archive"));
const Home = lazy(() => import("./pages/Home"));

const pageLoading = <div className="sub" role="status">Loading…</div>;

const TITLES: [string, string][] = [["/meetings/new", "New meeting"], ["/meetings/", "Meeting"], ["/templates", "Templates"],
  ["/search", "Search"], ["/votes", "Voting record"], ["/recordings", "Recordings"], ["/funding", "Funding requests"], ["/settings", "Settings"],
  ["/account", "My account"], ["/notifications", "Notifications"], ["/week", "This week"], ["/new-org", "Join or add organization"],
  ["/admin", "Platform"], ["/manage", "IT console"], ["/privacy", "Privacy policy"], ["/terms", "Terms of use"],
  ["/accessibility", "Accessibility"], ["/support", "Support"], ["/help/zoom", "Live Minutes for Zoom"], ["/download", "Downloads"],
  ["/dashboard", "Meetings"]];

const HOME_TITLE = "Live Minutes · AI meeting minutes from Zoom captions and transcripts";
const MISSING_PATH = document.querySelector('meta[name="lm-page"]')?.getAttribute("content") === "missing" ? location.pathname : null;
const PUBLIC_TITLES: Record<string, string> = {
  "/": HOME_TITLE, "/login": "Sign in · Live Minutes", "/privacy": "Privacy policy · Live Minutes", "/terms": "Terms of use · Live Minutes",
  "/accessibility": "Accessibility · Live Minutes", "/support": "Support · Live Minutes", "/help/zoom": "Live Minutes for Zoom",
  "/download": "Downloads · Live Minutes", "/dashboard": "Sign in · Live Minutes"
};

export function usePageTitle(signedOut = false) {
  const loc = useLocation();
  useLayoutEffect(() => {
    if (loc.pathname === MISSING_PATH) {
      document.title = "Page not found · Live Minutes";
      return;
    }
    if (signedOut || loc.pathname === "/") {
      if (!loc.pathname.startsWith("/archive/")) document.title = PUBLIC_TITLES[loc.pathname] || "Live Minutes";
      return;
    }
    const hit = TITLES.find(([p]) => loc.pathname.startsWith(p));
    document.title = (hit ? hit[1] + " · " : "") + "Live Minutes";
  }, [loc.pathname, signedOut]);
}

function Item({ to, icon, label, end, count }: { to: string; icon: string; label: string; end?: boolean; count?: number }) {
  return (
    <NavLink to={to} end={end}>
      <Icon name={icon} />
      <span className="nav-label">{label}</span>
      {!!count && <span className="count" aria-label={count + " unread"}>{count > 99 ? "99+" : count}</span>}
    </NavLink>
  );
}

function AccountMenu({ onNavigate }: { onNavigate: () => void }) {
  const { me, org, logout } = useSession();
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  if (!me) return null;
  const staff = me.user.is_platform_admin || me.user.admin_scopes.length > 0;
  const role = me.user.is_platform_admin ? "Platform owner" : org?.personal ? "Personal account" : org ? ROLE_LABEL[org.role] || org.role : staff ? "IT staff" : "";
  const who = me.user.name || me.user.email;
  return (
    <div className="account" ref={box}>
      {open && (
        <div className="account-menu" id="account-menu">
          <div className="account-menu-head">
            <strong>{who}</strong>
            <span className="sub">{me.user.email}</span>
          </div>
          <Link className="menu-item" to="/account" onClick={onNavigate}><Icon name="user" />My account</Link>
          {me.user.account_type !== "personal" && <Link className="menu-item" to="/new-org" onClick={onNavigate}><Icon name="plus" />Join or add organization</Link>}
          <button type="button" className="menu-item" onClick={() => { setOpen(false); setCustom(true); }}><Icon name="palette" />Customize</button>
          <button type="button" className="menu-item" onClick={() => void logout()}><Icon name="out" />Sign out</button>
        </div>
      )}
      <Customize show={custom} onClose={() => { setCustom(false); button.current?.focus(); }} />
      <button ref={button} type="button" className="account-btn" aria-expanded={open} aria-controls="account-menu" onClick={() => setOpen(!open)}>
        <span className="avatar" aria-hidden="true">{who.trim()[0]?.toUpperCase() || "?"}</span>
        <span className="account-text"><strong>{who}</strong><span className="sub">{role}</span></span>
        <Icon name="chevron" size={16} />
      </button>
    </div>
  );
}

function Shell() {
  const { me, org, setOrgId } = useSession();
  const navigate = useNavigate();
  const unread = useUnread();
  const loc = useLocation();
  const [drawer, setDrawer] = useState(false);
  usePageTitle();
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadMeetingView(); void loadNewMeeting(); void loadSettings(); void loadWeek(); void loadRecords();
    }, 2000);
    return () => window.clearTimeout(timer);
  }, []);
  useEffect(() => setDrawer(false), [loc.pathname]);
  if (!me) return null;
  const home = org ? "/dashboard" : me.user.is_platform_admin ? "/admin" : "/manage";
  const admin = me.user.admin_scopes.length > 0 || me.user.is_platform_admin;
  return (
    <div className={"shell" + (drawer ? " drawer-open" : "")}>
      <a className="skip" href="#main">Skip to content</a>
      {!!me.user.idle_hours && <IdleWarning idleHours={me.user.idle_hours} />}
      <header className="topbar">
        <button type="button" className="icon-btn" aria-label={drawer ? "Close menu" : "Open menu"} aria-expanded={drawer}
          aria-controls="side-nav" onClick={() => setDrawer(!drawer)}><Icon name={drawer ? "close" : "menu"} size={22} /></button>
        <Link className="brand brand-small" to={home}><img src="/favicon.svg" alt="" />Live Minutes</Link>
        <Link className="icon-btn" to="/notifications" aria-label={"Notifications" + (unread ? ", " + unread + " unread" : "")}>
          <Icon name="bell" size={22} />{unread > 0 && <span className="dot" aria-hidden="true" />}
        </Link>
      </header>
      {drawer && <div className="drawer-scrim" onClick={() => setDrawer(false)} />}
      <aside className="side" id="side-nav" aria-label="Main">
        <Link className="brand" to={home}><img src="/favicon.svg" alt="" />Live Minutes</Link>
        {!org ? (
          <div className="org-card">
            <strong>No organization</strong>
            <span className="sub">{me.user.is_platform_admin ? "Platform owner" : "IT staff"}</span>
          </div>
        ) : me.orgs.length > 1 ? (
          <label className="org-switch">
            <span className="sr-only">Organization</span>
            <select value={org.id} onChange={(e) => {
              if (e.target.value === "__new") { navigate("/new-org"); return; }
              setOrgId(e.target.value); navigate("/dashboard");
            }}>
              {me.orgs.map((o) => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
              {me.user.account_type !== "personal" && <option value="__new">Join or add organization…</option>}
            </select>
            {org.school && <span className="sub">{org.school}</span>}
            <span className="sub">{org.personal ? "Personal workspace" : org.district}</span>
          </label>
        ) : (
          <div className="org-card">
            <strong>{org.name}</strong>
            {org.school && <span className="sub">{org.school}</span>}
            <span className="sub">{org.personal ? "Personal workspace" : org.district}</span>
          </div>
        )}
        <nav className="nav" aria-label="Pages">
          {org && (
            <>
              <Item to="/dashboard" end icon="meetings" label="Meetings" />
              <Item to="/week" icon="week" label="This week" />
              <Item to="/recordings" icon="recordings" label="Recordings" />
              <div className="nav-group">Records</div>
              <Item to="/search" icon="search" label="Search" />
              {!org.personal && <Item to="/votes" icon="votes" label="Votes" />}
              {!org.personal && can(org.role, "member") && <Item to="/funding" icon="funding" label="Funding" />}
              {can(org.role, "member") && <Item to="/templates" icon="templates" label="Templates" />}
              <div className="nav-group">{org.personal ? "Workspace" : "Organization"}</div>
              <Item to="/settings" icon="settings" label="Settings" />
            </>
          )}
          {admin && <div className="nav-group">Administration</div>}
          {me.user.admin_scopes.length > 0 && <Item to="/manage" icon="shield" label="IT console" />}
          {me.user.is_platform_admin && <Item to="/admin" icon="globe" label="Platform" />}
        </nav>
        <div className="side-foot">
          <nav className="nav" aria-label="You">
            <Item to="/notifications" icon="bell" label="Notifications" count={unread} />
          </nav>
          <AccountMenu onNavigate={() => setDrawer(false)} />
          <div className="side-legal">
            <LegalLinks />
            <span className="credit">Built by <a href="https://kevinle.tech/" target="_blank" rel="noreferrer">Kevin Le</a> · @banyourself</span>
          </div>
        </div>
      </aside>
      <main className="main" id="main" tabIndex={-1}>
        <div className="sheet">
          <div className="punch" aria-hidden="true"><i /><i /><i /></div>
        <Suspense fallback={pageLoading}>
        <Routes>
          {org && <Route path="/dashboard" element={<Meetings />} />}
          {org && <Route path="/meetings/new" element={<NewMeeting />} />}
          {org && <Route path="/meetings/upload" element={<UploadMeeting />} />}
          {org && <Route path="/meetings/:id" element={<MeetingView />} />}
          {org && <Route path="/templates" element={<Templates />} />}
          {org && <Route path="/search" element={<SearchPage />} />}
          {org && <Route path="/votes" element={<VotesPage />} />}
          {org && <Route path="/recordings" element={<Recordings />} />}
          {org && <Route path="/funding" element={<FundingPage />} />}
          {org && <Route path="/settings" element={<Settings />} />}
          <Route path="/account" element={<AccountSettings />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/week" element={<Week />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="/accessibility" element={<Accessibility />} />
          <Route path="/support" element={<Support />} />
          <Route path="/help/zoom" element={<ZoomHelp />} />
          <Route path="/download" element={<Download />} />
          <Route path="/zoom/connect" element={<ZoomConnect />} />
          <Route path="/new-org" element={<Onboarding />} />
          <Route path="/admin" element={me.user.is_platform_admin ? <AdminHome /> : <Navigate to={home} replace />} />
          <Route path="/manage" element={me.user.admin_scopes.length > 0 ? <Console /> : <Navigate to={home} replace />} />
          <Route path="/invite/:token" element={<Invite />} />
          <Route path="*" element={<Navigate to={home} replace />} />
        </Routes>
        </Suspense>
        </div>
      </main>
      <Suspense fallback={null}><Assistant /></Suspense>
      <FreeAIProgress />
    </div>
  );
}

function NotFound({ signedIn }: { signedIn: boolean }) {
  return (
    <AuthCard title="Page not found" sub="This address does not match a page in Live Minutes. The link may be old or mistyped.">
      <div className="row">
        {signedIn ? <Link className="btn primary" to="/dashboard">Go to your meetings</Link>
          : <><Link className="btn primary" to="/">Home page</Link><Link className="btn" to="/login">Sign in</Link></>}
        <Link className="btn" to="/support">Support</Link>
      </div>
    </AuthCard>
  );
}

function Gate() {
  const { me, loading } = useSession();
  const loc = useLocation();
  const corner = <Customize floating />;
  usePageTitle(!me);
  const policy = ({ "/privacy": <Privacy />, "/terms": <Terms />, "/accessibility": <Accessibility />, "/support": <Support />,
    "/help/zoom": <ZoomHelp />, "/download": <Download /> } as Record<string, ReactNode>)[loc.pathname];
  if (loading) return <>{corner}<div className="auth"><div className="sub">Loading…</div></div></>;
  if (loc.pathname === MISSING_PATH) return <>{corner}<NotFound signedIn={!!me} /></>;
  if (loc.pathname === "/") return <Home />;
  if (loc.pathname.startsWith("/archive/")) {
    return <>{corner}<main className="public-page" id="main"><Routes><Route path="/archive/:orgId" element={<Archive />} /></Routes></main></>;
  }
  if (loc.pathname.startsWith("/verify/")) return <>{corner}<Verify /></>;
  if (loc.pathname.startsWith("/reset/")) return <>{corner}<Reset /></>;
  if (policy && (!me || !me.user.verified || !me.user.terms_current)) return <>{corner}<main className="public-page" id="main">{policy}</main></>;
  if (!me) {
    if (loc.pathname.startsWith("/invite/")) return <>{corner}<Invite /></>;
    return <>{corner}<Login /></>;
  }
  if (!me.user.verified) return <>{corner}<VerifyPending /></>;
  if (!me.user.terms_current) return <>{corner}<AcceptTerms /></>;
  if (!me.user.account_type) return <>{corner}<ChooseType /></>;
  if (loc.pathname.startsWith("/invite/")) return <>{corner}<Invite /></>;
  if (loc.pathname === "/connect") return <>{corner}<Connect /></>;
  if (me.orgs.length === 0 && !me.user.is_platform_admin && me.user.admin_scopes.length === 0) {
    return <>{corner}<div className="auth"><Onboarding first /></div></>;
  }
  return <Shell />;
}

export default function App() {
  return (
    <SessionProvider>
      <Suspense fallback={<div className="auth"><div className="sub" role="status">Loading…</div></div>}>
        <Gate />
      </Suspense>
    </SessionProvider>
  );
}
