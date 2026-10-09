import { useState } from "react";
import { api, type Meeting } from "../api";
import { ErrorBox, errText, fmtDate, useLoad } from "../ui";

interface ZoomStatus { available: boolean; connected: boolean; host_email: string }
interface Recording { uuid: string; topic: string; start_time: string; files: string[] }
const FILE_NAMES: Record<string, string> = { CC: "Captions", TRANSCRIPT: "Transcript", CHAT: "Chat", MP4: "Video", M4A: "Audio" };

export default function SourcesPanel({ meeting, onImported }: { meeting: Meeting; onImported: () => void }) {
  const base = "/api/orgs/" + meeting.org_id;
  const zoom = useLoad(() => api.get<ZoomStatus>(base + "/zoom"), [base]);
  const [token, setToken] = useState("");
  const [paste, setPaste] = useState("");
  const [recs, setRecs] = useState<Recording[] | null>(null);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<string>) {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      setMsg(await fn());
      onImported();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  const importText = (text: string, filename: string) => run(async () => {
    const r = await api.post<{ kind: string; lines: number }>("/api/meetings/" + meeting.id + "/import", { text, filename });
    return "Imported " + r.lines + " " + r.kind + " lines.";
  });

  return (
    <div className="grid-2">
      <div className="card stack">
        <h2>Live captions</h2>
        <p className="sub">
          Join the meeting in the <strong>Live Minutes desktop app</strong> (it opens Zoom in its own window and reads the
          captions), or in Chrome with the <strong>Live Minutes extension</strong>. Both only read captions you can already
          see as a participant. Turn on captions or the full transcript panel in Zoom first.
        </p>
        <ol className="sub" style={{ margin: 0, paddingLeft: 18 }}>
          <li>Create a capture token below and paste it into the desktop app or the extension.</li>
          <li>Choose this meeting, <strong>{meeting.title}</strong>, in the app.</li>
          <li>Click "Pick captions area" and click the caption or transcript panel.</li>
        </ol>
        {meeting.status !== "open" && <div className="alert warn">This meeting has ended, so live captions are closed.</div>}
        <div className="row">
          <button disabled={busy} onClick={() => void run(async () => {
            const r = await api.post<{ token: string }>(base + "/capture-tokens", { label: "Capture for " + meeting.title });
            setToken(r.token);
            return "Capture token created. Copy it now; it is shown only once.";
          })}>Create capture token</button>
        </div>
        {token && (
          <div className="stack">
            <div className="token-box mono">{token}</div>
            <div className="row">
              <button onClick={() => void navigator.clipboard.writeText(token)}>Copy token</button>
              <span className="sub">Server: {location.origin} · Meeting ID: <span className="mono">{meeting.id}</span></span>
            </div>
          </div>
        )}
      </div>

      <div className="card stack">
        <h2>Import a transcript or chat</h2>
        <p className="sub">A Zoom .vtt transcript, a Zoom chat file, or text copied from a recording page. Chat votes are kept.</p>
        <input type="file" accept=".vtt,.srt,.txt" disabled={busy}
          onChange={async (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) await importText(await f.text(), f.name); }} />
        <textarea aria-label="Transcript text" placeholder="…or paste transcript text here" value={paste} onChange={(e) => setPaste(e.target.value)} />
        <div className="row">
          <button disabled={busy || !paste.trim()} onClick={() => void importText(paste, "pasted.txt").then(() => setPaste(""))}>Import pasted text</button>
        </div>
      </div>

      <div className="card stack">
        <h2>Zoom recording</h2>
        {!zoom.data?.available ? (
          <p className="sub">The Zoom app is not turned on for this server yet.</p>
        ) : !zoom.data.connected ? (
          <p className="sub">Zoom is not connected. Connect the account that hosts your meetings once, in Settings, Zoom.</p>
        ) : (
          <>
            <p className="sub">Connected as {zoom.data.host_email}. Import a cloud recording's transcript and chat.</p>
            <div className="row">
              <button disabled={busy} onClick={() => void run(async () => {
                const r = await api.get<{ recordings: Recording[] }>(base + "/zoom/recordings?days=30");
                setRecs(r.recordings);
                return r.recordings.length + " recording(s) found.";
              })}>List recent recordings</button>
            </div>
            {recs?.map((r) => (
              <div key={r.uuid} className="row spread motion">
                <span>{r.topic}<br /><span className="sub">{fmtDate(Date.parse(r.start_time) / 1000) || r.start_time} · {r.files.map((f) => FILE_NAMES[f] || f).join(", ")}</span></span>
                <button disabled={busy || !["CC", "TRANSCRIPT", "MP4", "M4A", "CHAT"].some((k) => r.files.includes(k))} onClick={() => void run(async () => {
                  const x = await api.post<{ transcript_lines: number; chat_lines: number; recording: boolean; source: string; recording_skipped?: string }>(
                    "/api/meetings/" + meeting.id + "/zoom-import", { uuid: r.uuid, recording: true });
                  return "Imported " + x.transcript_lines + (x.source === "captions" ? " lines from Zoom's closed captions" : " transcript lines") +
                    " and " + x.chat_lines + " chat lines" + (x.recording ? ", and the recording." : ".") +
                    (x.recording_skipped ? " The video was not kept because this workspace's recording storage is full." : "");
                })}>Import</button>
              </div>
            ))}
          </>
        )}
      </div>

      <div className="stack" style={{ alignSelf: "start" }}>
        <ErrorBox error={error || zoom.error} />
        {msg && <div className="alert ok" role="status">{msg}</div>}
      </div>
    </div>
  );
}
