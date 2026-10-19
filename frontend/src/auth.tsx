import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, hasToken, setToken, setUnauthorizedHandler } from "./api";
import type { Researcher } from "./types";

type Auth = {
  me: Researcher | null;
  loading: boolean;
  login: (researcherId: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Researcher | null>(null);
  const [loading, setLoading] = useState(hasToken());
  const queryClient = useQueryClient();

  const logout = useCallback(() => {
    setToken(null);
    setMe(null);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    if (!hasToken()) return;
    api<Researcher>("/v1/me")
      .then(setMe)
      .catch(logout)
      .finally(() => setLoading(false));
  }, [logout]);

  const login = useCallback(
    async (researcherId: string) => {
      queryClient.clear();
      const r = await api<{ access_token: string; researcher: Researcher }>("/v1/auth/demo-login", {
        method: "POST",
        body: { researcher_id: researcherId },
      });
      setToken(r.access_token);
      setMe(r.researcher);
    },
    [queryClient],
  );

  return <AuthContext.Provider value={{ me, loading, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
