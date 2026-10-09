import { useParams } from "react-router-dom";
import { api } from "../api";
import { LegalLinks } from "./legal-links";
import { fmtDate, useLoad } from "../ui";

interface ArchiveData {
  name: string;
  school: string;
  meetings: { id: string; title: string; meeting_date: string; approved_at: number | null; summary: string }[];
}

export default function Archive() {
  const { orgId = "" } = useParams();
  const data = useLoad(() => api.get<ArchiveData>("/api/public/orgs/" + encodeURIComponent(orgId)), [orgId]);
  if (data.loading) return <p className="sub" role="status">Loading…</p>;
  if (!data.data) {
    return (
      <article className="legal">
        <h1>Minutes archive</h1>
        <p>This organization does not publish its minutes here, or the link is not right.</p>
      </article>
    );
  }
  const a = data.data;
  return (
    <article className="legal">
      <div className="page-head">
        <div>
          <div className="kicker">Approved minutes</div>
          <h1>{a.name}</h1>
          {a.school && <p className="sub">{a.school}</p>}
        </div>
      </div>
      <div className="card stack legal-body">
        <p>These are the official minutes this organization approved and chose to publish. Drafts, recordings, transcripts, and
          votes are not shown here.</p>
        {a.meetings.length === 0 && <p className="sub">No approved minutes are published yet.</p>}
        {a.meetings.map((m) => (
          <section key={m.id} className="stack" style={{ gap: 6 }}>
            <h2 style={{ margin: 0 }}>{m.title}</h2>
            <p className="sub" style={{ margin: 0 }}>{m.meeting_date || ""}{m.approved_at ? " · approved " + fmtDate(m.approved_at) : ""}</p>
            {m.summary && <p style={{ whiteSpace: "pre-line", margin: 0 }}>{m.summary}</p>}
            <div className="row"><a className="btn" href={"/api/public/meetings/" + m.id + "/minutes.docx"} download>Download the minutes (Word)</a></div>
          </section>
        ))}
      </div>
      <p className="sub" style={{ textAlign: "center" }}><LegalLinks /></p>
    </article>
  );
}
