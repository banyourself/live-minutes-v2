export interface Prefs {
  scheme: string;
  customBase: string;
  accent: string;
  customAccent: string;
  heading: "typewriter" | "mono" | "serif";
  text: "s" | "m" | "l";
  density: "comfortable" | "compact";
  contrast: "on" | "off";
  motion: "on" | "off";
  grain: "on" | "off";
  punch: "on" | "off";
}

export const SCHEMES = [
  { key: "navy", label: "Navy", base: "#0c1524" },
  { key: "midnight", label: "Midnight", base: "#07090f" },
  { key: "slate", label: "Slate", base: "#181d26" },
  { key: "inkblue", label: "Ink Blue", base: "#0c1a38" },
  { key: "forest", label: "Forest", base: "#0b1a17" },
  { key: "manila", label: "Manila", base: "#efe8d6" },
  { key: "cream", label: "Cream", base: "#f7f3e8" }
];

export const ACCENTS = [
  { key: "blue", label: "Blue", color: "#6ea8ff" },
  { key: "teal", label: "Teal", color: "#45c9bd" },
  { key: "violet", label: "Violet", color: "#a68bfa" },
  { key: "coral", label: "Coral", color: "#ff8a70" },
  { key: "gold", label: "Gold", color: "#e9b949" },
  { key: "green", label: "Green", color: "#5fcf95" }
];

export const DEFAULTS: Prefs = {
  scheme: "navy", customBase: "#1a2a44", accent: "blue", customAccent: "#6ea8ff",
  heading: "typewriter", text: "m", density: "comfortable",
  contrast: "off", motion: "on", grain: "on", punch: "on"
};

const KEY = "lm.prefs";

export function loadPrefs(): Prefs {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || "{}");
    return { ...DEFAULTS, ...(saved && typeof saved === "object" ? saved : {}) };
  } catch {
    return { ...DEFAULTS };
  }
}

export function savePrefs(p: Prefs) {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    return;
  }
}

function rgb(hex: string): [number, number, number] | null {
  const m = /^#?([\da-f]{6})$/i.exec(String(hex).trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function hex(c: number[]) {
  return "#" + c.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("");
}

export function mix(a: string, b: string, t: number) {
  const x = rgb(a) || [0, 0, 0];
  const y = rgb(b) || [0, 0, 0];
  return hex(x.map((v, i) => v + (y[i] - v) * t));
}

