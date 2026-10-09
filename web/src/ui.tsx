import { useCallback, useEffect, useState } from "react";

export function ErrorBox({ error }: { error: string }) {
  if (!error) return null;
  return <div className="alert bad" role="alert">{error}</div>;
}

export function errText(e: unknown) {
  return e instanceof Error ? e.message : String(e);
}

export function fmtDate(ts: number | null | undefined) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function fmtClock(t: number | null) {
  if (t === null || t === undefined) return "--:--";
  const s = Math.floor(t);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return (h ? h + ":" : "") + String(m).padStart(h ? 2 : 1, "0") + ":" + String(sec).padStart(2, "0");
}

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fn());
      setError("");
    } catch (e) {
      setError(errText(e));
    } finally {
      setLoading(false);
    }
  }, deps);
  useEffect(() => {
    void load();
  }, [load]);
  return { data, error, loading, reload: load, setData };
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, [string, string]> = {
    scheduled: ["Scheduled", "warn"],
    open: ["In session", "live"],
    ended: ["Draft", ""],
    approved: ["Approved", "ok"],
    error: ["Failed", ""]
  };
  const [label, cls] = map[status] || [status, ""];
  return <span className={"stamp sm " + cls}>{label}</span>;
}

export function fileNo(ts: number, id: string) {
  const d = new Date(ts * 1000);
  const two = (n: number) => String(n).padStart(2, "0");
  return two(d.getMonth() + 1) + "." + two(d.getDate()) + "." + String(d.getFullYear()).slice(2) + "-" + id.slice(0, 4).toUpperCase();
}
