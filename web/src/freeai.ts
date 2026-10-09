import { useEffect, useState } from "react";

export interface FreeRun {
  id: string;
  task: string;
  label: string;
  model: string;
  status: "queued" | "running" | "done" | "error";
  phase: string;
  progress: number;
  eta_seconds: number;
  position: number;
  output_tokens: number;
  updated_at: number;
  error: string;
}

const POLL_MS = 10000;
const runs = new Map<string, FreeRun>();
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((fn) => fn());
}

export function useFreeRuns(): FreeRun[] {
  const [, setTick] = useState(0);
  useEffect(() => {
    const fn = () => setTick((n) => n + 1);
    listeners.add(fn);
    return () => { listeners.delete(fn); };
  }, []);
  return [...runs.values()];
}

export function dismissRun(id: string) {
  runs.delete(id);
  emit();
}

async function fetchRun(id: string): Promise<FreeRun | null> {
  const res = await fetch("/api/free-ai/runs/" + encodeURIComponent(id), { credentials: "include", headers: { "X-Live-Minutes": "1" } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("could not check the free AI");
  return res.json() as Promise<FreeRun>;
}

export async function cancelRun(id: string) {
  await fetch("/api/free-ai/runs/" + encodeURIComponent(id), { method: "DELETE", credentials: "include", headers: { "X-Live-Minutes": "1" } });
  const run = runs.get(id);
  if (run) runs.set(id, { ...run, status: "error", error: "Cancelled." });
  emit();
}

export async function waitForRun(first: FreeRun): Promise<FreeRun> {
  runs.set(first.id, first);
  emit();
  let misses = 0;
  for (;;) {
    await new Promise((r) => setTimeout(r, POLL_MS));
    const current = runs.get(first.id);
    if (current && current.status === "error" && current.error === "Cancelled.") throw new Error("Cancelled.");
    let next: FreeRun | null = null;
    try {
      next = await fetchRun(first.id);
      misses = 0;
    } catch {
      misses += 1;
      if (misses > 30) throw new Error("lost touch with the free AI; try again");
      continue;
    }
    if (!next) {
      runs.delete(first.id);
      emit();
      throw new Error("the free AI request was cancelled");
    }
    runs.set(next.id, next);
    emit();
    if (next.status === "done") {
      setTimeout(() => dismissRun(next!.id), 4000);
      return next;
    }
    if (next.status === "error") {
      setTimeout(() => dismissRun(next!.id), 15000);
      return next;
    }
  }
}

export function minutesLeft(seconds: number): string {
  if (seconds <= 45) return "less than a minute left";
  const m = Math.round(seconds / 60);
  return "about " + m + (m === 1 ? " minute" : " minutes") + " left";
}

export function useSmoothProgress(run: Pick<FreeRun, "progress" | "eta_seconds" | "updated_at" | "status"> | null): number {
  const [shown, setShown] = useState(run?.progress || 0);
  useEffect(() => {
    if (!run) return;
    if (run.status === "done") { setShown(1); return; }
    const base = run.progress || 0;
    const seenAt = Date.now();
    const eta = Math.max(30, run.eta_seconds || 30);
    setShown((s) => Math.max(s, base));
    const timer = window.setInterval(() => {
      const elapsed = (Date.now() - seenAt) / 1000;
      const expected = base + (1 - base) * Math.min(1, elapsed / eta);
      const ceiling = Math.min(0.97, base + 0.12);
      setShown((s) => {
        const target = Math.min(ceiling, Math.max(expected, s + 0.0008));
        return s + (target - s) * 0.25;
      });
    }, 400);
    return () => window.clearInterval(timer);
  }, [run?.progress, run?.eta_seconds, run?.updated_at, run?.status]);
  return run ? shown : 0;
}
