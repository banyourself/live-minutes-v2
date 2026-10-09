import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { useExamples } from "../examples";
import { ErrorBox, errText } from "../ui";

type Align = "left" | "center" | "right";
export interface DesignStyle {
  font: string; accent: string; title_align: Align; subtitle_align: Align; date_align: Align; heading_align: Align;
  heading_style: "rule" | "band" | "plain" | "caps" | "tint"; numbering: "decimal" | "roman" | "letter" | "lower";
  title_size: number; body_size: number; bold_items: boolean; title_rule: boolean;
  title_block: "classic" | "banner" | "masthead"; section_numbers: boolean; accent_numbers: boolean;
}
export interface Design {
  name: string; title: string; subtitle: string; topics: string[]; attendance: boolean; action_items: boolean; summary: boolean;
  details: boolean; signatures: boolean; footer: boolean; intro: string; closing: string;
  date_label: string; first_item: string; opening_line: string; last_item: string; attendance_heading: string; present_label: string;
  absent_label: string; agenda_heading: string; action_heading: string; summary_heading: string; summary_lead: string;
  details_date: string; details_start: string; details_end: string; details_place: string; approval_heading: string;
  sign_first: string; sign_second: string; style: DesignStyle;
}

export const DEFAULT_STYLE: DesignStyle = { font: "Calibri", accent: "1F3A5F", title_align: "left", subtitle_align: "left", date_align: "left",
  heading_align: "left", heading_style: "rule", numbering: "decimal", title_size: 20, body_size: 11, bold_items: true, title_rule: false,
  title_block: "classic", section_numbers: false, accent_numbers: false };

export function blankDesign(name: string, title: string, topics: string[] = []): Design {
  return { name, title, subtitle: "", topics, attendance: true, action_items: true, summary: true, details: false, signatures: false,
    footer: false, intro: "", closing: "", date_label: "Date:", first_item: "Call to Order", opening_line: "Meeting called to order at .",
    last_item: "Adjournment", attendance_heading: "Attendance", present_label: "Present:", absent_label: "Absent:", agenda_heading: "Agenda",
    action_heading: "Action Items", summary_heading: "Summary", summary_lead: "Key Items Discussed/Actions Taken", details_date: "Date",
    details_start: "Called to order", details_end: "Adjourned", details_place: "Location", approval_heading: "Approval",
    sign_first: "Recording secretary", sign_second: "Presiding officer", style: { ...DEFAULT_STYLE } };
}

