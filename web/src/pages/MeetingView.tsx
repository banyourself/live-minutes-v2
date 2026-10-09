import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ProgressBar } from "../components/FreeAIProgress";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError, can, type Draft, type Line, type Meeting, type Motion, type Outline, type ReportValue } from "../api";
import { ErrorBox, errText, fileNo, fmtClock, fmtDate, StatusBadge } from "../ui";
import SourcesPanel from "../components/SourcesPanel";
import ReferencePanel from "../components/ReferencePanel";
import MotionRecord from "../components/MotionRecord";
import SharePanel from "../components/SharePanel";
import RecordingPanel from "../components/RecordingPanel";
import HistoryPanel from "../components/HistoryPanel";
import { when, ZoomLink } from "./Meetings";
import { useSession } from "../session";

interface LiveResponse {
  server_time: number;
  meeting: Meeting;
  lines: Line[];
  motions: Motion[];
}

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v ?? {}));
const planPrompt = (meetingId: string) =>
  "Use the Live Minutes connector to draft the minutes for my meeting " + meetingId + ". Call get_meeting with that meeting ID, follow its " +
  "instructions, then save the draft with save_minutes_draft so I can review and approve it in Live Minutes.";

function reportText(v: string | ReportValue) {
  return typeof v === "string" ? v : v.text;
}

