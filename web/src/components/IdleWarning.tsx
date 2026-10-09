import { useEffect, useRef, useState } from "react";
import { api } from "../api";

const WARN_SECONDS = 600;

export default function IdleWarning({ idleHours }: { idleHours: number }) {
  const last = useRef(Date.now());
  const [left, setLeft] = useState<number | null>(null);

  useEffect(() => {
    const bump = () => { if (left === null) last.current = Date.now(); };
    const events = ["keydown", "pointerdown", "scroll"];
    events.forEach((e) => window.addEventListener(e, bump, { passive: true }));
    const t = window.setInterval(() => {
      const remaining = idleHours * 3600 - (Date.now() - last.current) / 1000;
      setLeft(remaining <= WARN_SECONDS ? Math.max(0, Math.round(remaining)) : null);
    }, 15000);
    return () => { events.forEach((e) => window.removeEventListener(e, bump)); window.clearInterval(t); };
  }, [idleHours, left]);

  if (left === null) return null;
  async function stay() {
    try { await api.get("/api/auth/me"); } catch { return; }
    last.current = Date.now();
    setLeft(null);
  }
  return (
    <div className="card stack modal" role="alertdialog" aria-labelledby="idle-title" aria-describedby="idle-text">
      <h2 id="idle-title" style={{ margin: 0 }}>Still there?</h2>
      <p id="idle-text" style={{ margin: 0 }}>
        {left > 0 ? "You will be signed out in about " + Math.max(1, Math.round(left / 60)) + " minutes because nothing has happened for a while. Save any edits you are working on." : "Your session may have ended. Stay signed in to check."}
      </p>
      <div className="row"><button className="primary" autoFocus onClick={() => void stay()}>Stay signed in</button></div>
    </div>
  );
}
