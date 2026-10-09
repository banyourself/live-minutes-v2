import { useEffect, useMemo, useRef, useState } from "react";
import { fmtClock } from "../ui";

export interface PlayerLine { seq: number; t: number | null; speaker: string; text: string }

export default function Player({ src, type, captions, lines, downloads }: {
  src: string; type: string; captions: string; lines: PlayerLine[]; downloads: [string, string][];
}) {
  const media = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const [now, setNow] = useState(0);
  const [follow, setFollow] = useState(true);
  const [q, setQ] = useState("");
  const timed = useMemo(() => lines.filter((l) => l.t !== null), [lines]);
  const active = useMemo(() => {
    let hit = -1;
    for (let i = 0; i < timed.length; i++) {
      if ((timed[i].t as number) <= now + 0.25) hit = timed[i].seq; else break;
    }
    return hit;
  }, [timed, now]);
  const shown = q.trim() ? lines.filter((l) => (l.speaker + " " + l.text).toLowerCase().includes(q.trim().toLowerCase())) : lines;

  useEffect(() => {
    if (!follow || active < 0 || !list.current) return;
    const el = list.current.querySelector<HTMLElement>('[data-seq="' + active + '"]');
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [active, follow]);

  function seek(t: number | null) {
    if (t === null || !media.current) return;
    media.current.currentTime = t;
    void media.current.play().catch(() => undefined);
  }

  const video = !type.startsWith("audio/");
  const common = {
    ref: media, controls: true, preload: "metadata" as const, src,
    onTimeUpdate: () => setNow(media.current?.currentTime || 0)
  };
  return (
    <div className="player">
      <div className="player-media">
        {video ? (
          <video {...common} playsInline>
            <track kind="captions" src={captions} srcLang="en" label="Transcript" default />
          </video>
        ) : (
          <audio {...common} style={{ width: "100%" }}>
            <track kind="captions" src={captions} srcLang="en" label="Transcript" />
          </audio>
        )}
        <div className="row" style={{ marginTop: 8 }}>
          {downloads.map(([label, href]) => <a key={href} className="btn sm" href={href}>{label}</a>)}
        </div>
      </div>
      <div className="player-side">
        <div className="row spread">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the transcript" aria-label="Search the transcript" style={{ flex: 1 }} />
          <label className="row" style={{ textTransform: "none", letterSpacing: "normal" }}>
            <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Follow along
          </label>
        </div>
        <div className="player-lines" ref={list} role="list" aria-label="Transcript">
          {shown.length === 0 ? <div className="empty">{lines.length ? "No matches." : "No transcript yet."}</div> : shown.map((l) => (
            <button key={l.seq} type="button" role="listitem" data-seq={l.seq} className={"pline" + (l.seq === active ? " on" : "")}
              onClick={() => seek(l.t)} disabled={l.t === null} aria-current={l.seq === active ? "true" : undefined}>
              <span className="ts">{fmtClock(l.t)}</span>
              {l.speaker && <strong>{l.speaker}</strong>}
              <span>{l.text}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
