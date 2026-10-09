import { useState, type FormEvent } from "react";
import { useExamples } from "../examples";
import { Link, useNavigate } from "react-router-dom";
import { api, type AIConn, type Meeting, type Org, type Template } from "../api";
import { useSession } from "../session";
import { ErrorBox, errText, useLoad } from "../ui";
import { holidayOn, isoDay, seriesDays } from "../holidays";

interface Unresolved { id: string; text: string; under: string; result: string; mover: string; meeting_id: string; meeting_title: string; meeting_date: string }

export default function NewMeeting() {
  const { org } = useSession();
  const ex = useExamples();
  const navigate = useNavigate();
  const base = "/api/orgs/" + org!.id;
  const tpls = useLoad(() => api.get<{ templates: Template[] }>(base + "/templates"), [base]);
  const conns = useLoad(() => api.get<{ connections: AIConn[] }>(base + "/ai"), [base]);
  const info = useLoad(() => api.get<Org>(base), [base]);
  const open = useLoad(() => api.get<{ items: Unresolved[] }>(base + "/unresolved"), [base]);
  const [carry, setCarry] = useState<Record<string, boolean>>({});
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [connId, setConnId] = useState("");
  const [mode, setMode] = useState<"live" | "after">("live");
  const [notes, setNotes] = useState("");
  const [timing, setTiming] = useState<"now" | "later">("now");
  const [day, setDay] = useState("");
  const [time, setTime] = useState("14:00");
  const [duration, setDuration] = useState(60);
  const [zoom, setZoom] = useState("");
  const [place, setPlace] = useState("");
  const [repeat, setRepeat] = useState("none");
  const [until, setUntil] = useState("");
  const clashes = !day ? [] : (repeat === "none" ? [new Date(day + "T12:00")] : seriesDays(day, repeat, until))
    .map((d) => ({ name: holidayOn(isoDay(d)), label: d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }) }))
    .filter((c) => c.name);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [told, setTold] = useState(false);

  const templates = (tpls.data?.templates || []).filter((t) => t.purpose !== "example");
  const connections = conns.data?.connections || [];
  const fallback = templates.find((t) => t.id === info.data?.default_template_id)?.id || templates[0]?.id || "";
  const chosenTemplate = templateId || (file ? "" : fallback);
  const chosenConn = connId || connections[0]?.id || "";
  const freeChosen = !!connections.find((c) => c.id === chosenConn)?.free;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      let tid = chosenTemplate;
      if (file) {
        const form = new FormData();
        form.append("file", file);
        form.append("name", file.name.replace(/\.[^.]+$/, ""));
        form.append("title", title);
        form.append("date", date);
        tid = (await api.post<Template>(base + "/templates", form)).id;
      }
      if (!tid) throw new Error("choose or upload a template or agenda");
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      const carried = (open.data?.items || []).filter((m) => carry[m.id] ?? m.result === "tabled");
      const carryNotes = carried.length
        ? "UNRESOLVED FROM EARLIER MEETINGS (bring these up under unfinished business and record what happens to each):\n"
          + carried.map((m) => "- " + m.text + (m.mover ? " (moved by " + m.mover + ")" : "") + ", "
            + (m.result === "tabled" ? "tabled" : "no result recorded") + " at " + m.meeting_title
            + (m.meeting_date ? ", " + m.meeting_date : "")).join("\n")
        : "";
      const allNotes = [notes.trim(), carryNotes].filter(Boolean).join("\n\n");
      const common = { title, template_id: tid, ai_connection_id: chosenConn || null, run_mode: mode, notes: allNotes,
        duration_min: duration, zoom_url: zoom, location: place, notice_ack: told };
      if (timing === "later") {
        if (!day) throw new Error("choose the date");
        const first = new Date(day + "T" + time);
        if (repeat !== "none") {
          const weekday = (first.getDay() + 6) % 7;
          const nth = Math.floor((first.getDate() - 1) / 7) + 1;
          await api.post(base + "/series", {
            ...common, frequency: repeat.startsWith("monthly") ? "monthly" : "weekly", interval: repeat === "biweekly" ? 2 : 1,
            weekdays: [weekday], month_week: repeat === "monthly_last" || nth > 4 ? -1 : nth, month_weekday: weekday,
            start_date: day, start_time: time, timezone: tz, until_date: until
          });
          navigate("/dashboard");
          return;
        }
        const mt = await api.post<Meeting>(base + "/meetings", { ...common, scheduled_at: first.getTime() / 1000, timezone: tz });
        navigate("/meetings/" + mt.id);
        return;
      }
      const mt = await api.post<Meeting>(base + "/meetings", { ...common, meeting_date: date });
      navigate("/meetings/" + mt.id);
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <div className="kicker">Open a new file</div>
          <h1>New meeting</h1>
          <p className="sub">Pick the notes document, the AI, and how the draft should update.</p>
        </div>
      </div>
      <form className="card stack" style={{ maxWidth: 760 }} onSubmit={submit}>
        <div className="grid-2">
          <label>Title<input required value={title} onChange={(e) => setTitle(e.target.value)} placeholder={ex.meetingTitle} /></label>
          {timing === "now" && <label>Date and time<input value={date} onChange={(e) => setDate(e.target.value)} placeholder="October 7, 2026; 9:00 a.m." /></label>}
        </div>

        <div className="stack">
          <h3>When</h3>
          <div className="choice">
            <button type="button" className={timing === "now" ? "on" : ""} aria-pressed={timing === "now"} onClick={() => setTiming("now")}>Starting now</button>
            <button type="button" className={timing === "later" ? "on" : ""} aria-pressed={timing === "later"} onClick={() => setTiming("later")}>Schedule for later</button>
          </div>
          {timing === "later" && (
            <div className="grid-2">
              <label>Date<input type="date" value={day} onChange={(e) => setDay(e.target.value)} /></label>
              <label>Start time<input type="time" value={time} onChange={(e) => setTime(e.target.value)} /></label>
              <label>Length in minutes<input type="number" min={5} max={600} value={duration} onChange={(e) => setDuration(Number(e.target.value))} /></label>
              <label>Repeats
                <select value={repeat} onChange={(e) => setRepeat(e.target.value)}>
                  <option value="none">Does not repeat</option>
                  <option value="weekly">Every week on this day</option>
                  <option value="biweekly">Every two weeks on this day</option>
                  <option value="monthly">Monthly on this week and day</option>
                  <option value="monthly_last">Monthly on the last one of this day</option>
                </select>
              </label>
              {repeat !== "none" && <label>Last meeting on (optional)<input type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></label>}
            </div>
          )}
          {timing === "later" && clashes.length > 0 && (
            <div className="alert warn" role="status">
              {clashes.length === 1 && repeat === "none"
                ? clashes[0].label + " is " + clashes[0].name + ". Many colleges are closed that day, so check that your room and members are available."
                : "This series lands on " + clashes.length + " holiday" + (clashes.length === 1 ? "" : "s") + " when many colleges are closed: "
                  + clashes.slice(0, 6).map((c) => c.label + " (" + c.name + ")").join(", ") + (clashes.length > 6 ? ", and more" : "")
                  + ". Skip or move those meetings after you create the series."}
            </div>
          )}
          <div className="grid-2">
            <label>Zoom link (optional)<input value={zoom} onChange={(e) => setZoom(e.target.value)} placeholder="https://zoom.us/j/123456789" /></label>
            <label>Room or place (optional)<input value={place} onChange={(e) => setPlace(e.target.value)} placeholder={ex.place} /></label>
          </div>
          {timing === "later" && <p className="sub" style={{ margin: 0 }}>Times use your time zone ({Intl.DateTimeFormat().resolvedOptions().timeZone}).
            Captions from the desktop app or extension start the meeting automatically when it begins.</p>}
        </div>

        <div className="stack">
          <h3>Notes document</h3>
          {templates.length > 0 && (
            <label>Saved template
              <select value={file ? "" : chosenTemplate} onChange={(e) => { setTemplateId(e.target.value); setFile(null); }}>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>{t.name} {t.mode === "generated" ? "(generated from topics)" : ""}</option>
                ))}
              </select>
            </label>
          )}
          <label>{templates.length ? "Or upload a new one" : "Upload"}: agenda or minutes template (.docx keeps its format), or a list of topics (.pdf, .txt)
            <input type="file" accept=".docx,.pdf,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </label>
        </div>

        <div className="stack">
          <h3>AI</h3>
          {connections.length === 0 ? (
            <div className="alert warn">No AI connection yet. <Link to="/settings">Add one in Settings</Link>, or continue and add it later.</div>
          ) : (
            <label>AI connection
              <select value={chosenConn} onChange={(e) => setConnId(e.target.value)}>
                {connections.map((c) => <option key={c.id} value={c.id}>{c.free ? c.label : c.label + " · " + c.model}</option>)}
              </select>
            </label>
          )}
          {freeChosen && (
            <div className="alert">The free AI is free for everyone but slow: it drafts after the meeting ends and takes about 15 to 40 minutes
              for an hour-long meeting, longer if other meetings are in line. Live updates during the meeting need your own AI under Settings, AI.
              You will get a notification when the draft is ready.</div>
          )}
        </div>


        <div className="stack">
          <h3>Mode</h3>
          <div className="choice">
            <button type="button" className={mode === "live" ? "on" : ""} aria-pressed={mode === "live"} onClick={() => setMode("live")}>
              Live: update the draft during the meeting
            </button>
            <button type="button" className={mode === "after" ? "on" : ""} aria-pressed={mode === "after"} onClick={() => setMode("after")}>
              After: fill everything in when it ends
            </button>
          </div>
        </div>

        <div className="alert" role="note">Before captions start, tell everyone that the meeting is being captured for minutes. Do not capture closed sessions or
          confidential discussions. See the <a href="/terms" target="_blank" rel="noreferrer">Terms of use</a>.</div>

        {(open.data?.items || []).length > 0 && (
          <fieldset className="card stack">
            <legend>Unresolved from earlier meetings</legend>
            <p className="sub" style={{ margin: 0 }}>Tabled motions and motions with no recorded result. Checked items are added to this meeting's
              notes, so the draft lists them under unfinished business.</p>
            {(open.data?.items || []).map((m) => (
              <label key={m.id} className="setting-row">
                <span>{m.text}<br />
                  <span className="sub">{m.result === "tabled" ? "Tabled" : "No result recorded"} · {m.meeting_title}{m.meeting_date ? " · " + m.meeting_date : ""}</span>
                </span>
                <input type="checkbox" checked={carry[m.id] ?? m.result === "tabled"}
                  onChange={(e) => setCarry({ ...carry, [m.id]: e.target.checked })} />
              </label>
            ))}
          </fieldset>
        )}

        <label>Notes for the AI (optional)
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
            placeholder={ex.notes} />
        </label>
        <label className="row" style={{ textTransform: "none", letterSpacing: "normal", alignItems: "flex-start" }}>
          <input type="checkbox" checked={told} onChange={(e) => setTold(e.target.checked)} required style={{ marginTop: 4 }} />
          <span>I will tell everyone at the start that captions, the transcript, and chat are being captured for minutes, and I will not
            capture closed sessions or anyone who has not been told. <Link to="/terms" target="_blank">Recording rules</Link></span>
        </label>
        <ErrorBox error={error || tpls.error || conns.error} />
        <div className="row">
          <button className="primary" disabled={busy || !told}>{busy ? "Saving…" : timing === "later" ? (repeat === "none" ? "Schedule meeting" : "Schedule meetings") : "Create meeting"}</button>
          <Link className="btn" to="/dashboard">Cancel</Link>
        </div>
      </form>
    </>
  );
}