export default function MeetingView() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { refresh } = useSession();
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [motions, setMotions] = useState<Motion[]>([]);
  const [outline, setOutline] = useState<Outline | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [dirty, setDirty] = useState(false);
  const [aiNewer, setAiNewer] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [params] = useSearchParams();
  const focusLine = params.get("line");
  const [tab, setTab] = useState<"draft" | "transcript" | "sources" | "votes" | "share" | "recording" | "history">(
    focusLine ? "transcript" : params.get("tab") === "votes" ? "votes" : params.get("tab") === "recording" ? "recording" : "draft");
  const cursor = useRef({ afterSeq: 0, since: 0 });
  const serverDraft = useRef("");
  const dirtyRef = useRef(false);
  const baseRev = useRef(0);
  const serverRev = useRef(0);
  const tail = useRef<HTMLDivElement>(null);

  const poll = useCallback(async () => {
    try {
      const r = await api.get<LiveResponse>(
        "/api/meetings/" + id + "/live?after_seq=" + cursor.current.afterSeq + "&since=" + cursor.current.since);
      cursor.current.since = r.server_time - 2;
      if (r.lines.length) {
        cursor.current.afterSeq = Math.max(cursor.current.afterSeq, ...r.lines.map((l) => l.seq + 1));
        setLines((prev) => {
          const map = new Map(prev.map((l) => [l.seq, l]));
          r.lines.forEach((l) => map.set(l.seq, l));
          return [...map.values()].sort((a, b) => a.seq - b.seq);
        });
      }
      setMotions(r.motions);
      setMeeting(r.meeting);
      serverRev.current = r.meeting.draft_rev;
      const incoming = JSON.stringify(r.meeting.draft || {});
      if (incoming !== serverDraft.current) {
        serverDraft.current = incoming;
        if (dirtyRef.current) setAiNewer(true);
        else setDraft(clone(r.meeting.draft));
      }
      if (!dirtyRef.current) baseRev.current = r.meeting.draft_rev;
      setError("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) void refresh();
      setError(errText(e));
    }
  }, [id, refresh]);

  useEffect(() => {
    cursor.current = { afterSeq: 0, since: 0 };
    serverDraft.current = "";
    setLines([]);
    void poll();
    const t = setInterval(() => void poll(), 2500);
    return () => clearInterval(t);
  }, [poll]);

  useEffect(() => {
    if (!meeting?.template?.id) return;
    api.get<{ outline: Outline }>("/api/templates/" + meeting.template.id + "/outline")
      .then((r) => setOutline(r.outline)).catch(() => undefined);
  }, [meeting?.template?.id]);

  useEffect(() => {
    if (tab !== "transcript" || !tail.current) return;
    const target = focusLine ? document.getElementById("line-" + focusLine) : null;
    if (target) target.scrollIntoView({ block: "center" });
    else if (!focusLine) tail.current.scrollTop = tail.current.scrollHeight;
  }, [lines.length, tab]);

  function edit(next: Draft) {
    setDraft(next);
    setDirty(true);
    dirtyRef.current = true;
  }

  async function act(label: string, fn: () => Promise<unknown>, done = "") {
    setBusy(label);
    setError("");
    try {
      await fn();
      if (done) setNotice(done);
      await poll();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy("");
    }
  }

  async function pushDraft() {
    let m: Meeting;
    try {
      m = await api.patch<Meeting>("/api/meetings/" + id, { draft, base_rev: baseRev.current });
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        baseRev.current = serverRev.current;
        setAiNewer(true);
        throw new Error("The AI updated this draft while you were editing. Press Save again to keep your version, or load the AI version.");
      }
      throw e;
    }
    baseRev.current = m.draft_rev;
    serverRev.current = m.draft_rev;
    serverDraft.current = JSON.stringify(m.draft || {});
    setDirty(false);
    dirtyRef.current = false;
    setAiNewer(false);
  }

  async function save() {
    await act("save", pushDraft, "Draft saved.");
  }

  function loadAiVersion() {
    baseRev.current = serverRev.current;
    setDraft(clone(JSON.parse(serverDraft.current || "{}")));
    setDirty(false);
    dirtyRef.current = false;
    setAiNewer(false);
  }

  async function exportDocx() {
    await act("export", async () => {
      if (dirty) await pushDraft();
      const r = await api.post<{ download: string; skipped: string[] }>("/api/meetings/" + id + "/export");
      window.location.href = r.download;
      if (r.skipped.length) setNotice(r.skipped.length + " item(s) did not match the template and were left out.");
    });
  }

  const unfilled = useMemo(() => {
    const used = new Set((draft.fills || []).map((f) => f.under));
    return (outline?.slots || []).filter((s) => ![...used].some((u) => s.startsWith(u) || u.startsWith(s)));
  }, [outline, draft.fills]);

  if (!meeting) return <><ErrorBox error={error} />{!error && <div className="empty">Loading…</div>}</>;
  const secretary = can(meeting.role, "secretary");
  const locked = meeting.status === "approved";
  const pending = meeting.line_count - meeting.drafted_upto;

  return (
    <>
      <div className="page-head">
        <div>
          <div className="row" style={{ marginBottom: 6 }}>
            <Link to="/dashboard" className="lbl" style={{ margin: 0 }}>← Minutes index</Link>
          </div>
          <div className="kicker">Minutes file<span className="lbl">File no. {fileNo(meeting.created_at, meeting.id)}</span></div>
          <h1>{meeting.title}</h1>
          <div className="row sub">
            <StatusBadge status={meeting.status} />
            <span className="chip">Members only</span>
            <span>{meeting.meeting_date}</span>
            <span>· {meeting.run_mode === "live" ? "Live drafting" : "Draft after meeting"}</span>
            <span>· {meeting.ai_connection ? meeting.ai_connection.label + " (" + meeting.ai_connection.model + ")" : "No AI chosen for drafting"}</span>
            {meeting.draft_status === "drafting" && <span className="badge accent">AI drafting…</span>}
            {meeting.draft_status === "queued" && <span className="badge">Draft queued</span>}
            {meeting.draft_status === "error" && <span className="badge bad">Draft failed</span>}
            {meeting.zoom_url && meeting.status === "open" && <a href={meeting.zoom_url} target="_blank" rel="noopener noreferrer">Join on Zoom</a>}
          </div>
          {secretary && !locked && meeting.status !== "scheduled" && (
            <div className="row sub">
              <span>Draft with your own plan:</span>
              <a href={"https://claude.ai/new?q=" + encodeURIComponent(planPrompt(id))} target="_blank" rel="noopener noreferrer">Claude</a>
              <a href={"https://chatgpt.com/?q=" + encodeURIComponent(planPrompt(id))} target="_blank" rel="noopener noreferrer">ChatGPT</a>
              <a href={"https://grok.com/?q=" + encodeURIComponent(planPrompt(id))} target="_blank" rel="noopener noreferrer">Grok</a>
              <button type="button" className="link" onClick={() => {
                void navigator.clipboard.writeText(planPrompt(id))
                  .then(() => setNotice("Copied. Paste it into Gemini, Le Chat, Perplexity, or any AI app you connected to Live Minutes."))
                  .catch(() => setError("Could not copy; your browser blocked the clipboard."));
              }}>Copy the request for Gemini, Le Chat, or Perplexity</button>
              <Link to="/account?tab=ai">First time? Connect Live Minutes there</Link>
            </div>
          )}
        </div>
        <div className="row">
          {secretary && !locked && meeting.status !== "scheduled" && (
            <button disabled={!!busy}
              onClick={() => void act("draft", () => api.post("/api/meetings/" + id + "/draft", { full: true }), "Draft requested.")}>
              Update draft now
            </button>
          )}
          {secretary && meeting.status === "open" && (
            <button disabled={!!busy} onClick={() => { if (confirm("End the meeting? Captions stop and the final draft is written.")) void act("end", () => api.post("/api/meetings/" + id + "/end"), "Meeting ended. Final draft requested."); }}>
              End meeting
            </button>
          )}
          {can(meeting.role, "member") && (
            <button className={secretary && !locked && meeting.status === "ended" ? "" : "primary"} disabled={!!busy} onClick={() => void exportDocx()}>
              {busy === "export" ? "Building…" : "Download Word file"}
            </button>
          )}
          {secretary && !locked && meeting.status === "ended" && (
            <button className="primary" disabled={!!busy || (meeting.review.required && meeting.review.status !== "reviewed" && !meeting.review.can_review)}
              title={meeting.review.required && meeting.review.status !== "reviewed" && !meeting.review.can_review ? "An advisor needs to review these minutes first" : ""}
              onClick={() => { if (confirm("Approve these minutes? They become the official record and are locked until someone reopens them.")) void act("approve", () => api.post("/api/meetings/" + id + "/approve"), "Minutes approved."); }}>
              Approve
            </button>
          )}
          {secretary && locked && (
            <button disabled={!!busy} onClick={() => void act("reopen", () => api.post("/api/meetings/" + id + "/reopen"))}>Reopen</button>
          )}
        </div>
      </div>

      {meeting.status === "scheduled" && (
        <div className="card row spread">
          <div>
            <strong>Scheduled for {when(meeting.scheduled_at)}</strong>
            <div className="sub">{meeting.duration_min} minutes{meeting.location ? " · " + meeting.location : ""}{meeting.series_id ? " · repeats" : ""}</div>
          </div>
          <div className="row">
            <ZoomLink url={meeting.zoom_url} />
            <a className="btn sm" href={"/api/meetings/" + id + "/invite.ics"}>Add to calendar</a>
            {secretary && <button className="primary" disabled={!!busy} onClick={() => void act("start", () => api.post("/api/meetings/" + id + "/start"), "Meeting started.")}>Start meeting</button>}
            {secretary && <button className="danger" disabled={!!busy} onClick={() => {
              if (confirm("Cancel this meeting?")) void act("cancel", async () => { await api.post("/api/meetings/" + id + "/cancel"); navigate("/dashboard"); });
            }}>Cancel meeting</button>}
          </div>
        </div>
      )}
      {meeting.sample && <div className="alert warn" style={{ marginBottom: 12 }}>This is a sample meeting with made-up people and events, for trying out
        Live Minutes. Remove samples from the bottom of the Meetings page.</div>}
      {meeting.free_ai && (
        <div className="card stack" style={{ marginBottom: 12 }}>
          <strong>{meeting.free_ai.status === "queued" ? "Waiting for the free AI" : "The free AI is drafting these minutes"}</strong>
          <ProgressBar run={meeting.free_ai} />
          <p className="sub" style={{ margin: 0 }}>It runs on the Live Minutes server, so it is free but slower: about 15 to 40 minutes for an hour-long
            meeting. You can close this page; you will get a notification when the draft is ready.</p>
        </div>
      )}
      <ErrorBox error={error || (meeting.draft_status === "error" ? "Drafting failed: " + meeting.draft_error : "")} />
      {notice && <div className="alert ok" role="status" style={{ marginBottom: 12 }} onClick={() => setNotice("")}>{notice}</div>}
      {meeting.problems.length > 0 && (
        <div className="alert warn" style={{ marginBottom: 12 }}>
          {meeting.problems.length} item(s) don't match the template and will be left out of the Word file: {meeting.problems.join("; ")}
        </div>
      )}

      {meeting.status === "ended" && (meeting.review.has_reviewers || meeting.review.status) && (
        <ReviewPanel meeting={meeting} secretary={secretary} busy={!!busy}
          send={(body, done) => act("review", () => api.post("/api/meetings/" + id + "/review", body), done)} />
      )}

      <div className="tabs" role="group" aria-label="Sections">
        <button className={tab === "draft" ? "on" : ""} aria-pressed={tab === "draft"} onClick={() => setTab("draft")}>Draft</button>
        <button className={tab === "transcript" ? "on" : ""} aria-pressed={tab === "transcript"} onClick={() => setTab("transcript")}>
          Transcript ({meeting.line_count}{pending > 0 ? ", " + pending + " new" : ""})
        </button>
        <button className={tab === "votes" ? "on" : ""} aria-pressed={tab === "votes"} onClick={() => setTab("votes")}>Votes</button>
        <button className={tab === "recording" ? "on" : ""} aria-pressed={tab === "recording"} onClick={() => setTab("recording")}>
          Recording{meeting.recording ? "" : meeting.recording_link ? " (Zoom link)" : ""}
        </button>
        <button className={tab === "history" ? "on" : ""} aria-pressed={tab === "history"} onClick={() => setTab("history")}>History</button>
        <button className={tab === "share" ? "on" : ""} aria-pressed={tab === "share"} onClick={() => setTab("share")}>Summary and translations</button>
        {secretary && <button className={tab === "sources" ? "on" : ""} aria-pressed={tab === "sources"} onClick={() => setTab("sources")}>Sources</button>}
      </div>

      {tab === "sources" && <div className="stack"><SourcesPanel meeting={meeting} onImported={() => void poll()} /><ReferencePanel meeting={meeting} canEdit={secretary} /></div>}
      {tab === "votes" && <MotionRecord meetingId={id} />}
      {tab === "share" && <SharePanel meetingId={id} secretary={secretary} />}
      {tab === "history" && <HistoryPanel meetingId={id} dirty={dirty} onRestored={async () => {
        dirtyRef.current = false; setDirty(false); setAiNewer(false); serverDraft.current = ""; await poll(); setNotice("Older version restored.");
      }} />}
      {tab === "recording" && <RecordingPanel meeting={meeting} lines={lines} secretary={secretary} onChanged={() => void poll()} />}

      {tab !== "sources" && tab !== "votes" && tab !== "share" && tab !== "recording" && tab !== "history" && (
        <div className="grid-3">
          <div>
            {tab === "draft" ? (
              <DraftEditor draft={draft} onChange={edit} readOnly={!secretary || locked} unfilled={unfilled}
                dirty={dirty} aiNewer={aiNewer} saving={busy === "save"} onSave={() => void save()} onLoadAi={loadAiVersion} />
            ) : (
              <div className="card">
                <div className="row spread" style={{ marginBottom: 8 }}>
                  <h2 style={{ margin: 0 }}>Transcript</h2>
                  <div className="row">
                    {["txt", "vtt", "srt"].map((f) => (
                      <a key={f} className="btn" href={"/api/meetings/" + id + "/transcript." + f}>.{f}</a>
                    ))}
                  </div>
                </div>
                <div className="transcript" ref={tail}>
                  {lines.length === 0 ? <div className="empty">No transcript yet. Connect a source in Meeting sources.</div> :
                    lines.map((l) => (
                      <div key={l.seq} id={"line-" + l.seq} className={"tline" + (String(l.seq) === focusLine ? " hit" : "")}>
                        <span className="ts">{fmtClock(l.t)}</span>
                        {l.speaker && <span className="who">{l.speaker}</span>}
                        {l.source === "chat" && <span className="chat">chat</span>}
                        {l.speaker ? ": " : ""}{l.text}
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
          <div>
            <div className="card">
              <h2>Motion tracker</h2>
              <p className="sub">Detected from the transcript. Confirm each one before approving.</p>
              {motions.length === 0 ? <div className="empty">No motions detected yet.</div> : motions.map((m, i) => {
                const cls = /pass|carr/.test(m.status) ? "ok" : /fail/.test(m.status) ? "" : "warn";
                const word = /pass|carr/.test(m.status) ? "Carried" : /fail/.test(m.status) ? "Failed" : m.seconder ? "Pending vote" : "Needs second";
                const tally = Object.entries(m.tally || {}).map(([k, v]) => k + " " + v).join(", ");
                return (
                  <div key={i} className="motion">
                    <div className="row spread"><span className="lbl" style={{ margin: 0 }}>Motion {i + 1} · {fmtClock(m.t)}</span><span className={"stamp sm " + cls}>{word}</span></div>
                    <div style={{ marginTop: 4 }}>Moved by <strong>{m.mover || "?"}</strong>
                      {m.seconder ? <>, seconded by <strong>{m.seconder}</strong></> : null}{tally ? " · " + tally : ""}</div>
                    <div className="sub">{m.text}</div>
                  </div>
                );
              })}
            </div>
            <div className="card">
              <h2>Details</h2>
              <div className="stack sub">
                <span>Template: {meeting.template?.name}{meeting.template?.mode === "generated" ? " (generated)" : ""}</span>
                <span>Created {fmtDate(meeting.created_at)}</span>
                {meeting.approved_at && <span>Approved {fmtDate(meeting.approved_at)}</span>}
                {secretary && can(meeting.role, "owner") && (
                  <button className="danger" style={{ justifySelf: "start" }} onClick={() => {
                    if (confirm("Delete this meeting, its transcript and its files? This cannot be undone.")) {
                      void act("delete", async () => { await api.del("/api/meetings/" + id); navigate("/dashboard"); });
                    }
                  }}>Delete meeting</button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

interface EditorProps {
  draft: Draft;
  onChange: (d: Draft) => void;
  readOnly: boolean;
  unfilled: string[];
  dirty: boolean;
  aiNewer: boolean;
  saving: boolean;
  onSave: () => void;
  onLoadAi: () => void;
}

function DraftEditor({ draft, onChange, readOnly, unfilled, dirty, aiNewer, saving, onSave, onLoadAi }: EditorProps) {
  const set = (patch: Partial<Draft>) => onChange({ ...draft, ...patch });
  const fills = draft.fills || [];
  const reports = Object.entries(draft.reports || {});
  const roll = Object.entries(draft.roll_call || {});
  const empty = !fills.length && !reports.length && !(draft.summary || []).length && !draft.order_time;

  return (
    <div className="card">
      <div className="row spread" style={{ marginBottom: 10 }}>
        <h2 style={{ margin: 0 }}>Draft minutes</h2>
        {!readOnly && (
          <div className="row">
            {dirty && <span className="badge warn">Unsaved edits</span>}
            <button className="primary" disabled={!dirty || saving} onClick={onSave}>{saving ? "Saving…" : "Save"}</button>
          </div>
        )}
      </div>
      {aiNewer && (
        <div className="alert warn" style={{ marginBottom: 10 }}>
          The AI updated the draft while you were editing. Your edits are kept.{" "}
          <button className="link" onClick={onLoadAi}>Load the AI version instead</button>
        </div>
      )}
      {empty && <div className="empty">The draft appears here as the meeting is transcribed.</div>}

      {(draft.order_time !== undefined || draft.adjourn_time !== undefined) && (
        <div className="grid-2 section-item">
          <label>Called to order<input disabled={readOnly} value={draft.order_time || ""} onChange={(e) => set({ order_time: e.target.value })} /></label>
          <label>Adjourned<input disabled={readOnly} value={draft.adjourn_time || ""} onChange={(e) => set({ adjourn_time: e.target.value })} /></label>
        </div>
      )}

      {roll.length > 0 && (
        <div className="section-item">
          <div className="label">Roll call</div>
          <div className="stack">
            {roll.map(([k, v]) => (
              <label key={k}>{k}<input disabled={readOnly} value={v}
                onChange={(e) => set({ roll_call: { ...draft.roll_call, [k]: e.target.value } })} /></label>
            ))}
          </div>
        </div>
      )}

      {fills.map((f, i) => (
        <div className="section-item" key={i}>
          <div className="row spread">
            <div className="label">{f.under}</div>
            {!readOnly && <button className="link" onClick={() => set({ fills: fills.filter((_, j) => j !== i) })}>Remove</button>}
          </div>
          <textarea disabled={readOnly} value={f.text} rows={Math.min(10, Math.max(3, Math.ceil(f.text.length / 90)))}
            onChange={(e) => set({ fills: fills.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)) })} />
        </div>
      ))}

      {(draft.motions || []).map((m, i) => (
        <div className="section-item" key={"m" + i}>
          <div className="label">Motion · {m.under}</div>
          <textarea disabled={readOnly} value={m.text}
            onChange={(e) => set({ motions: (draft.motions || []).map((x, j) => (j === i ? { ...x, text: e.target.value } : x)) })} />
        </div>
      ))}

      {(draft.replace || []).map((m, i) => (
        <div className="section-item" key={"r" + i}>
          <div className="label">Updated line · {m.match}</div>
          <textarea disabled={readOnly} value={m.text}
            onChange={(e) => set({ replace: (draft.replace || []).map((x, j) => (j === i ? { ...x, text: e.target.value } : x)) })} />
        </div>
      ))}

      {reports.map(([k, v]) => (
        <div className="section-item" key={"rep" + k}>
          <div className="label">{k}</div>
          <textarea disabled={readOnly} value={reportText(v)} rows={2}
            onChange={(e) => set({ reports: { ...draft.reports, [k]: typeof v === "string" ? e.target.value : { ...v, text: e.target.value } } })} />
        </div>
      ))}

      {!readOnly && unfilled.length > 0 && (
        <div className="section-item">
          <label>Add a topic the AI hasn't filled
            <select value="" onChange={(e) => { if (e.target.value) set({ fills: [...fills, { under: e.target.value, text: "" }] }); }}>
              <option value="">Choose a topic…</option>
              {unfilled.map((s, i) => <option key={i} value={s}>{s.slice(0, 110)}</option>)}
            </select>
          </label>
        </div>
      )}

      <div className="section-item">
        <label>Summary (one item per line)
          <textarea disabled={readOnly} rows={4} value={(draft.summary || []).join("\n")}
            onChange={(e) => set({ summary: e.target.value.split("\n") })}
            onBlur={() => set({ summary: (draft.summary || []).filter((s) => s.trim()) })} />
        </label>
      </div>
    </div>
  );
}

function ReviewPanel({ meeting, secretary, busy, send }: {
  meeting: Meeting; secretary: boolean; busy: boolean;
  send: (body: { action: string; note?: string }, done: string) => Promise<void>;
}) {
  const [note, setNote] = useState("");
  const r = meeting.review;
  const label = r.status === "requested" ? "Waiting for advisor review" : r.status === "changes" ? "Changes requested" :
    r.status === "reviewed" ? "Reviewed" : r.required ? "Needs advisor review before approval" : "Advisor review is optional";
  const cls = r.status === "reviewed" ? "ok" : r.status === "changes" ? "bad" : r.status === "requested" || r.required ? "warn" : "";
  return (
    <div className="card stack">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>Advisor review</h2>
        <span className={"badge " + cls}>{label}</span>
      </div>
      {r.status === "reviewed" && <p className="sub" style={{ margin: 0 }}>Reviewed by {r.reviewer} on {fmtDate(r.reviewed_at)}.</p>}
      {r.note && <div className={"alert " + (r.status === "changes" ? "warn" : "")}>{r.status === "changes" && r.reviewer ? r.reviewer + ": " : ""}{r.note}</div>}
      {r.can_review && r.status !== "reviewed" && (
        <>
          <label>Notes for the secretary (needed when asking for changes)
            <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add the vote count for item 4" />
          </label>
          <div className="row">
            <button className="primary" disabled={busy} onClick={() => void send({ action: "reviewed", note }, "Marked as reviewed.").then(() => setNote(""))}>Mark reviewed</button>
            <button disabled={busy || !note.trim()} onClick={() => void send({ action: "changes", note }, "Changes requested.").then(() => setNote(""))}>Ask for changes</button>
          </div>
        </>
      )}
      {secretary && !r.can_review && r.status !== "requested" && r.status !== "reviewed" && r.has_reviewers && (
        <div className="row">
          <button className="primary" disabled={busy} onClick={() => void send({ action: "request" }, "Sent for review.")}>
            {r.status === "changes" ? "Send back for review" : "Send for advisor review"}
          </button>
        </div>
      )}
    </div>
  );
}
