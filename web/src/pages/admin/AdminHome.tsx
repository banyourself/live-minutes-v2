import { useState } from "react";
import Directory from "../Admin";
import { Activity, Emails, JoinRequests, Overview, Security } from "./Panels";
import { Orgs } from "./Orgs";
import { BillingPanel, ItRoles } from "./Platform";
import { PlatformAi } from "./AiAdmin";
import { ProcurementCard, UsageReport } from "./Reports";
import { SudoProvider } from "./sudo";
import { Users } from "./Users";

const TABS: [string, string][] = [
  ["overview", "Overview"], ["users", "Users"], ["orgs", "Organizations"], ["roles", "IT roles"], ["joins", "Join requests"],
  ["schools", "Schools"], ["ai", "AI"], ["reports", "Reports"], ["billing", "Billing"], ["emails", "Emails"], ["security", "Security"], ["activity", "Activity"]
];

export default function AdminHome() {
  const [tab, setTab] = useState("overview");
  return (
    <SudoProvider>
      <div className="page-head">
        <div>
          <div className="kicker">Platform owner</div>
          <h1>Platform</h1>
          <p className="sub">Every district, college, organization, and person on Live Minutes, plus billing, email, and security.</p>
        </div>
      </div>
      <div className="tabs" role="group" aria-label="Sections">
        {TABS.map(([k, label]) => <button key={k} className={tab === k ? "on" : ""} aria-pressed={tab === k} onClick={() => setTab(k)}>{label}</button>)}
      </div>
      {tab === "overview" && <Overview go={setTab} />}
      {tab === "users" && <Users />}
      {tab === "orgs" && <Orgs />}
      {tab === "roles" && <ItRoles />}
      {tab === "billing" && <BillingPanel />}
      {tab === "ai" && <PlatformAi />}
      {tab === "reports" && <div className="stack"><UsageReport url="/api/admin/reports" title="Usage across the platform" /><ProcurementCard /></div>}
      {tab === "joins" && <JoinRequests />}
      {tab === "schools" && <Directory embedded />}
      {tab === "emails" && <Emails />}
      {tab === "security" && <Security />}
      {tab === "activity" && <Activity />}
    </SudoProvider>
  );
}