const INK = "1F2328";
const channels = (hex: string) => [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
function luminance(hex: string) {
  const [r, g, b] = channels(hex).map((c) => c / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a: string, b: string) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}
export const tint = (hex: string, amount: number) =>
  channels(hex).map((c) => Math.round(255 - (255 - c) * amount).toString(16).padStart(2, "0")).join("").toUpperCase();
const inkOn = (fill: string) => (contrast("FFFFFF", fill) >= 4.5 ? "FFFFFF" : INK);
const readable = (color: string, fill: string) => (contrast(color, fill) >= 4.5 ? color : INK);

export function withDefaults(d: Partial<Design>): Design {
  const base = blankDesign(d.name || "", d.title || "");
  return { ...base, ...d, topics: d.topics || [], style: { ...DEFAULT_STYLE, ...(d.style || {}) } } as Design;
}

const FONTS: Record<string, string> = {
  Calibri: "Calibri, Carlito, 'Segoe UI', sans-serif", Aptos: "Aptos, 'Segoe UI', Arial, sans-serif", Arial: "Arial, Helvetica, sans-serif",
  Verdana: "Verdana, Geneva, sans-serif", Georgia: "Georgia, serif", "Times New Roman": "'Times New Roman', Times, serif",
  Garamond: "Garamond, 'EB Garamond', Georgia, serif", Cambria: "Cambria, Georgia, serif"
};
const NUMBERS: Record<string, string> = { decimal: "decimal", roman: "upper-roman", letter: "upper-alpha", lower: "lower-alpha" };
const FIXED = ["call to order", "adjournment", "adjourn", "meeting adjourned"];

export async function downloadFile(url: string, body: unknown, fallback: string) {
  const res = await fetch(url, body === undefined ? { credentials: "include" } : {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-Live-Minutes": "1" }, body: JSON.stringify(body)
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { detail = res.statusText; }
    throw new Error(typeof detail === "string" ? detail : "please check the form");
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") || "")?.[1] || fallback;
  const link = document.createElement("a");
  link.href = URL.createObjectURL(await res.blob());
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

type TextKey = "title" | "subtitle" | "date_label" | "first_item" | "opening_line" | "last_item" | "attendance_heading" | "present_label"
  | "absent_label" | "agenda_heading" | "action_heading" | "summary_heading" | "summary_lead" | "details_date" | "details_start"
  | "details_end" | "details_place" | "approval_heading" | "sign_first" | "sign_second" | "intro" | "closing";
type AlignKey = "title_align" | "subtitle_align" | "date_align" | "heading_align";
type SectionKey = "details" | "attendance" | "action_items" | "summary" | "signatures" | "footer";
type NoteKey = "intro" | "closing";

export interface PaperEdit {
  text: (key: TextKey, value: string) => void;
  topic: (i: number, value: string) => void;
  moveTopic: (from: number, to: number) => void;
  removeTopic: (i: number) => void;
  addTopic: () => void;
  toggle: (key: SectionKey, on: boolean) => void;
  note: (key: NoteKey, on: boolean) => void;
  notes: Record<NoteKey, boolean>;
  focus: (align: AlignKey | null) => void;
  begin: () => void;
  fresh: number | null;
}

function Editable({ value, onChange, label, max = 160, multiline, onFocus, autoFocus }: {
  value: string; onChange: (v: string) => void; label: string; max?: number; multiline?: boolean; onFocus?: () => void; autoFocus?: boolean;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const clean = (raw: string) => (multiline ? raw.replace(/\n{3,}/g, "\n\n") : raw.replace(/\s+/g, " ")).slice(0, max);
  const mark = (el: HTMLElement) => { el.dataset.empty = String(!el.innerText.trim()); };
  useLayoutEffect(() => {
    const el = ref.current;
    if (el && document.activeElement !== el && el.innerText !== value) el.innerText = value;
    if (el) mark(el);
  }, [value]);
  useEffect(() => {
    const el = ref.current;
    if (autoFocus && el) {
      el.focus();
      document.getSelection()?.selectAllChildren(el);
    }
  }, [autoFocus]);
  return (
    <span ref={ref} className={"pe-text" + (multiline ? " pe-multi" : "")} role="textbox" aria-label={label} aria-multiline={multiline || undefined}
      tabIndex={0} contentEditable="plaintext-only" suppressContentEditableWarning spellCheck data-placeholder={label} onFocus={onFocus}
      onInput={(e) => { mark(e.currentTarget); onChange(clean(e.currentTarget.innerText)); }}
      onKeyDown={(e) => {
        if ((e.key === "Enter" && !multiline) || e.key === "Escape") { e.preventDefault(); e.currentTarget.blur(); }
      }}
      onBlur={(e) => {
        const el = e.currentTarget;
        const v = clean(el.innerText).trim();
        if (el.innerText !== v) el.innerText = v;
        mark(el);
        onChange(v);
      }} />
  );
}

export function Paper({ d, mini, edit }: { d: Design; mini?: boolean; edit?: PaperEdit }) {
  const [drag, setDrag] = useState<number | null>(null);
  const [over, setOver] = useState<number | null>(null);
  const st = { ...DEFAULT_STYLE, ...d.style };
  const hex = st.accent;
  const accent = "#" + hex;
  const skip = [...FIXED, d.first_item.toLowerCase(), d.last_item.toLowerCase()];
  const topics = d.topics.map((t) => t.trim()).filter((t) => t && !skip.includes(t.toLowerCase().replace(/[.:]+$/, "")));
  const title = d.title || "Meeting Minutes";
  const head: CSSProperties = { textAlign: st.heading_align, color: accent, fontWeight: 700, margin: "14px 0 6px", padding: "2px 0" };
  if (st.heading_style === "rule") Object.assign(head, { borderBottom: "1px solid " + accent });
  if (st.heading_style === "band") Object.assign(head, { background: accent, color: "#" + inkOn(hex), padding: "3px 8px" });
  if (st.heading_style === "caps") Object.assign(head, { textTransform: "uppercase", letterSpacing: "0.08em", fontSize: "0.92em" });
  if (st.heading_style === "tint") {
    const fill = tint(hex, 0.12);
    Object.assign(head, { background: "#" + fill, color: "#" + readable(hex, fill), borderLeft: "3px solid " + accent, padding: "2px 8px" });
  }
  const sections = [d.attendance && "attendance", "agenda", d.action_items && "action", d.summary && "summary", d.signatures && "approval"]
    .filter(Boolean);
  const T = (key: TextKey, label: string, opts: { max?: number; align?: AlignKey; multiline?: boolean } = {}) => edit ? (
    <Editable value={d[key]} label={label} max={opts.max} multiline={opts.multiline} onChange={(v) => edit.text(key, v)}
      onFocus={() => { edit.begin(); edit.focus(opts.align || null); }} />
  ) : d[key];
  const h = (k: string, key: TextKey, label: string) => (
    <div style={head}>
      {st.section_numbers && <span style={{ fontWeight: 400, marginRight: "0.7em" }}>{String(sections.indexOf(k) + 1).padStart(2, "0")}</span>}
      {T(key, label, { align: "heading_align" })}
    </div>
  );
  const block = (label: string, off: () => void, children: ReactNode) => edit ? (
    <div className="pe-block">
      {children}
      <button type="button" className="pe-remove" aria-label={"Remove " + label} onClick={off}>Remove</button>
    </div>
  ) : children;
  const note = (key: NoteKey, label: string, style: CSSProperties) => (d[key] || (edit && edit.notes[key])) ? block(label, () => edit?.note(key, false), (
    <div className="paper-note" style={style}>{edit ? T(key, label, { max: 600, multiline: true }) : d[key]}</div>
  )) : null;
  const titleText: CSSProperties = { textAlign: st.title_align, color: accent, fontWeight: 700, fontSize: st.title_size * 1.25 + "px", lineHeight: 1.2 };
  const masthead = st.title_block === "masthead";
  const ink = "#" + inkOn(hex);
  const showSub = !!d.subtitle || !!edit;
  const weight = { fontWeight: st.bold_items ? 700 : 400 };
  const blank = (text: string) => <li className="paper-blank">{text}</li>;
  return (
    <div className={"paper" + (mini ? " mini" : "") + (edit ? " editing" : "")} aria-label={mini ? undefined : edit ? "Template page" : "Preview of the document"}
      aria-hidden={mini || undefined} style={{ fontFamily: FONTS[st.font] || FONTS.Calibri, fontSize: st.body_size * 1.2 + "px" }}>
      {st.title_block === "banner" ? (
        <div style={{ background: accent, color: ink, padding: "10px 12px", marginBottom: 8 }}>
          <div style={{ ...titleText, color: ink }}>{edit ? T("title", "Title", { max: 200, align: "title_align" }) : title}</div>
          {showSub && <div style={{ textAlign: st.subtitle_align, marginTop: 2 }}>{T("subtitle", "Line under the title", { max: 200, align: "subtitle_align" })}</div>}
        </div>
      ) : (
        <>
          <div style={{ ...titleText, borderTop: masthead ? "5px solid " + accent : undefined, paddingTop: masthead ? 8 : 0,
            borderBottom: st.title_rule ? "2px solid " + accent : undefined, paddingBottom: st.title_rule ? 6 : 0 }}>
            {edit ? T("title", "Title", { max: 200, align: "title_align" }) : title}</div>
          {showSub && <div style={{ textAlign: st.subtitle_align, color: "#444", marginTop: 4, textTransform: masthead ? "uppercase" : undefined,
            letterSpacing: masthead ? "0.08em" : undefined, fontSize: masthead ? "0.9em" : undefined }}>
            {T("subtitle", "Line under the title", { max: 200, align: "subtitle_align" })}</div>}
        </>
      )}
      {note("intro", "Note under the title", { textAlign: st.subtitle_align })}
      {d.details ? block("the meeting details table", () => edit?.toggle("details", false), (
        <div className="paper-details" style={{ "--marker": accent, "--tint": "#" + tint(hex, 0.1) } as CSSProperties}>
          {([["details_date", "Date column"], ["details_start", "Start column"], ["details_end", "End column"], ["details_place", "Location column"]] as [TextKey, string][])
            .map(([key, label]) => <span key={key} className="paper-label">{T(key, label)}</span>)}
          {["Meeting date", "Time", "Time", "Room or Zoom"].map((t, i) => <span key={"v" + i} className="paper-blank">{t}</span>)}
        </div>
      )) : <div style={{ textAlign: st.date_align, color: "#555", margin: "4px 0 6px" }}>{T("date_label", "Date line", { align: "date_align" })}</div>}
      {d.attendance && block("the attendance section", () => edit?.toggle("attendance", false), (
        <>{h("attendance", "attendance_heading", "Attendance heading")}
          <ul className="paper-bullets"><li>{T("present_label", "Present line")}</li><li>{T("absent_label", "Absent line")}</li></ul></>
      ))}
      {h("agenda", "agenda_heading", "Agenda heading")}
      <ol className={"paper-agenda" + (st.accent_numbers ? " accent-markers" : "")}
        style={{ listStyleType: NUMBERS[st.numbering], "--marker": accent } as CSSProperties}>
        <li><span style={weight}>{T("first_item", "First agenda item", { max: 120 })}</span>
          <ul className="paper-bullets"><li>{T("opening_line", "Line under the first item")}</li></ul></li>
        {edit ? d.topics.map((t, i) => (
          <li key={i} className={"pe-item" + (over === i && drag !== null && drag !== i ? " pe-over" : "")}
            onDragOver={(e) => { if (drag !== null) { e.preventDefault(); setOver(i); } }}
            onDrop={(e) => { e.preventDefault(); if (drag !== null && drag !== i) edit.moveTopic(drag, i); setDrag(null); setOver(null); }}>
            <span className="pe-handle" draggable aria-hidden="true" title="Drag to move"
              onDragStart={(e) => { setDrag(i); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", String(i)); }}
              onDragEnd={() => { setDrag(null); setOver(null); }}>⠿</span>
            <span style={weight}><Editable value={t} label={"Agenda topic " + (i + 1)} max={120} autoFocus={edit.fresh === i}
              onChange={(v) => edit.topic(i, v)} onFocus={() => { edit.begin(); edit.focus(null); }} /></span>
            <span className="pe-tools">
              <button type="button" aria-label={"Move " + (t || "this topic") + " up"} disabled={i === 0} onClick={() => edit.moveTopic(i, i - 1)}>↑</button>
              <button type="button" aria-label={"Move " + (t || "this topic") + " down"} disabled={i === d.topics.length - 1}
                onClick={() => edit.moveTopic(i, i + 1)}>↓</button>
              <button type="button" aria-label={"Remove " + (t || "this topic")} onClick={() => edit.removeTopic(i)}>✕</button>
            </span>
            <ul className="paper-bullets">{blank("The AI writes this part")}</ul>
          </li>
        )) : topics.map((t, i) => (
          <li key={i}><span style={weight}>{t}</span><ul className="paper-bullets">{blank("The AI writes this part")}</ul></li>
        ))}
        <li><span style={weight}>{T("last_item", "Last agenda item", { max: 120 })}</span>
          <ul className="paper-bullets">{blank("The AI writes this part")}</ul></li>
      </ol>
      {edit && <button type="button" className="pe-add" disabled={d.topics.length >= 60} onClick={edit.addTopic}>+ Add a topic</button>}
      {d.action_items && block("the action items section", () => edit?.toggle("action_items", false), (
        <>{h("action", "action_heading", "Action items heading")}<ul className="paper-bullets">{blank("Who does what, by when")}</ul></>
      ))}
      {d.summary && block("the summary section", () => edit?.toggle("summary", false), (
        <>{h("summary", "summary_heading", "Summary heading")}<div className="paper-strong">{T("summary_lead", "First line of the summary")}</div></>
      ))}
      {d.signatures && block("the signature lines", () => edit?.toggle("signatures", false), (
        <>
          {h("approval", "approval_heading", "Approval heading")}
          {([["sign_first", "First signer"], ["sign_second", "Second signer"]] as [TextKey, string][]).map(([key, label]) => (
            <div key={key} className="paper-signer"><div className="paper-sign" /><strong>{T(key, label)}</strong> <span className="paper-muted">Signature and date</span></div>
          ))}
        </>
      ))}
      {note("closing", "Closing note", {})}
      {d.footer && block("the page footer", () => edit?.toggle("footer", false), (
        <div className="paper-foot" style={{ borderTopColor: "#" + tint(hex, 0.45) }}><span>{title}</span><span>Page 1 of 1</span></div>
      ))}
    </div>
  );
}

function Seg<T extends string>({ label, value, options, onPick }: { label: string; value: T; options: [T, string][]; onPick: (v: T) => void }) {
  return (
    <div className="seg-wrap">
      <span className="lbl">{label}</span>
      <div className="seg" role="group" aria-label={label}>
        {options.map(([v, text]) => (
          <button key={v} type="button" className={value === v ? "on" : ""} aria-pressed={value === v} onClick={() => onPick(v)}>{text}</button>
        ))}
      </div>
    </div>
  );
}

const ALIGNS: [Align, string][] = [["left", "Left"], ["center", "Center"], ["right", "Right"]];
const ALIGN_NAMES: Record<AlignKey, string> = { title_align: "title", subtitle_align: "line under the title", date_align: "date line",
  heading_align: "headings" };
const HEADINGS: [DesignStyle["heading_style"], string][] = [["rule", "Underlined"], ["band", "Color band"], ["tint", "Tinted"], ["plain", "Plain"],
  ["caps", "Small caps"]];
const NUMBER_STYLES: [DesignStyle["numbering"], string][] = [["decimal", "1. 2. 3."], ["roman", "I. II. III."], ["letter", "A. B. C."],
  ["lower", "a) b) c)"]];
const BLOCKS: [DesignStyle["title_block"], string][] = [["classic", "Classic"], ["banner", "Color banner"], ["masthead", "Masthead"]];
const ADDABLE: [SectionKey | NoteKey, string][] = [["details", "Meeting details"], ["attendance", "Attendance"], ["action_items", "Action items"],
  ["summary", "Summary"], ["signatures", "Signature lines"], ["footer", "Page footer"], ["intro", "Note under the title"], ["closing", "Closing note"]];

function Stepper({ label, value, min, max, onPick }: { label: string; value: number; min: number; max: number; onPick: (v: number) => void }) {
  return (
    <div className="pe-group" role="group" aria-label={label}>
      <span className="lbl">{label}</span>
      <button type="button" aria-label={"Smaller " + label.toLowerCase()} disabled={value <= min} onClick={() => onPick(value - 1)}>−</button>
      <span className="pe-value" aria-live="polite">{value} pt</span>
      <button type="button" aria-label={"Larger " + label.toLowerCase()} disabled={value >= max} onClick={() => onPick(value + 1)}>+</button>
    </div>
  );
}

const same = (a: Design, b: Design) => JSON.stringify(a) === JSON.stringify(b);

export default function TemplateDesigner({ start, heading, saveLabel, onSave, onClose, fonts }: {
  start: Design; heading: string; saveLabel: string; onSave: (d: Design) => Promise<void>; onClose: () => void; fonts?: string[];
}) {
  const ex = useExamples();
  const [d, setD] = useState<Design>(withDefaults(start));
  const [mode, setMode] = useState<"page" | "form">("page");
  const [past, setPast] = useState<Design[]>([]);
  const [future, setFuture] = useState<Design[]>([]);
  const [target, setTarget] = useState<AlignKey>("title_align");
  const [notes, setNotes] = useState<Record<NoteKey, boolean>>({ intro: false, closing: false });
  const [fresh, setFreshTopic] = useState<number | null>(null);
  const [newTopic, setNewTopic] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const top = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setD(withDefaults(start));
    setPast([]);
    setFuture([]);
    setNotes({ intro: false, closing: false });
    top.current?.scrollIntoView({ block: "start", behavior: "smooth" });
    top.current?.focus();
  }, [start]);

  const st = d.style;
  const snapshot = () => {
    setPast((p) => (p.length && same(p[p.length - 1], d) ? p : [...p.slice(-49), d]));
    setFuture([]);
  };
  const commit = (next: Design) => { snapshot(); setD(next); };
  const set = (patch: Partial<Design>) => setD({ ...d, ...patch });
  const style = (patch: Partial<DesignStyle>) => setD({ ...d, style: { ...d.style, ...patch } });
  const restyle = (patch: Partial<DesignStyle>) => commit({ ...d, style: { ...d.style, ...patch } });
  const moveTo = (topics: string[], from: number, to: number) => {
    const next = [...topics];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    return next;
  };
  const undo = () => {
    if (!past.length) return;
    setFuture([d, ...future]);
    setD(past[past.length - 1]);
    setPast(past.slice(0, -1));
  };
  const redo = () => {
    if (!future.length) return;
    setPast([...past, d]);
    setD(future[0]);
    setFuture(future.slice(1));
  };
  const editApi: PaperEdit = {
    text: (key, value) => setD((cur) => ({ ...cur, [key]: value })),
    topic: (i, value) => setD((cur) => ({ ...cur, topics: cur.topics.map((t, j) => (j === i ? value : t)) })),
    moveTopic: (from, to) => {
      if (to < 0 || to >= d.topics.length) return;
      setFreshTopic(null);
      commit({ ...d, topics: moveTo(d.topics, from, to) });
    },
    removeTopic: (i) => { setFreshTopic(null); commit({ ...d, topics: d.topics.filter((_, j) => j !== i) }); },
    addTopic: () => { commit({ ...d, topics: [...d.topics, ""] }); setFreshTopic(d.topics.length); },
    toggle: (key, on) => commit({ ...d, [key]: on }),
    note: (key, on) => { setNotes({ ...notes, [key]: on }); if (!on) commit({ ...d, [key]: "" }); },
    notes,
    focus: (align) => { if (align) setTarget(align); },
    begin: snapshot,
    fresh,
  };
  const addable = ADDABLE.filter(([key]) => (key === "intro" || key === "closing" ? !d[key] && !notes[key] : !d[key]));
  const shortcuts = (e: KeyboardEvent<HTMLDivElement>) => {
    const el = e.target as HTMLElement;
    if (!(e.ctrlKey || e.metaKey) || el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)) return;
    const key = e.key.toLowerCase();
    if (key === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
    if (key === "y" || (key === "z" && e.shiftKey)) { e.preventDefault(); redo(); }
  };
  const topicAt = (i: number, value: string) => set({ topics: d.topics.map((t, j) => j === i ? value : t) });
  const addTopic = () => { const v = newTopic.trim(); if (v) { set({ topics: [...d.topics, v] }); setNewTopic(""); } };
  const text = (key: keyof Design, label: string, hint?: string) => (
    <label>{label}<input value={String(d[key] ?? "")} maxLength={160} onChange={(e) => set({ [key]: e.target.value } as Partial<Design>)} />
      {hint && <span className="hint">{hint}</span>}</label>
  );
  const area = (key: NoteKey, label: string) => (
    <label>{label}<textarea value={d[key]} maxLength={600} rows={2} onChange={(e) => set({ [key]: e.target.value })} /></label>
  );

  async function act(label: string, fn: () => Promise<void>) {
    setBusy(label); setError("");
    try { await fn(); } catch (e) { setError(errText(e)); } finally { setBusy(""); }
  }

  const actions = (
    <>
      <ErrorBox error={error} />
      <div className="row">
        <button className="primary" disabled={!!busy || !d.topics.some((t) => t.trim())} onClick={() => void act("save", () => onSave(d))}>
          {busy === "save" ? "Saving…" : saveLabel}</button>
        <button disabled={!!busy} onClick={() => void act("word", () => downloadFile("/api/templates/preview", d, "template.docx"))}>
          {busy === "word" ? "Making…" : "Download as Word"}</button>
      </div>
    </>
  );

  return (
    <div className="card stack" ref={top} tabIndex={-1} aria-label={heading}>
      <div className="row spread">
        <h2 style={{ margin: 0 }}>{heading}</h2>
        <button className="link" onClick={onClose}>Close</button>
      </div>
      <Seg label="Editor" value={mode} onPick={setMode} options={[["page", "Edit on the page"], ["form", "Form and preview"]]} />
      {mode === "page" ? (
        <div className="pe-wrap" onKeyDown={shortcuts}>
          <div className="pe-toolbar" role="toolbar" aria-label="Template formatting">
            <div className="pe-group">
              <button type="button" disabled={!past.length} onClick={undo} aria-label="Undo" title="Undo (Ctrl+Z)">↶ Undo</button>
              <button type="button" disabled={!future.length} onClick={redo} aria-label="Redo" title="Redo (Ctrl+Y)">↷ Redo</button>
            </div>
            <label className="pe-group"><span className="lbl">Font</span>
              <select value={st.font} onChange={(e) => restyle({ font: e.target.value })}>
                {(fonts || Object.keys(FONTS)).map((f) => <option key={f} value={f}>{f}</option>)}</select></label>
            <label className="pe-group"><span className="lbl">Color</span>
              <input type="color" value={"#" + st.accent} onChange={(e) => restyle({ accent: e.target.value.slice(1).toUpperCase() })} /></label>
            <Stepper label="Text size" value={st.body_size} min={9} max={16} onPick={(v) => restyle({ body_size: v })} />
            <Stepper label="Title size" value={st.title_size} min={14} max={40} onPick={(v) => restyle({ title_size: v })} />
            <Seg label={"Align the " + ALIGN_NAMES[target]} value={st[target]} options={ALIGNS} onPick={(v) => restyle({ [target]: v })} />
            <Seg label="Title style" value={st.title_block} options={BLOCKS} onPick={(v) => restyle({ title_block: v })} />
            <Seg label="Headings" value={st.heading_style} options={HEADINGS} onPick={(v) => restyle({ heading_style: v })} />
            <Seg label="Agenda numbers" value={st.numbering} options={NUMBER_STYLES} onPick={(v) => restyle({ numbering: v })} />
            <div className="pe-group pe-checks">
              <label><input type="checkbox" checked={st.section_numbers} onChange={(e) => restyle({ section_numbers: e.target.checked })} /> Number sections</label>
              <label><input type="checkbox" checked={st.accent_numbers} onChange={(e) => restyle({ accent_numbers: e.target.checked })} /> Color numbers</label>
              <label><input type="checkbox" checked={st.bold_items} onChange={(e) => restyle({ bold_items: e.target.checked })} /> Bold topics</label>
              <label><input type="checkbox" checked={st.title_rule} onChange={(e) => restyle({ title_rule: e.target.checked })} /> Line under title</label>
            </div>
            {addable.length > 0 && (
              <div className="pe-group pe-addbar" role="group" aria-label="Add to the page">
                <span className="lbl">Add</span>
                {addable.map(([key, label]) => (
                  <button key={key} type="button" onClick={() => (key === "intro" || key === "closing"
                    ? setNotes({ ...notes, [key]: true }) : editApi.toggle(key, true))}>+ {label}</button>
                ))}
              </div>
            )}
          </div>
          <Paper d={d} edit={editApi} />
          <p className="hint" style={{ margin: 0 }}>Click any text on the page to change it, drag the dots to reorder topics, and use Remove to take a section out.
            The gray lines show where the AI writes, so they stay in place. Keep the words "called to order at" under the first item so the AI can fill in the time.</p>
          {actions}
        </div>
      ) : (
        <div className="designer">
          <div className="stack">
            <details className="design-section" open>
              <summary>Title and date</summary>
              <div className="grid-2">
                {text("name", "Template name")}
                {text("title", "Title at the top")}
                {text("subtitle", "Line under the title (optional)")}
                {text("date_label", "Date line", d.details ? "Not shown while the meeting details table is on." : undefined)}
              </div>
              <div className="grid-3-even">
                <Seg label="Title" value={st.title_align} options={ALIGNS} onPick={(v) => style({ title_align: v })} />
                <Seg label="Line under title" value={st.subtitle_align} options={ALIGNS} onPick={(v) => style({ subtitle_align: v })} />
                <Seg label="Date" value={st.date_align} options={ALIGNS} onPick={(v) => style({ date_align: v })} />
              </div>
              <Seg label="Title style" value={st.title_block} onPick={(v) => style({ title_block: v })} options={BLOCKS} />
              {area("intro", "Note under the title (optional)")}
            </details>

            <details className="design-section" open>
              <summary>Agenda</summary>
              {text("agenda_heading", "Agenda heading")}
              <ol className="topic-list">
                <li className="row" style={{ flexWrap: "nowrap" }}>
                  <input value={d.first_item} maxLength={120} aria-label="First item" onChange={(e) => set({ first_item: e.target.value })} />
                  <span className="sub nowrap">always first</span>
                </li>
                {d.topics.map((t, i) => (
                  <li key={i} className="row" style={{ flexWrap: "nowrap" }}>
                    <input value={t} maxLength={120} aria-label={"Topic " + (i + 1)} onChange={(e) => topicAt(i, e.target.value)} />
                    <button type="button" aria-label={"Move " + (t || "topic") + " up"} disabled={i === 0}
                      onClick={() => set({ topics: moveTo(d.topics, i, i - 1) })}>↑</button>
                    <button type="button" aria-label={"Move " + (t || "topic") + " down"} disabled={i === d.topics.length - 1}
                      onClick={() => set({ topics: moveTo(d.topics, i, i + 1) })}>↓</button>
                    <button type="button" className="danger" aria-label={"Take out " + (t || "topic")}
                      onClick={() => set({ topics: d.topics.filter((_, j) => j !== i) })}>✕</button>
                  </li>
                ))}
                <li className="row" style={{ flexWrap: "nowrap" }}>
                  <input value={d.last_item} maxLength={120} aria-label="Last item" onChange={(e) => set({ last_item: e.target.value })} />
                  <span className="sub nowrap">always last</span>
                </li>
              </ol>
              <div className="row" style={{ flexWrap: "nowrap" }}>
                <input value={newTopic} maxLength={120} aria-label="New topic" placeholder={ex.topic}
                  onChange={(e) => setNewTopic(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTopic(); } }} />
                <button type="button" disabled={!newTopic.trim() || d.topics.length >= 60} onClick={addTopic}>Add</button>
              </div>
              {text("opening_line", "Line under the first item", "Keep the words \"called to order at\" so the AI can fill in the time.")}
            </details>

            <details className="design-section" open>
              <summary>Sections</summary>
              <label className="setting-row"><span>Meeting details table</span>
                <input type="checkbox" checked={d.details} onChange={(e) => set({ details: e.target.checked })} /></label>
              {d.details && (<>
                <span className="hint">Live Minutes fills in the date, start and end times, and location when it builds the Word file.</span>
                <div className="grid-2">{text("details_date", "Date column")}{text("details_start", "Start column")}
                  {text("details_end", "End column")}{text("details_place", "Location column")}</div>
              </>)}
              <label className="setting-row"><span>Attendance</span>
                <input type="checkbox" checked={d.attendance} onChange={(e) => set({ attendance: e.target.checked })} /></label>
              {d.attendance && <div className="grid-3-even">{text("attendance_heading", "Heading")}{text("present_label", "Present line")}{text("absent_label", "Absent line")}</div>}
              <label className="setting-row"><span>Action items</span>
                <input type="checkbox" checked={d.action_items} onChange={(e) => set({ action_items: e.target.checked })} /></label>
              {d.action_items && text("action_heading", "Heading")}
              <label className="setting-row"><span>Summary</span>
                <input type="checkbox" checked={d.summary} onChange={(e) => set({ summary: e.target.checked })} /></label>
              {d.summary && <div className="grid-2">{text("summary_heading", "Heading")}{text("summary_lead", "First line")}</div>}
              <label className="setting-row"><span>Signature lines</span>
                <input type="checkbox" checked={d.signatures} onChange={(e) => set({ signatures: e.target.checked })} /></label>
              {d.signatures && <div className="grid-3-even">{text("approval_heading", "Heading")}{text("sign_first", "First signer")}
                {text("sign_second", "Second signer")}</div>}
              <label className="setting-row"><span>Page footer with page numbers</span>
                <input type="checkbox" checked={d.footer} onChange={(e) => set({ footer: e.target.checked })} /></label>
              {area("closing", "Closing note (optional)")}
            </details>

            <details className="design-section" open>
              <summary>Look</summary>
              <div className="grid-2">
                <label>Font<select value={st.font} onChange={(e) => style({ font: e.target.value })}>
                  {(fonts || Object.keys(FONTS)).map((f) => <option key={f} value={f}>{f}</option>)}</select></label>
                <label>Accent color<input type="color" value={"#" + st.accent} onChange={(e) => style({ accent: e.target.value.slice(1).toUpperCase() })} /></label>
                <label>Title size ({st.title_size} pt)<input type="range" min={14} max={40} value={st.title_size} onChange={(e) => style({ title_size: Number(e.target.value) })} /></label>
                <label>Text size ({st.body_size} pt)<input type="range" min={9} max={16} value={st.body_size} onChange={(e) => style({ body_size: Number(e.target.value) })} /></label>
              </div>
              <Seg label="Headings" value={st.heading_style} onPick={(v) => style({ heading_style: v })} options={HEADINGS} />
              <Seg label="Heading position" value={st.heading_align} options={ALIGNS} onPick={(v) => style({ heading_align: v })} />
              <Seg label="Agenda numbers" value={st.numbering} onPick={(v) => style({ numbering: v })} options={NUMBER_STYLES} />
              <label className="setting-row"><span>Bold agenda items</span>
                <input type="checkbox" checked={st.bold_items} onChange={(e) => style({ bold_items: e.target.checked })} /></label>
              <label className="setting-row"><span>Line under the title</span>
                <input type="checkbox" checked={st.title_rule} onChange={(e) => style({ title_rule: e.target.checked })} /></label>
              <label className="setting-row"><span>Number the sections (01, 02, 03)</span>
                <input type="checkbox" checked={st.section_numbers} onChange={(e) => style({ section_numbers: e.target.checked })} /></label>
              <label className="setting-row"><span>Color the agenda numbers</span>
                <input type="checkbox" checked={st.accent_numbers} onChange={(e) => style({ accent_numbers: e.target.checked })} /></label>
            </details>
            {actions}
          </div>
          <div className="designer-preview">
            <h3>Preview</h3>
            <Paper d={d} />
          </div>
        </div>
      )}
    </div>
  );
}
