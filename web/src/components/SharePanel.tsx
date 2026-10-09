import { useState } from "react";
import { api } from "../api";
import { ErrorBox, errText, fmtDate, useLoad } from "../ui";

interface Translation { language: string; name: string; summary: string; created_at: number; ai: string; stale: boolean; items: number }
interface ShareData {
  translations: Translation[]; languages: { code: string; name: string }[]; quick: string[];
  summary: { text: string; at: number | null; stale: boolean };
}
interface Check { id: string; label: string; status: "pass" | "warn" | "fail"; detail: string; count: number }

export default function SharePanel({ meetingId, secretary }: { meetingId: string; secretary: boolean }) {
  const base = "/api/meetings/" + meetingId;
  const data = useLoad(() => api.get<ShareData>(base + "/translations"), [base]);
  const [lang, setLang] = useState("es");
  const [engine, setEngine] = useState<"ai" | "quick">("ai");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [report, setReport] = useState<{ passed: number; total: number; checks: Check[]; language: string } | null>(null);
  const [open, setOpen] = useState("");

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(label); setError("");
    try { await fn(); await data.reload(); } catch (e) { setError(errText(e)); } finally { setBusy(""); }
  }

  async function check(language: string) {
    setBusy("check-" + language); setError("");
    try { setReport({ ...(await api.get<{ passed: number; total: number; checks: Check[] }>(base + "/accessibility?language=" + language)), language }); }
    catch (e) { setError(errText(e)); }
    finally { setBusy(""); }
  }

  const d = data.data;
  if (!d) return <ErrorBox error={data.error} />;
  const nameOf = (code: string) => code === "en" ? "English" : d.languages.find((l) => l.code === code)?.name || code;

  return (
    <div className="stack">
      <ErrorBox error={error} />
      <div className="grid-2" style={{ alignItems: "start" }}>
        <div className="card stack">
          <div className="row spread">
            <h2 style={{ margin: 0 }}>Plain-language summary</h2>
            {d.summary.stale && <span className="badge warn">Made from an older draft</span>}
          </div>
          <p className="sub" style={{ margin: 0 }}>A short version of the minutes in everyday words, for students and the public.</p>
          {d.summary.text ? <div className="prewrap" style={{ fontFamily: "inherit", fontSize: "0.95rem" }}>{d.summary.text}</div> : <div className="empty">No summary yet.</div>}
          <div className="row">
            {secretary && <button className="primary" disabled={!!busy} onClick={() => void run("summary", () => api.post(base + "/summary"))}>
              {busy === "summary" ? "Writing…" : d.summary.text ? "Write it again" : "Write a summary"}</button>}
            {d.summary.text && <button onClick={() => void navigator.clipboard.writeText(d.summary.text)}>Copy</button>}
          </div>
          {d.summary.at && <div className="sub">Written {fmtDate(d.summary.at)}. Read it over before sharing.</div>}
        </div>
        <div className="card stack">
          <h2>Translations</h2>
          <p className="sub" style={{ margin: 0 }}>The AI translates the minutes and the summary. Names, numbers, and votes stay as written, and your template's own headings stay in English.</p>
          {secretary && d.quick.length > 0 && (
            <div className="choice">
              <button type="button" className={engine === "ai" ? "on" : ""} aria-pressed={engine === "ai"} onClick={() => setEngine("ai")}>AI translation (best)</button>
              <button type="button" className={engine === "quick" ? "on" : ""} aria-pressed={engine === "quick"} onClick={() => setEngine("quick")}>Quick translation (on our server)</button>
            </div>
          )}
          {secretary && engine === "quick" && (
            <p className="sub" style={{ margin: 0 }}>Quick translation runs on the Live Minutes server, so the minutes never leave it, and it finishes in seconds.
              It is rougher than the AI: read names, numbers, and motions against the English before sharing.</p>
          )}
          {secretary && (
            <div className="row">
              <select value={lang} onChange={(e) => setLang(e.target.value)} style={{ maxWidth: 260 }}>
                {d.languages.filter((l) => engine === "ai" || d.quick.includes(l.code)).map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
              </select>
              <button className="primary" disabled={!!busy || (engine === "quick" && !d.quick.includes(lang))}
                onClick={() => void run("translate", () => api.post(base + "/translations", { language: lang, engine }))}>
                {busy === "translate" ? "Translating…" : "Translate"}</button>
            </div>
          )}
          {d.translations.length === 0 ? <div className="empty">No translations yet.</div> : d.translations.map((t) => (
            <div key={t.language} className="request-row">
              <div className="row spread">
                <strong>{t.name}</strong>
                {t.stale && <span className="badge warn">Older draft</span>}
              </div>
              <div className="sub">{fmtDate(t.created_at)}{t.ai ? " · " + t.ai : ""}</div>
              <div className="row" style={{ marginTop: 6 }}>
                <a className="btn sm" href={base + "/translations/" + t.language + "/minutes.docx"}>Word file</a>
                {t.summary && <button onClick={() => setOpen(open === t.language ? "" : t.language)}>{open === t.language ? "Hide summary" : "Summary"}</button>}
                <button disabled={!!busy} onClick={() => void check(t.language)}>Check accessibility</button>
                {secretary && <button className="danger" onClick={() => { if (confirm("Remove the " + t.name + " translation?")) void run("del", () => api.del(base + "/translations/" + t.language)); }}>Remove</button>}
              </div>
              {open === t.language && <div className="prewrap" style={{ fontFamily: "inherit", fontSize: "0.95rem" }}>{t.summary}</div>}
            </div>
          ))}
        </div>
      </div>
      <div className="card stack">
        <div className="row spread">
          <h2 style={{ margin: 0 }}>Accessibility</h2>
          <button disabled={!!busy} onClick={() => void check("en")}>{busy === "check-en" ? "Checking…" : "Check the Word file"}</button>
        </div>
        <p className="sub" style={{ margin: 0 }}>Checks the Word file the way screen reader users experience it. Live Minutes sets the title and language for you; the rest comes from your template.</p>
        {report && (
          <>
            <div><strong>{report.passed} of {report.total}</strong> checks passed for the {nameOf(report.language)} file.</div>
            <table>
              <tbody>
                {report.checks.map((c) => (
                  <tr key={c.id}>
                    <td style={{ width: 90 }}><span className={"chip " + (c.status === "pass" ? "ok" : c.status === "fail" ? "bad" : "warn")}>{c.status === "pass" ? "Pass" : c.status === "fail" ? "Fix" : "Check"}</span></td>
                    <td><strong>{c.label}</strong><div className="sub">{c.detail}</div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}
