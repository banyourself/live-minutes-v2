import { Link } from "react-router-dom";
import { api } from "../api";
import { useSession } from "../session";
import { ErrorBox, fmtDate, useLoad } from "../ui";

interface Rec { id: string; title: string; meeting_date: string; status: string; type: string; size: number; created_at: number }

const bytes = (n: number) => n >= 1073741824 ? (n / 1073741824).toFixed(1) + " GB" : n >= 1048576 ? (n / 1048576).toFixed(1) + " MB"
  : Math.max(1, Math.round(n / 1024)) + " KB";

export default function Recordings() {
  const { org } = useSession();
  const base = "/api/orgs/" + org!.id;
  const data = useLoad(() => api.get<{ recordings: Rec[]; total_bytes: number; can_download_all: boolean }>(base + "/recordings"), [base]);
  const rows = data.data?.recordings || [];
  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker">File cabinet</div>
          <h1>Recordings</h1>
          <p className="sub">Every meeting recording kept in Live Minutes for {org!.name}. Play one with its transcript from the meeting, download it,
            or download them all at once. Recordings are not part of automatic backups, so download any you need to keep elsewhere.</p>
        </div>
        {data.data?.can_download_all && rows.length > 0 && (
          <a className="btn primary" href={base + "/recordings.zip"} download>Download all ({bytes(data.data.total_bytes)}, ZIP)</a>
        )}
      </div>
      <ErrorBox error={data.error} />
      <div className="card">
        {rows.length === 0 && !data.loading ? <div className="empty">No recordings yet. Add one from a meeting's Recording tab, or upload a meeting.</div> : (
          <table>
            <thead><tr><th scope="col">Meeting</th><th scope="col">Date</th><th scope="col">Size</th><th /></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td><Link to={"/meetings/" + r.id + "?tab=recording"}>{r.title}</Link></td>
                  <td className="sub">{r.meeting_date || fmtDate(r.created_at)}</td>
                  <td className="sub">{bytes(r.size)}</td>
                  <td><a className="btn" href={"/api/meetings/" + r.id + "/recording?download=1"} download>Download</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
