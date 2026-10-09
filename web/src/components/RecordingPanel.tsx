import { useState } from "react";
import { useExamples } from "../examples";
import { api, uploadRecording, type Line, type Meeting } from "../api";
import { ErrorBox, errText } from "../ui";
import Player from "./Player";

const size = (n: number) => n > 1073741824 ? (n / 1073741824).toFixed(1) + " GB" : Math.max(1, Math.round(n / 1048576)) + " MB";

export default function RecordingPanel({ meeting, lines, secretary, onChanged }: {
  meeting: Meeting; lines: Line[]; secretary: boolean; onChanged: () => void;
}) {
  const ex = useExamples();
  const base = "/api/meetings/" + meeting.id;
  const [progress, setProgress] = useState<number | null>(null);
  const [link, setLink] = useState(meeting.recording_link);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  async function upload(file: File) {
    setError(""); setMsg(""); setProgress(0);
    try {
      await uploadRecording(meeting.id, file, setProgress);
      setMsg("Recording uploaded.");
      onChanged();
    } catch (e) {
      setError(errText(e));
    } finally {
      setProgress(null);
    }
  }

  async function run(fn: () => Promise<unknown>, done: string) {
    setError(""); setMsg("");
    try { await fn(); setMsg(done); onChanged(); } catch (e) { setError(errText(e)); }
  }

  const transcriptLinks: [string, string][] = [["Transcript .txt", base + "/transcript.txt"], ["Captions .vtt", base + "/transcript.vtt"], ["Subtitles .srt", base + "/transcript.srt"]];
  return (
    <div className="card stack">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Recording and transcript</h2>
        {meeting.recording_link && <a className="btn sm" href={meeting.recording_link} target="_blank" rel="noopener noreferrer">Watch on Zoom</a>}
      </div>
      {meeting.recording ? (
        <Player src={base + "/recording"} type={meeting.recording.type} captions={base + "/transcript.vtt"} lines={lines}
          downloads={[["Download recording (" + size(meeting.recording.size) + ")", base + "/recording?download=1"], ...transcriptLinks]} />
      ) : (
        <>
          <p className="sub" style={{ margin: 0 }}>No recording stored here yet. Live Minutes captures captions, not audio, so recordings come from Zoom:
            upload the file you downloaded, or import it under Meeting sources if Zoom is connected.</p>
          {lines.length > 0 && <div className="row">{transcriptLinks.map(([l, h]) => <a key={h} className="btn sm" href={h}>{l}</a>)}</div>}
        </>
      )}
      {msg && <div className="alert ok" role="status">{msg}</div>}
      <ErrorBox error={error} />
      {secretary && (
        <div className="stack">
          <label>{meeting.recording ? "Replace the recording" : "Upload the recording"} (MP4, M4A, MOV, WebM, MP3, WAV)
            <input type="file" accept="video/mp4,video/quicktime,video/webm,audio/mp4,audio/x-m4a,audio/mpeg,audio/wav,audio/ogg,.m4a,.mp4,.mov"
              disabled={progress !== null} onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
          </label>
          {progress !== null && (
            <div className="stack" style={{ gap: 4 }}>
              <progress value={progress} max={1} style={{ width: "100%" }} aria-label="Upload progress" />
              <span className="sub" role="status">Uploading… {Math.round(progress * 100)}%. Keep this page open.</span>
            </div>
          )}
          <div className="row">
            <input value={link} onChange={(e) => setLink(e.target.value)} placeholder={ex.recordingLink} aria-label="Zoom recording share link" style={{ flex: 1 }} />
            <button onClick={() => void run(() => api.put(base + "/recording-link", { url: link }), "Zoom link saved.")}>Save Zoom link</button>
          </div>
          {meeting.recording && (
            <div className="row"><button className="danger" onClick={() => { if (confirm("Delete the stored recording? The transcript and minutes stay.")) void run(() => api.del(base + "/recording"), "Recording deleted."); }}>Delete recording</button></div>
          )}
        </div>
      )}
    </div>
  );
}
