import { useEffect, useRef, useState } from "react";
import { ACCENTS, accentColor, applyPrefs, baseColor, DEFAULTS, loadPrefs, savePrefs, SCHEMES, type Prefs } from "../prefs";

const HEADING_FONTS: Record<Prefs["heading"], string> = {
  typewriter: '"Special Elite", monospace',
  mono: '"IBM Plex Mono", monospace',
  serif: '"Spectral", serif'
};

function Pick<T extends string>({ value, current, label, onPick, font }: {
  value: T; current: T; label: string; onPick: (v: T) => void; font?: string;
}) {
  return (
    <button type="button" className={"cz__pick" + (value === current ? " on" : "")} aria-pressed={value === current}
      style={font ? { fontFamily: font, textTransform: "none", letterSpacing: "0.02em", fontSize: "0.9rem" } : undefined}
      onClick={() => onPick(value)}>
      {label}
    </button>
  );
}

function Toggle({ on, label, onToggle }: { on: boolean; label: string; onToggle: () => void }) {
  return (
    <button type="button" className="cz__t" role="switch" aria-checked={on} onClick={onToggle}>
      <span className="cz__box" aria-hidden="true" />
      {label}
    </button>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="cz__row">
      <span className="cz__lbl">{label}</span>
      <div className="cz__ctl">{children}</div>
    </div>
  );
}

export default function Customize({ floating = false, show, onClose }: { floating?: boolean; show?: boolean; onClose?: () => void }) {
  const controlled = show !== undefined;
  const [own, setOwn] = useState(false);
  const open = controlled ? !!show : own;
  const setOpen = (v: boolean) => { if (controlled) { if (!v) onClose?.(); } else setOwn(v); };
  const [p, setP] = useState<Prefs>(loadPrefs);
  const trigger = useRef<HTMLButtonElement>(null);
  const body = useRef<HTMLDivElement>(null);

  function update(patch: Partial<Prefs>) {
    const next = { ...p, ...patch };
    setP(next);
    savePrefs(next);
    applyPrefs(next);
  }

  function close() {
    setOpen(false);
    trigger.current?.focus();
  }

  useEffect(() => {
    if (!open) return;
    body.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const on = (k: "contrast" | "motion" | "grain" | "punch") => p[k] === "on";
  const flip = (k: "contrast" | "motion" | "grain" | "punch") => update({ [k]: on(k) ? "off" : "on" } as Partial<Prefs>);

  return (
    <>
      {!controlled && (
        <button ref={trigger} type="button" className={floating ? "cz-float" : "cz-btn"} aria-expanded={open}
          aria-controls="cz-panel" onClick={() => setOpen(true)}>
          Customize
        </button>
      )}
      {open && (
        <>
          <div className="cz-scrim" onClick={close} />
          <section className="cz" id="cz-panel" role="dialog" aria-modal="true" aria-label="Customize">
            <div className="cz__bar">
              <span className="cz__title">Customize</span>
              <button type="button" onClick={close}>Close</button>
            </div>
            <div className="cz__body" ref={body} tabIndex={-1}>
              <Row label="Background">
                {SCHEMES.map((s) => (
                  <span key={s.key} className="cz__swlbl">
                    <button type="button" className={"cz__sw" + (p.scheme === s.key ? " on" : "")} aria-label={s.label}
                      aria-pressed={p.scheme === s.key} title={s.label} style={{ background: s.base }}
                      onClick={() => update({ scheme: s.key })} />
                    {s.label}
                  </span>
                ))}
                <label className={"cz__custom" + (p.scheme === "custom" ? " on" : "")}>
                  <input type="color" value={p.scheme === "custom" ? baseColor(p) : p.customBase}
                    onChange={(e) => update({ scheme: "custom", customBase: e.target.value })} />
                  Custom
                </label>
              </Row>

              <Row label="Accent">
                {ACCENTS.map((a) => (
                  <span key={a.key} className="cz__swlbl">
                    <button type="button" className={"cz__sw" + (p.accent === a.key ? " on" : "")} aria-label={a.label}
                      aria-pressed={p.accent === a.key} title={a.label} style={{ background: a.color }}
                      onClick={() => update({ accent: a.key })} />
                    {a.label}
                  </span>
                ))}
                <label className={"cz__custom" + (p.accent === "custom" ? " on" : "")}>
                  <input type="color" value={p.accent === "custom" ? accentColor(p) : p.customAccent}
                    onChange={(e) => update({ accent: "custom", customAccent: e.target.value })} />
                  Custom
                </label>
              </Row>

              <Row label="Headings">
                <Pick value="typewriter" current={p.heading} label="Typewriter" font={HEADING_FONTS.typewriter} onPick={(v) => update({ heading: v })} />
                <Pick value="mono" current={p.heading} label="Mono" font={HEADING_FONTS.mono} onPick={(v) => update({ heading: v })} />
                <Pick value="serif" current={p.heading} label="Serif" font={HEADING_FONTS.serif} onPick={(v) => update({ heading: v })} />
              </Row>

              <Row label="Text size">
                <Pick value="s" current={p.text} label="Small" onPick={(v) => update({ text: v })} />
                <Pick value="m" current={p.text} label="Normal" onPick={(v) => update({ text: v })} />
                <Pick value="l" current={p.text} label="Large" onPick={(v) => update({ text: v })} />
              </Row>

              <Row label="Density">
                <Pick value="comfortable" current={p.density} label="Comfortable" onPick={(v) => update({ density: v })} />
                <Pick value="compact" current={p.density} label="Compact" onPick={(v) => update({ density: v })} />
              </Row>

              <Row label="Display">
                <Toggle on={on("contrast")} label="High contrast" onToggle={() => flip("contrast")} />
                <Toggle on={on("motion")} label="Animations" onToggle={() => flip("motion")} />
                <Toggle on={on("grain")} label="Paper grain" onToggle={() => flip("grain")} />
                <Toggle on={on("punch")} label="Punch holes" onToggle={() => flip("punch")} />
              </Row>

              <div className="cz__foot">
                <span className="sub">Saved in this browser.</span>
                <button type="button" onClick={() => update({ ...DEFAULTS })}>Reset to defaults</button>
              </div>
            </div>
          </section>
        </>
      )}
    </>
  );
}
