import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, describe } from "../api";
import { useAuth } from "../auth";
import { Pill, useToast } from "../components";
import { Banner } from "../Layout";
import type { Persona } from "../types";

type SystemHealth = {
  status: string;
  registry: { database: boolean };
  agents: Record<string, { status: string; graph_loaded: boolean }>;
};

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const personas = useQuery({ queryKey: ["personas"], queryFn: () => api<{ personas: Persona[] }>("/v1/public/personas") });
  const health = useQuery({ queryKey: ["system-health"], queryFn: () => api<SystemHealth>("/v1/system/health"), refetchInterval: 5000 });
  const mode = useQuery({ queryKey: ["health"], queryFn: () => api<{ test_mode: boolean }>("/v1/health") });
  const reset = useMutation({
    mutationFn: () => api("/v1/test/reset", { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries();
      toast("Demo reset: channels, requests, results and audit cleared; fixtures reseeded.");
    },
    onError: (e) => toast(describe(e), "bad"),
  });

  async function signIn(id: string) {
    setBusy(id);
    try {
      await login(id);
      navigate(id === "persona_e" ? "/audit" : "/discover");
    } catch (e) {
      toast(describe(e), "bad");
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <Banner />
      <main className="content narrow">
        <header className="page-header">
          <h1>FederatedKG demo</h1>
          <p className="muted">
            Choose a simulated account. This is a labelled demo sign-in standing in for institutional login; each browser
            tab keeps its own session.
          </p>
        </header>

        <ul className="persona-grid">
          {personas.data?.personas.map((p) => (
            <li key={p.researcher_id} className="card">
              <div className="row between">
                <h2>{p.display_name}</h2>
                <Pill value={p.verified_researcher ? "verified researcher" : "unverified"} tone={p.verified_researcher ? "ok" : "bad"} />
              </div>
              <p>{p.theme}</p>
              {p.public_scientific_inspiration && (
                <p className="muted small">
                  Research-theme inspiration: {p.public_scientific_inspiration.citation}{" "}
                  <a href={`https://doi.org/${p.public_scientific_inspiration.doi}`} target="_blank" rel="noreferrer">
                    doi:{p.public_scientific_inspiration.doi}
                  </a>
                </p>
              )}
              <p className="muted small">{p.disclaimer}</p>
              <button className="primary" disabled={busy !== null} onClick={() => signIn(p.researcher_id)}
                data-testid={`login-${p.researcher_id}`}>
                {busy === p.researcher_id ? "Signing in…" : `Sign in as ${p.display_name}`}
              </button>
            </li>
          ))}
        </ul>

        <section className="card">
          <h2>System</h2>
          {health.data && (
            <p className="row wrap">
              <Pill value={health.data.status === "ok" ? "all services healthy" : "degraded"} tone={health.data.status === "ok" ? "ok" : "bad"} testId="system-status" />
              <Pill value={health.data.registry.database ? "registry database" : "database down"} tone={health.data.registry.database ? "ok" : "bad"} />
              {Object.entries(health.data.agents).map(([id, a]) => (
                <Pill key={id} value={`agent ${id.replace("persona_", "")}`} tone={a.status === "ok" && a.graph_loaded ? "ok" : "bad"} />
              ))}
            </p>
          )}
          {mode.data?.test_mode && (
            <p className="row wrap">
              <button className="ghost" onClick={() => reset.mutate()} disabled={reset.isPending} data-testid="reset-demo">
                Reset demo
              </button>
              <span className="muted small">Test mode is on: demo clock and reset are available. Never enable outside a local demo.</span>
            </p>
          )}
        </section>
      </main>
    </>
  );
}
