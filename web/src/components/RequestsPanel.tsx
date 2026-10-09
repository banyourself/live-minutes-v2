import { useState } from "react";
import { api } from "../api";
import { ErrorBox, errText, fmtDate, useLoad } from "../ui";
import { typeLabel } from "./AccountType";

export interface CreationRequest {
  id: string; kind: "org" | "school" | "district"; status: string; district: string; district_id: string | null;
  school: string; school_id: string | null; org: string; school_email: string; domain: string; user: string; name: string;
  account_type: string; note: string; created_at: number; possible_duplicates: { id: string; name: string }[];
  college: { name: string; domains: string[]; email_matches: boolean } | null;
}

interface Option { id: string; name: string; district_id?: string }

const KIND: Record<string, string> = { org: "New organization", school: "New college", district: "New district" };

export default function RequestsPanel({ listUrl, actionBase, districts = [], schools = [], title = "New requests" }: {
  listUrl: string; actionBase: string; districts?: Option[]; schools?: Option[]; title?: string;
}) {
  const list = useLoad(() => api.get<{ requests: CreationRequest[] }>(listUrl), [listUrl]);
  const [map, setMap] = useState<Record<string, string>>({});
  const [domains, setDomains] = useState<Record<string, string>>({});
  const [conflict, setConflict] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const rows = list.data?.requests || [];
  const pending = rows.filter((r) => r.status === "pending");
  const decided = rows.filter((r) => r.status !== "pending").slice(0, 15);

  async function approve(r: CreationRequest, allowDuplicate = false) {
    setMsg(""); setError("");
    const target = map[r.id] || "";
    const body: Record<string, unknown> = { allow_duplicate: allowDuplicate };
    if (target.startsWith("d:")) body.district_id = target.slice(2);
    if (target.startsWith("s:")) body.school_id = target.slice(2);
    if (r.kind !== "org" && !target.startsWith("s:")) body.domains = (domains[r.id] ?? r.domain).split(/[\s,]+/).filter(Boolean);
    try {
      await api.post(actionBase + "/" + r.id + "/approve", body);
      setConflict({ ...conflict, [r.id]: "" });
      setMsg("Approved. " + r.org + " is set up and " + (r.name || r.user) + " is its owner.");
      await list.reload();
    } catch (e) {
      const text = errText(e);
      if (/looks like/.test(text)) setConflict({ ...conflict, [r.id]: text });
      else setError(text);
    }
  }

  async function reject(r: CreationRequest) {
    const note = prompt("Reason to send to " + (r.name || r.user) + " (optional)");
    if (note === null) return;
    setMsg(""); setError("");
    try {
      await api.post(actionBase + "/" + r.id + "/reject", { note });
      setMsg("Rejected.");
      await list.reload();
    } catch (e) {
      setError(errText(e));
    }
  }

  return (
    <div className="card stack">
      <h2>{title}</h2>
      <p className="sub" style={{ margin: 0 }}>Nothing new appears in the lists until someone approves it here, so there is only one official version of each district, college, and organization.</p>
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error || list.error} />
      {pending.length === 0 && <p className="sub">Nothing waiting.</p>}
      {pending.map((r) => {
        const sameDistrict = schools.filter((s) => !r.district_id || s.district_id === r.district_id);
        return (
          <div key={r.id} className="stack request-row">
            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <span className="chip accent">{KIND[r.kind]}</span>{" "}
                <strong>{r.org}</strong> at {r.school}{r.kind !== "org" ? ", " + r.district : ""}
                <div className="sub">{r.name || r.user} ({r.user}, {typeLabel(r.account_type)}){r.school_email ? " confirmed " + r.school_email : ""} · {fmtDate(r.created_at)}</div>
              </div>
            </div>
            {r.possible_duplicates.length > 0 && (
              <div className="alert warn">Looks like {r.possible_duplicates.map((d) => d.name).join(" or ")}, which already exists. {r.kind === "org"
                ? "If it is the same group, reject this and ask them to request to join it."
                : "If it is the same, choose it below instead of creating a second one."}</div>
            )}
            {conflict[r.id] && <div className="alert bad">{conflict[r.id]}</div>}
            {r.college && (
              <div className={"alert " + (r.college.email_matches ? "ok" : "warn")}>
                A public list of colleges has {r.college.name} with {r.college.domains.map((d) => "@" + d).join(", ")}.{" "}
                {r.college.email_matches ? "The confirmed email matches." : "The confirmed email does not match, so check this request carefully."}
                {r.kind !== "org" && !(map[r.id] || "").startsWith("s:") && (
                  <> <button type="button" className="link" onClick={() => setDomains({ ...domains, [r.id]: r.college!.domains.join(", ") })}>Use these domains</button></>
                )}
              </div>
            )}
            {r.kind !== "org" && (
              <div className="row wrap">
                <select value={map[r.id] || ""} onChange={(e) => setMap({ ...map, [r.id]: e.target.value })}>
                  <option value="">{r.kind === "district" ? "Create the new district and college" : "Create the new college"}</option>
                  {r.kind === "district" && districts.map((d) => <option key={d.id} value={"d:" + d.id}>Use existing district: {d.name}</option>)}
                  {sameDistrict.map((s) => <option key={s.id} value={"s:" + s.id}>Use existing college: {s.name}</option>)}
                </select>
                {!(map[r.id] || "").startsWith("s:") && (
                  <input style={{ flex: 1, minWidth: 220 }} value={domains[r.id] ?? r.domain} onChange={(e) => setDomains({ ...domains, [r.id]: e.target.value })}
                    placeholder="Email domains for the new college" />
                )}
              </div>
            )}
            <div className="row">
              <button className="primary" onClick={() => void approve(r)}>Approve</button>
              {conflict[r.id] && <button onClick={() => void approve(r, true)}>It is different, approve anyway</button>}
              <button className="danger" onClick={() => void reject(r)}>Reject</button>
            </div>
          </div>
        );
      })}
      {decided.length > 0 && (
        <details>
          <summary className="sub">Recent decisions</summary>
          <table><tbody>
            {decided.map((r) => <tr key={r.id}><td>{KIND[r.kind]}: {r.org} at {r.school}</td><td>{r.user}</td><td>{r.status}</td><td>{fmtDate(r.created_at)}</td></tr>)}
          </tbody></table>
        </details>
      )}
    </div>
  );
}
