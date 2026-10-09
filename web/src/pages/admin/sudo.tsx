import { createContext, useCallback, useContext, useState, type FormEvent, type ReactNode } from "react";
import { api, ApiError } from "../../api";
import { ErrorBox, errText } from "../../ui";

type Guard = <T>(fn: () => Promise<T>) => Promise<T>;

interface Pending {
  fn: () => Promise<unknown>;
  resolve: (v: unknown) => void;
  reject: (e: unknown) => void;
}

const Ctx = createContext<Guard>((fn) => fn());

export function useSudo() {
  return useContext(Ctx);
}

export function SudoProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const guard = useCallback(async <T,>(fn: () => Promise<T>): Promise<T> => {
    try {
      return await fn();
    } catch (e) {
      if (e instanceof ApiError && e.status === 403 && /confirm your password/i.test(e.message)) {
        return new Promise<T>((resolve, reject) => {
          setError("");
          setPassword("");
          setPending({ fn, resolve: resolve as (v: unknown) => void, reject });
        });
      }
      throw e;
    }
  }, []) as Guard;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!pending) return;
    setBusy(true);
    setError("");
    try {
      await api.post("/api/auth/sudo", { password });
    } catch (err) {
      setError(errText(err));
      setBusy(false);
      return;
    }
    const job = pending;
    setPending(null);
    setPassword("");
    setBusy(false);
    try {
      job.resolve(await job.fn());
    } catch (err) {
      job.reject(err);
    }
  }

  function cancel() {
    pending?.reject(new Error("cancelled"));
    setPending(null);
    setPassword("");
  }

  return (
    <Ctx.Provider value={guard}>
      {children}
      {pending && (
        <>
          <div className="cz-scrim" onClick={cancel} />
          <form className="card stack modal" role="dialog" aria-modal="true" aria-label="Confirm your password" onSubmit={submit}>
            <h2>Confirm it's you</h2>
            <p className="sub" style={{ margin: 0 }}>Enter your password to make administrator changes for the next 10 minutes.</p>
            <label>Password
              <input type="password" autoFocus required value={password} onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password" />
            </label>
            <ErrorBox error={error} />
            <div className="row">
              <button className="primary" disabled={busy || !password}>Confirm</button>
              <button type="button" onClick={cancel}>Cancel</button>
            </div>
          </form>
        </>
      )}
    </Ctx.Provider>
  );
}
