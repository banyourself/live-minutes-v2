import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, type Me, type OrgSummary } from "./api";

interface SessionValue {
  me: Me | null;
  loading: boolean;
  org: OrgSummary | null;
  setOrgId: (id: string) => void;
  refresh: () => Promise<Me | null>;
  logout: () => Promise<void>;
}

const Ctx = createContext<SessionValue | null>(null);
const ORG_KEY = "lm.org";

function readOrg() {
  try {
    return localStorage.getItem(ORG_KEY) || "";
  } catch {
    return "";
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [orgId, setOrgIdState] = useState(readOrg());

  const refresh = useCallback(async () => {
    try {
      const data = await api.get<Me>("/api/auth/me");
      setMe(data);
      return data;
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setMe(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setOrgId = useCallback((id: string) => {
    setOrgIdState(id);
    try {
      localStorage.setItem(ORG_KEY, id);
    } catch {
      return;
    }
  }, []);

  const logout = useCallback(async () => {
    await api.post("/api/auth/logout");
    setMe(null);
  }, []);

  const org = useMemo(() => {
    if (!me || me.orgs.length === 0) return null;
    return me.orgs.find((o) => o.id === orgId) || me.orgs[0];
  }, [me, orgId]);

  return <Ctx.Provider value={{ me, loading, org, setOrgId, refresh, logout }}>{children}</Ctx.Provider>;
}

export function useSession() {
  const v = useContext(Ctx);
  if (!v) throw new Error("SessionProvider missing");
  return v;
}
