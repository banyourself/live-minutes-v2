import { useEffect, useState, type FormEvent } from "react";
import { useExamples } from "../examples";
import { Link, useNavigate } from "react-router-dom";
import { api, uploadRecording, type AIConn, type Meeting, type Org, type Template } from "../api";
import { useSession } from "../session";
import { ZoomWarning } from "../components/ZoomChecklist";
import { ErrorBox, errText, useLoad } from "../ui";

export default function UploadMeeting() {
  const { org } = useSession();
  const ex = useExamples();
  const navigate = useNavigate();
  const base = "/api/orgs/" + org!.id;
  const tpls = useLoad(() => api.get<{ templates: Template[] }>(base + "/templates"), [base]);
  const info = useLoad(() => api.get<Org>(base), [base]);
  const conns = useLoad(() => api.get<{ connections: AIConn[] }>("/api/ai/available?org_id=" + org!.id), [org!.id]);
  const zoom = useLoad(() => api.get<{ available: boolean; connected: boolean }>(base + "/zoom"), [base]);
  const [f, setF] = useState({ title: "", day: "", time: "", templateId: "", link: "", draft: true });
  const [recording, setRecording] = useState<File | null>(null);
  const [transcript, setTranscript] = useState<File | null>(null);
  const [chat, setChat] = useState<File | null>(null);
  const [step, setStep] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [told, setTold] = useState(false);
  const templates = (tpls.data?.templates || []).filter((t) => t.purpose !== "example");
  const ai = conns.data?.connections || [];

  useEffect(() => {
    if (info.data) setF((x) => ({ ...x, templateId: x.templateId || info.data!.default_template_id || "" }));
  }, [info.data]);
  const templateId = f.templateId || templates[0]?.id || "";
  const viaZoom = !!(zoom.data?.connected && f.link.trim() && !recording && !transcript);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      if (!templateId) throw new Error("add a template first under Templates, or start from a built-in one");
      let mt: Meeting;
      if (viaZoom) {
        setStep("Finding the recording in Zoom and copying it here…");
        mt = await api.post<Meeting>(base + "/zoom/import-link", { share_url: f.link, title: f.title, template_id: templateId, notice_ack: told });
      } else {
        const when = f.day ? new Date(f.day + "T" + (f.time || "12:00")) : null;
        setStep("Creating the meeting…");
        mt = await api.post<Meeting>(base + "/meetings", {
          title: f.title || recording?.name.replace(/\.[^.]+$/, "") || "Uploaded meeting", template_id: templateId, run_mode: "after",
          status: "ended", ai_connection_id: ai[0]?.id || null, notice_ack: told,
          meeting_date: when ? when.toLocaleString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric", ...(f.time ? { hour: "numeric", minute: "2-digit" } : {}) }) : ""
        });
        for (const [file, label] of [[transcript, "transcript"], [chat, "chat"]] as [File | null, string][]) {
          if (!file) continue;
          setStep("Reading the " + label + "…");
          await api.post("/api/meetings/" + mt.id + "/import", { text: await file.text(), filename: file.name });
        }
        if (recording) {
          setStep("Uploading the recording…");
          setProgress(0);
          mt = await uploadRecording(mt.id, recording, setProgress);
          setProgress(null);
        }
        if (f.link.trim()) await api.put("/api/meetings/" + mt.id + "/recording-link", { url: f.link.trim() });
      }
      if (f.draft && ai.length && (transcript || viaZoom)) {
        setStep("Asking the AI for a draft…");
        await api.post("/api/meetings/" + mt.id + "/draft", { full: true }).catch(() => undefined);
      }
      navigate("/meetings/" + mt.id + "?tab=recording");
    } catch (err) {
      setError(errText(err));
      setStep("");
      setProgress(null);
    }
  }

  const busy = !!step;
  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker">Add a past meeting</div>
          <h1>Upload meeting</h1>
          <p className="sub">Bring in a meeting that already happened: its recording, transcript, and chat from Zoom, so it can be watched, searched, and turned into minutes.</p>
        </div>
      </div>
      <form className="card stack" style={{ maxWidth: 820 }} onSubmit={submit}>
        <div className="grid-2">
          <label>Title<input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder={ex.uploadTitle} /></label>
          <label>Date<input type="date" value={f.day} onChange={(e) => setF({ ...f, day: e.target.value })} /></label>
          <label>Start time (optional)<input type="time" value={f.time} onChange={(e) => setF({ ...f, time: e.target.value })} /></label>
          <label>Template for the minutes
            <select value={templateId} onChange={(e) => setF({ ...f, templateId: e.target.value })}>
              {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </label>
        </div>
        {templates.length === 0 && <div className="alert warn">No template yet. <Link to="/templates">Add one or start from a built-in template.</Link></div>}

        <h3>Zoom recording link</h3>
        <label>Share link (optional)
          <input value={f.link} onChange={(e) => setF({ ...f, link: e.target.value })} placeholder={ex.recordingLink} className="mono" />
        </label>
        {zoom.data?.connected && <ZoomWarning orgId={org!.id} />}
        <p className="sub" style={{ margin: 0 }}>
          {zoom.data?.connected
            ? "Zoom is connected. With only a link, Live Minutes finds the recording in the connected Zoom account and copies the video, transcript, and chat here."
            : "Zoom is not connected, so Live Minutes cannot open the link itself. On the share page, download the recording, the audio transcript (.vtt), and the chat file, then add them below. The link is saved so people can also watch it on Zoom."}
        </p>

        <h3>Files</h3>
        <div className="grid-2">
          <label>Recording (MP4 or M4A)<input type="file" accept="video/mp4,video/quicktime,video/webm,audio/mp4,audio/mpeg,audio/wav,.m4a,.mp4,.mov"
            onChange={(e) => setRecording(e.target.files?.[0] || null)} /></label>
          <label>Transcript (.vtt from Zoom, or .txt)<input type="file" accept=".vtt,.txt,.srt" onChange={(e) => setTranscript(e.target.files?.[0] || null)} /></label>
          <label>Chat (.txt from Zoom)<input type="file" accept=".txt" onChange={(e) => setChat(e.target.files?.[0] || null)} /></label>
        </div>
        {ai.length > 0 && (
          <label className="setting-row">
            <span>Draft the minutes from the transcript right away</span>
            <input type="checkbox" checked={f.draft} onChange={(e) => setF({ ...f, draft: e.target.checked })} />
          </label>
        )}
        <div className="alert" role="note">A public meeting's recording and transcript can be viewed by anyone once it is saved; the chat stays private.</div>
        <label className="row" style={{ textTransform: "none", letterSpacing: "normal", alignItems: "flex-start" }}>
          <input type="checkbox" checked={told} onChange={(e) => setTold(e.target.checked)} required style={{ marginTop: 4 }} />
          <span>Everyone in this meeting knew it was being recorded, and I am allowed to add this recording and transcript.{" "}
            <Link to="/terms" target="_blank">Recording rules</Link></span>
        </label>
        {progress !== null && <progress value={progress} max={1} style={{ width: "100%" }} aria-label="Upload progress" />}
        {step && <div className="sub" role="status">{step}{progress !== null ? " " + Math.round(progress * 100) + "%" : ""}</div>}
        <ErrorBox error={error} />
        <div className="row">
          <button className="primary" disabled={busy || !told || (!recording && !transcript && !chat && !f.link.trim())}>{viaZoom ? "Import from Zoom" : "Upload meeting"}</button>
          <Link className="btn" to="/dashboard">Cancel</Link>
        </div>
      </form>
    </>
  );
}
