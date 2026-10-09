import { useState } from "react";
import { api } from "../api";
import RequestsPanel from "../components/RequestsPanel";
import { ErrorBox, errText, useLoad } from "../ui";
import { useSudo } from "./admin/sudo";

interface AdminSchool { id: string; name: string; domains: string[]; staff_domains: string[]; active: boolean; org_count: number }
interface AdminDistrict { id: string; name: string; schools: AdminSchool[] }

export default function Admin({ embedded = false }: { embedded?: boolean }) {
  const guard = useSudo();
  const dir = useLoad(() => api.get<{ districts: AdminDistrict[] }>("/api/admin/directory"), []);
  const [mergeInto, setMergeInto] = useState<Record<string, string>>({});
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [staffEdits, setStaffEdits] = useState<Record<string, string>>({});
  const [add, setAdd] = useState({ district_id: "", district_name: "", name: "", domains: "", staff: "" });
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const split = (v: string) => v.split(/[\s,]+/).map((d) => d.trim()).filter(Boolean);

  async function act(fn: () => Promise<unknown>, done: string) {
    setError("");
    setMsg("");
    try {
      await fn();
      setMsg(done);
      await dir.reload();
    } catch (e) {
      if (errText(e) !== "cancelled") setError(errText(e));
    }
  }

  return (
    <>
      {!embedded && (
        <div className="page-head">
          <div>
            <div className="kicker">Platform administration</div>
            <h1>Directory</h1>
            <p className="sub">Schools people can pick, the email domains that prove they belong, and requests for new schools.</p>
          </div>
        </div>
      )}
      <ErrorBox error={error || dir.error} />
      {msg && <div className="alert ok" role="status">{msg}</div>}

      <RequestsPanel listUrl="/api/admin/school-requests" actionBase="/api/admin/school-requests"
        districts={(dir.data?.districts || []).map((d) => ({ id: d.id, name: d.name }))}
        schools={(dir.data?.districts || []).flatMap((d) => d.schools.map((x) => ({ id: x.id, name: x.name + " (" + d.name + ")", district_id: d.id })))} />

      <div className="card stack">
        <h2>Districts</h2>
        <p className="sub" style={{ margin: 0 }}>If the same district was added twice (for example "CCCD" and "Coast Community College District"), merge the extra one into the official one. Its colleges, organizations, IT roles, and subscriptions move over.</p>
        <table>
          <tbody>
            {(dir.data?.districts || []).map((d) => (
              <tr key={d.id}>
                <td>{d.name}<div className="sub">{d.schools.length} colleges · {d.schools.reduce((n, x) => n + x.org_count, 0)} organizations</div></td>
                <td>
                  <select value={mergeInto[d.id] || ""} onChange={(e) => setMergeInto({ ...mergeInto, [d.id]: e.target.value })}>
                    <option value="">Merge into…</option>
                    {(dir.data?.districts || []).filter((x) => x.id !== d.id).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                  </select>
                </td>
                <td><button className="danger" disabled={!mergeInto[d.id]} onClick={() => {
                  const into = (dir.data?.districts || []).find((x) => x.id === mergeInto[d.id]);
                  if (into && confirm("Merge " + d.name + " into " + into.name + "? " + d.name + " will be removed.")) {
                    void act(() => guard(() => api.post("/api/admin/districts/" + d.id + "/merge", { into_id: into.id })), "Merged into " + into.name + ".");
                  }
                }}>Merge</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card stack">
        <h2>Schools</h2>
        <table>
          <thead><tr><th>School</th><th>Member email domains</th><th>Staff domains (IT roles)</th><th>Orgs</th><th /></tr></thead>
          <tbody>
            {(dir.data?.districts || []).flatMap((d) => d.schools.map((s) => (
              <tr key={s.id}>
                <td>{s.name}<div className="sub">{d.name}{s.active ? "" : " · hidden"}</div></td>
                <td><input value={edits[s.id] ?? s.domains.join(", ")} onChange={(e) => setEdits({ ...edits, [s.id]: e.target.value })} /></td>
                <td><input value={staffEdits[s.id] ?? (s.staff_domains || []).join(", ")} placeholder="college.edu" onChange={(e) => setStaffEdits({ ...staffEdits, [s.id]: e.target.value })} /></td>
                <td>{s.org_count}</td>
                <td className="row">
                  <button onClick={() => void act(() => api.patch("/api/admin/schools/" + s.id, {
                    domains: split(edits[s.id] ?? s.domains.join(",")),
                    staff_domains: split(staffEdits[s.id] ?? (s.staff_domains || []).join(","))
                  }), "Saved.")}>Save</button>
                  <button onClick={() => void act(() => api.patch("/api/admin/schools/" + s.id, { active: !s.active }), s.active ? "Hidden from the list." : "Shown in the list.")}>
                    {s.active ? "Hide" : "Show"}
                  </button>
                </td>
              </tr>
            )))}
          </tbody>
        </table>
        <h2>Add a school</h2>
        <div className="grid-2">
          <label>District
            <select value={add.district_id} onChange={(e) => setAdd({ ...add, district_id: e.target.value })}>
              <option value="">New district…</option>
              {(dir.data?.districts || []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </label>
          {!add.district_id && <label>New district name<input value={add.district_name} onChange={(e) => setAdd({ ...add, district_name: e.target.value })} /></label>}
          <label>School name<input value={add.name} onChange={(e) => setAdd({ ...add, name: e.target.value })} /></label>
          <label>Member email domains<input value={add.domains} placeholder="student.school.edu, school.edu" onChange={(e) => setAdd({ ...add, domains: e.target.value })} /></label>
          <label>Staff domains<input value={add.staff} placeholder="school.edu" onChange={(e) => setAdd({ ...add, staff: e.target.value })} /></label>
        </div>
        <div className="row">
          <button className="primary" disabled={!add.name || !add.domains} onClick={() => void act(async () => {
            await api.post("/api/admin/schools", { district_id: add.district_id, district_name: add.district_name, name: add.name,
              domains: split(add.domains), staff_domains: split(add.staff) });
            setAdd({ district_id: "", district_name: "", name: "", domains: "", staff: "" });
          }, "School added.")}>Add school</button>
        </div>
      </div>
    </>
  );
}