export function luminance(color: string) {
  const c = rgb(color);
  if (!c) return 0;
  const [r, g, b] = c.map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function baseColor(p: Prefs) {
  if (p.scheme === "custom") return rgb(p.customBase) ? p.customBase : DEFAULTS.customBase;
  return (SCHEMES.find((s) => s.key === p.scheme) || SCHEMES[0]).base;
}

export function accentColor(p: Prefs) {
  if (p.accent === "custom") return rgb(p.customAccent) ? p.customAccent : DEFAULTS.customAccent;
  return (ACCENTS.find((a) => a.key === p.accent) || ACCENTS[0]).color;
}

function palette(base: string, accent: string, contrast: boolean): Record<string, string> {
  const W = "#ffffff";
  const K = "#000000";
  const dark = luminance(base) < 0.3;
  if (dark) {
    const text = contrast ? "#ffffff" : mix(W, base, 0.1);
    return {
      "--bg": base,
      "--sheet": mix(base, W, 0.04),
      "--card": mix(base, W, 0.075),
      "--card-2": mix(base, W, 0.11),
      "--field": mix(base, K, 0.2),
      "--field-focus": mix(base, W, 0.03),
      "--folder": mix(mix(base, W, 0.1), accent, 0.12),
      "--folder-deep": mix(mix(base, W, 0.14), accent, 0.18),
      "--folder-hover": mix(mix(base, W, 0.18), accent, 0.22),
      "--folder-edge": mix(mix(base, W, 0.22), accent, 0.3),
      "--side-top": mix(mix(base, W, 0.07), accent, 0.1),
      "--side-bottom": mix(mix(base, W, 0.04), accent, 0.07),
      "--text": text,
      "--text-strong": "#ffffff",
      "--text-soft": contrast ? mix(W, base, 0.08) : mix(W, base, 0.3),
      "--text-faint": contrast ? mix(W, base, 0.2) : mix(W, base, 0.34),
      "--placeholder": mix(W, base, 0.34),
      "--rule": contrast ? mix(base, W, 0.35) : mix(base, W, 0.15),
      "--rule-soft": mix(base, W, 0.1),
      "--rule-strong": contrast ? mix(base, W, 0.7) : mix(mix(base, W, 0.4), accent, 0.25),
      "--accent": accent,
      "--accent-text": accent,
      "--accent-deep": mix(accent, K, 0.3),
      "--accent-ink": luminance(accent) > 0.35 ? mix(base, K, 0.4) : "#ffffff",
      "--shadow-hard": mix(base, K, 0.55),
      "--stamp-red": "#ff8272",
      "--stamp-green": "#6ad8a0",
      "--stamp-blue": "#84b8ff",
      "--stamp-amber": "#f2b865",
      "--alert-bad": mix(base, "#ff8272", 0.12),
      "--alert-warn": mix(base, "#f2b865", 0.1),
      "--alert-ok": mix(base, "#6ad8a0", 0.1),
      "--alert-bad-text": "#ffc3ba",
      "--alert-warn-text": "#f7d6a6",
      "--alert-ok-text": "#b6ecd0",
      "--glow": accent,
      "--scheme": "dark"
    };
  }
  const ink = contrast ? "#000000" : mix(K, base, 0.12);
  const accentText = luminance(accent) > 0.18 ? mix(accent, K, 0.45) : accent;
  return {
    "--bg": base,
    "--sheet": mix(base, W, 0.5),
    "--card": mix(base, W, 0.7),
    "--card-2": mix(base, K, 0.03),
    "--field": mix(base, W, 0.3),
    "--field-focus": mix(base, W, 0.85),
    "--folder": mix(base, K, 0.1),
    "--folder-deep": mix(base, K, 0.17),
    "--folder-hover": mix(base, K, 0.22),
    "--folder-edge": mix(base, K, 0.3),
    "--side-top": mix(base, K, 0.08),
    "--side-bottom": mix(base, K, 0.12),
    "--text": ink,
    "--text-strong": mix(K, base, 0.05),
    "--text-soft": contrast ? mix(K, base, 0.15) : mix(K, base, 0.32),
    "--text-faint": contrast ? mix(K, base, 0.25) : mix(K, base, 0.4),
    "--placeholder": mix(K, base, 0.42),
    "--rule": contrast ? mix(base, K, 0.5) : mix(base, K, 0.22),
    "--rule-soft": mix(base, K, 0.12),
    "--rule-strong": ink,
    "--accent": accent,
    "--accent-text": accentText,
    "--accent-deep": mix(accent, K, 0.35),
    "--accent-ink": luminance(accent) > 0.35 ? ink : "#ffffff",
    "--shadow-hard": ink,
    "--stamp-red": "#9c2b21",
    "--stamp-green": "#3d6349",
    "--stamp-blue": "#2c4a63",
    "--stamp-amber": "#9a4e1b",
    "--alert-bad": "#efdcd2",
    "--alert-warn": "#eedfc4",
    "--alert-ok": "#dde5d3",
    "--alert-bad-text": "#6e1c15",
    "--alert-warn-text": "#5e300e",
    "--alert-ok-text": "#233c2b",
    "--glow": accent,
    "--scheme": "light"
  };
}

const HEADINGS = {
  typewriter: '"Special Elite", "Courier New", monospace',
  mono: '"IBM Plex Mono", ui-monospace, monospace',
  serif: '"Spectral", Georgia, serif'
};
const TEXT = { s: "93.75%", m: "100%", l: "112.5%" };

export function applyPrefs(p: Prefs) {
  const root = document.documentElement;
  const vars = palette(baseColor(p), accentColor(p), p.contrast === "on");
  Object.entries(vars).forEach(([k, v]) => root.style.setProperty(k, v));
  root.style.colorScheme = vars["--scheme"];
  root.style.setProperty("--f-stamp", HEADINGS[p.heading] || HEADINGS.typewriter);
  root.style.fontSize = TEXT[p.text] || "100%";
  root.dataset.density = p.density;
  root.dataset.contrast = p.contrast;
  root.dataset.motion = p.motion;
  root.dataset.grain = p.grain;
  root.dataset.punch = p.punch;
  root.dataset.light = vars["--scheme"] === "light" ? "on" : "off";
}
