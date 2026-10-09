import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Org } from "../api";
import { emailWord, expectedDomains } from "../components/AccountType";
import { useSession } from "../session";
import { ErrorBox, errText, fmtDate, useLoad } from "../ui";

interface DirOrg { id: string; name: string; my_role: string | null; pending: boolean }
interface DirSchool { id: string; name: string; domains: string[]; staff_domains: string[]; orgs: DirOrg[] }
interface Match { id: string; name: string }

function useMatches(kind: string, name: string, parent: string, enabled: boolean) {
  const [matches, setMatches] = useState<Match[]>([]);
  useEffect(() => {
    if (!enabled || name.trim().length < 2) { setMatches([]); return; }
    const t = setTimeout(() => {
      api.get<{ matches: Match[] }>("/api/directory/suggest?kind=" + kind + "&name=" + encodeURIComponent(name) + "&parent_id=" + parent)
        .then((r) => setMatches(r.matches)).catch(() => setMatches([]));
    }, 350);
    return () => clearTimeout(t);
  }, [kind, name, parent, enabled]);
  return matches;
}
interface College { name: string; domains: string[] }
function useColleges(name: string) {
  const [found, setFound] = useState<College[]>([]);
  useEffect(() => {
    if (name.trim().length < 3) { setFound([]); return; }
    const t = setTimeout(() => {
      api.get<{ matches: College[] }>("/api/directory/colleges?q=" + encodeURIComponent(name))
        .then((r) => setFound(r.matches)).catch(() => setFound([]));
    }, 300);
    return () => clearTimeout(t);
  }, [name]);
  return found;
}
function CollegeName({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const found = useColleges(value);
  const exact = found.find((c) => c.name.toLowerCase() === value.trim().toLowerCase());
  return (
    <label>College name
      <input value={value} onChange={(e) => onChange(e.target.value)} maxLength={200} list="college-names" autoComplete="off" />
      <datalist id="college-names">{found.map((c) => <option key={c.name} value={c.name} />)}</datalist>
      <span className="hint">{exact ? "Student and staff emails there usually end in " + exact.domains.map((d) => "@" + d).join(" or ") + "."
        : "Start typing to pick the official name from a public list of colleges."}</span>
    </label>
  );
}
interface DirDistrict { id: string; name: string; schools: DirSchool[] }
interface SchoolEmail { id: string; email: string; domain: string; verified: boolean }
interface MyRequests {
  joins: { id: string; org: string; school: string; status: string; created_at: number }[];
  schools: { id: string; kind: string; school: string; district: string; org: string; status: string; note: string; created_at: number }[];
}

const OTHER = "__other";

export default function Onboarding({ first = false }: { first?: boolean }) {
  const { me, refresh, setOrgId, logout } = useSession();
  const navigate = useNavigate();
  const dir = useLoad(() => api.get<{ districts: DirDistrict[] }>("/api/directory"), []);
  const mine = useLoad(() => api.get<{ emails: SchoolEmail[] }>("/api/me/school-emails"), []);
  const reqs = useLoad(() => api.get<MyRequests>("/api/me/requests"), []);
  const [districtId, setDistrictId] = useState("");
  const [districtName, setDistrictName] = useState("");
  const [schoolId, setSchoolId] = useState("");
  const [schoolName, setSchoolName] = useState("");
  const [orgId, setOrgChoice] = useState("");
  const [orgName, setOrgName] = useState("");
  const [schoolEmail, setSchoolEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");

  const districts = dir.data?.districts || [];
  const district = districts.find((d) => d.id === districtId);
  const school = district?.schools.find((s) => s.id === schoolId);
  const otherDistrict = districtId === OTHER;
  const otherSchool = otherDistrict || schoolId === OTHER;
  const newOrg = otherSchool || orgId === OTHER;
  const verifiedList = (mine.data?.emails || []).filter((e) => e.verified);
  const kind = me?.user.account_type || "student";
  const allowed = school ? expectedDomains(school.domains, school.staff_domains || [], kind) : [];
  const proof = useMemo(() => {
    if (school) return verifiedList.find((e) => allowed.includes(e.domain));
    return verifiedList.find((e) => e.email === schoolEmail.trim().toLowerCase());
  }, [school, verifiedList, schoolEmail, allowed]);
  const admin = !!me?.user.is_platform_admin;
  const itHere = !!school && !!me?.user.admin_scopes.some((s) => (s.scope === "school" && s.id === school.id) || (s.scope === "district" && s.id === districtId));
  const districtMatches = useMatches("district", districtName, "", districtId === OTHER);
  const schoolMatches = useMatches("school", schoolName, districtId, schoolId === OTHER && districtId !== OTHER && !!districtId);
  const orgMatches = useMatches("org", orgName, schoolId, orgId === OTHER && !!school);
  const chosenOrg = school?.orgs.find((o) => o.id === orgId);
  const already = chosenOrg?.my_role || "";
  const waiting = !!chosenOrg?.pending;

  useEffect(() => { setSchoolId(""); setOrgChoice(""); setSent(false); }, [districtId]);
  useEffect(() => { setOrgChoice(""); setSent(false); }, [schoolId]);

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy("");
    }
  }

  const makeWorkspace = () => run("workspace", async () => {
    await api.post("/api/auth/personal-workspace");
    await refresh();
    navigate("/dashboard");
  });

  const sendCode = () => run("send", async () => {
    const r = await api.post<{ status: string }>("/api/school-emails", { email: schoolEmail, school_id: school?.id || "" });
    if (r.status === "verified") {
      await mine.reload();
      setNotice("That school email is already verified on your account.");
    } else {
      setSent(true);
      setNotice("We sent a 6-digit code to " + schoolEmail.trim() + ". It works for 10 minutes.");
    }
  });

  const confirmCode = () => run("confirm", async () => {
    await api.post("/api/school-emails/confirm", { email: schoolEmail, code });
    setCode("");
    setSent(false);
    await mine.reload();
    setNotice("School email verified.");
  });

  const finish = () => run("finish", async () => {
    if (!newOrg && orgId) {
      await api.post("/api/orgs/" + orgId + "/join-requests", { message });
      await reqs.reload();
      setNotice("Request sent. An owner of that organization will approve it, and you'll get an email.");
      return;
    }
    if (otherSchool) {
      await api.post("/api/school-requests", {
        district_id: otherDistrict ? "" : districtId, district_name: otherDistrict ? districtName : "",
        school_name: schoolName, org_name: orgName, school_email: proof?.email || schoolEmail
      });
      await reqs.reload();
      setNotice("Sent for review. Once it is approved, the organization is created with you as its owner.");
      setDistrictId("");
      return;
    }
    const org = await api.post<Org & { status: string }>("/api/orgs", { school_id: schoolId, name: orgName });
    if (org.status === "pending") {
      await reqs.reload();
      setNotice("Sent to " + school!.name + "'s IT staff for approval. Once approved, " + orgName + " is created with you as its owner.");
      setOrgChoice("");
      setOrgName("");
      return;
    }
    setOrgId(org.id);
    await refresh();
    navigate("/settings");
  });

  function open(id: string) {
    setOrgId(id);
    navigate("/dashboard");
  }

  const pending = [...(reqs.data?.joins || []).map((j) => ({ key: "j" + j.id, id: j.id, kind: "join", text: "Join " + j.org + (j.school ? " at " + j.school : ""), status: j.status, at: j.created_at, note: "" })),
    ...(reqs.data?.schools || []).map((s) => ({ key: "s" + s.id, id: s.id, kind: "school", text: "New " + (s.kind === "org" ? "organization " : s.kind === "school" ? "college " : "district ") + s.org + " at " + s.school + (s.kind === "org" ? "" : ", " + s.district), status: s.status, at: s.created_at, note: s.note }))];

  const word = emailWord(kind);
  const emailHint = school
    ? (allowed.length ? "Use your " + school.name + " " + word + " email, ending in " + allowed.map((d) => "@" + d).join(" or ") + "."
      : school.name + " has no " + word + " email domains set up yet. Ask its IT staff or the platform owner.")
    : "Use the " + word + " email address your college gave you.";
  const ready = otherDistrict ? districtName.trim().length > 1 : !!districtId && !!schoolId;
  const orgReady = newOrg ? orgName.trim().length > 1 && (!otherSchool || schoolName.trim().length > 1) : !!orgId;
  const verified = !!proof || ((admin || itHere) && !otherSchool);
  const action = !newOrg ? (orgId ? "Request to join" : "Continue") : otherSchool ? "Submit for approval"
    : admin || itHere ? "Create organization" : "Request this organization";

  return (
    <div className="card stack" style={{ maxWidth: 620 }}>
      <div>
        <div className="kicker">New records file</div>
        <h1>{first ? "Set up your organization" : "Join or create an organization"}</h1>
        <p className="sub">Pick your school, then confirm your school email. Your sign-in email can stay personal.</p>
      </div>

      {kind === "personal" && !me?.orgs.some((o) => o.personal) && (
        <div className="stack">
          <h2>Your personal workspace</h2>
          <p className="sub" style={{ margin: 0 }}>A private workspace for your own meetings, with no school or organization needed.</p>
          <div className="row"><button className="primary" disabled={!!busy} onClick={() => void makeWorkspace()}>
            {busy === "workspace" ? "Creating…" : "Create my workspace"}</button></div>
        </div>
      )}

      {(me?.orgs.length || 0) > 0 && (
        <div className="stack">
          <h2>Your organizations</h2>
          {me!.orgs.map((o) => (
            <div key={o.id} className="row" style={{ justifyContent: "space-between" }}>
              <span>{o.name}<span className="sub"> · {o.school ? o.school + " · " : ""}{o.district} · {o.role}</span></span>
              <button onClick={() => open(o.id)}>Open</button>
            </div>
          ))}
          <p className="sub" style={{ margin: 0 }}>To join another organization or start a new one, pick it below.</p>
        </div>
      )}

      {pending.length > 0 && (
        <div className="stack">
          <h2>Your requests</h2>
          {pending.map((p) => (
            <div key={p.key} className="row" style={{ justifyContent: "space-between" }}>
              <span>{p.text}<span className="sub"> · {fmtDate(p.at)}{p.note ? " · " + p.note : ""}</span></span>
              <span className="row">
                <span className={"stamp" + (p.status === "approved" ? " ok" : p.status === "pending" ? " live" : "")}>{p.status}</span>
                {p.kind === "join" && p.status === "pending" && (
                  <button onClick={() => void run("cancel", async () => { await api.del("/api/me/join-requests/" + p.id); await reqs.reload(); })}>Cancel</button>
                )}
              </span>
            </div>
          ))}
        </div>
      )}

      <ErrorBox error={dir.error} />
      <label>School district
        <select value={districtId} onChange={(e) => setDistrictId(e.target.value)}>
          <option value="">Choose your district</option>
          {districts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          <option value={OTHER}>Other (request a new district)</option>
        </select>
      </label>
      {otherDistrict && (
        <>
          <label>District name<input value={districtName} onChange={(e) => setDistrictName(e.target.value)} maxLength={200}
            placeholder="Full name of your school district" /></label>
          {districtMatches.length > 0 && (
            <div className="hint-match">Did you mean
              {districtMatches.map((m) => <button key={m.id} type="button" className="link" onClick={() => setDistrictId(m.id)}>{m.name}</button>)}
              <span>? Pick it so there is only one official district.</span></div>
          )}
        </>
      )}

      {districtId && (
        otherDistrict ? (
          <CollegeName value={schoolName} onChange={setSchoolName} />
        ) : (
          <>
            <label>College
              <select value={schoolId} onChange={(e) => setSchoolId(e.target.value)}>
                <option value="">Choose your college</option>
                {district?.schools.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                <option value={OTHER}>Other (request a new college)</option>
              </select>
            </label>
            {schoolId === OTHER && (
              <>
                <CollegeName value={schoolName} onChange={setSchoolName} />
                {schoolMatches.length > 0 && (
                  <div className="hint-match">Did you mean
                    {schoolMatches.map((m) => <button key={m.id} type="button" className="link" onClick={() => setSchoolId(m.id)}>{m.name}</button>)}
              <span>? Pick it so there is only one official college.</span></div>
                )}
              </>
            )}
          </>
        )
      )}

      {ready && (
        otherSchool ? (
          <label>Organization<input value={orgName} onChange={(e) => setOrgName(e.target.value)} maxLength={200}
            placeholder="Associated Student Government" /></label>
        ) : (
          <>
            <label>Organization
              <select value={orgId} onChange={(e) => setOrgChoice(e.target.value)}>
                <option value="">Choose your organization</option>
                {school?.orgs.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}{o.my_role ? " (you're " + (o.my_role === "owner" ? "have full access" : o.my_role === "viewer" ? "read only" : "a " + o.my_role) + ")" : o.pending ? " (request pending)" : ""}
                  </option>
                ))}
                <option value={OTHER}>Other (request a new organization)</option>
              </select>
            </label>
            {orgId === OTHER && (
              <>
                <label>New organization name<input value={orgName} onChange={(e) => setOrgName(e.target.value)} maxLength={200}
                  placeholder="Associated Student Government" /></label>
                {orgMatches.length > 0 && (
                  <div className="hint-match">Did you mean
                    {orgMatches.map((m) => <button key={m.id} type="button" className="link" onClick={() => setOrgChoice(m.id)}>{m.name}</button>)}
              <span>? Pick it so there is only one official organization.</span></div>
                )}
              </>
            )}
          </>
        )
      )}

      {already && (
        <div className="stack">
          <div className="alert ok" role="status">You're already in {chosenOrg!.name} as {already === "owner" ? "the owner" : "a " + already}.</div>
          <div className="row"><button className="primary" onClick={() => open(chosenOrg!.id)}>Open {chosenOrg!.name}</button></div>
        </div>
      )}
      {!already && waiting && <div className="alert ok" role="status">Your request to join {chosenOrg!.name} is waiting for an owner to approve it.</div>}

      {ready && orgReady && !already && !waiting && (
        <div className="stack">
          <h2>Verify your school email</h2>
          {proof ? (
            <div className="alert ok" role="status">Verified: {proof.email}</div>
          ) : (
            <>
              <p className="sub" style={{ margin: 0 }}>{emailHint}{(admin || itHere) && !otherSchool ? " You manage this college, so you may skip this." : ""}</p>
              <div className="row">
                <input type="email" style={{ flex: 1 }} value={schoolEmail} maxLength={254} onChange={(e) => { setSchoolEmail(e.target.value); setSent(false); }}
                  placeholder={school ? "name@" + school.domains[0] : "name@yourschool.edu"} autoComplete="off" />
                <button disabled={!schoolEmail.includes("@") || busy === "send"} onClick={() => void sendCode()}>
                  {sent ? "Send again" : "Send code"}
                </button>
              </div>
              {sent && (
                <div className="row">
                  <input inputMode="numeric" pattern="[0-9]*" maxLength={6} style={{ maxWidth: 160, letterSpacing: "0.3em" }}
                    value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="123456" />
                  <button className="primary" disabled={code.length !== 6 || busy === "confirm"} onClick={() => void confirmCode()}>Verify</button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {ready && orgReady && !newOrg && !already && !waiting && (
        <label>Note to the owners (optional)
          <input value={message} onChange={(e) => setMessage(e.target.value)} maxLength={500} placeholder="I'm the new secretary" />
        </label>
      )}

      {notice && <div className="alert ok" role="status">{notice}</div>}
      <ErrorBox error={error} />
      <div className="row">
        {!already && !waiting && (
          <button className="primary" disabled={!ready || !orgReady || !verified || !!busy} onClick={() => void finish()}>
            {busy === "finish" ? "Working…" : action}
          </button>
        )}
        {first && <button type="button" onClick={() => void logout()}>Sign out</button>}
      </div>
    </div>
  );
}
