import { useEffect, useRef } from "react";

interface TurnstileApi {
  render: (el: HTMLElement, opts: Record<string, unknown>) => string;
  reset: (id?: string) => void;
  remove: (id?: string) => void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let loader: Promise<void> | null = null;

function load() {
  if (window.turnstile) return Promise.resolve();
  if (!loader) {
    loader = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error("security check failed to load"));
      document.head.appendChild(s);
    });
  }
  return loader;
}

export default function Turnstile({ siteKey, action, onToken, resetKey = 0 }: { siteKey: string; action: string; onToken: (t: string) => void; resetKey?: number }) {
  const box = useRef<HTMLDivElement>(null);
  const widget = useRef<string>("");

  useEffect(() => {
    if (!siteKey) return;
    let alive = true;
    load().then(() => {
      if (!alive || !box.current || !window.turnstile) return;
      widget.current = window.turnstile.render(box.current, {
        sitekey: siteKey,
        action,
        theme: "auto",
        size: box.current.clientWidth < 300 ? "compact" : "normal",
        callback: (t: string) => onToken(t),
        "expired-callback": () => onToken(""),
        "error-callback": () => onToken("")
      });
    }).catch(() => onToken(""));
    return () => {
      alive = false;
      if (widget.current && window.turnstile) window.turnstile.remove(widget.current);
      widget.current = "";
    };
  }, [siteKey, action, onToken]);

  useEffect(() => {
    if (resetKey && widget.current && window.turnstile) {
      window.turnstile.reset(widget.current);
      onToken("");
    }
  }, [resetKey, onToken]);

  if (!siteKey) return null;
  return <div ref={box} className="turnstile" />;
}
