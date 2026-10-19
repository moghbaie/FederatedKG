import { useEffect, useState } from "react";

const BANNER = "Simulated researchers and synthetic knowledge graphs. No real researcher participation.";

type ComponentHealth = { status: string; graph_loaded?: boolean; database?: boolean };
type SystemHealth = {
  status: string;
  registry: ComponentHealth;
  agents: Record<string, ComponentHealth>;
};
type Persona = {
  researcher_id: string;
  display_name: string;
  theme: string;
  verified_researcher: boolean;
  public_scientific_inspiration: { name: string; doi: string; citation: string } | null;
  disclaimer: string;
};

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return <span className={`pill ${ok ? "ok" : "bad"}`}>{label}</span>;
}

export function App() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () =>
      getJson<SystemHealth>("/api/v1/system/health")
        .then((h) => {
          setHealth(h);
          setError(null);
        })
        .catch((e: Error) => setError(e.message));
    load();
    const timer = setInterval(load, 5000);
    getJson<{ personas: Persona[] }>("/api/v1/public/personas")
      .then((d) => setPersonas(d.personas))
      .catch((e: Error) => setError(e.message));
    return () => clearInterval(timer);
  }, []);

  return (
    <>
      <div className="banner" role="note">{BANNER}</div>
      <main>
        <h1>FederatedKG</h1>
        <p className="muted">Phase 1: system health and simulated demo accounts.</p>

        <section aria-labelledby="health-h">
          <h2 id="health-h">System health</h2>
          {error && <p className="error">{error}</p>}
          {health && (
            <table>
              <tbody>
                <tr>
                  <th>Overall</th>
                  <td data-testid="overall-status">
                    <StatusPill ok={health.status === "ok"} label={health.status} />
                  </td>
                </tr>
                <tr>
                  <th>Registry database</th>
                  <td>
                    <StatusPill ok={!!health.registry.database} label={health.registry.database ? "connected" : "down"} />
                  </td>
                </tr>
                {Object.entries(health.agents).map(([id, a]) => (
                  <tr key={id}>
                    <th>Agent {id}</th>
                    <td>
                      <StatusPill ok={a.status === "ok"} label={a.status} />{" "}
                      <StatusPill ok={!!a.graph_loaded} label={a.graph_loaded ? "private graph loaded" : "no graph"} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section aria-labelledby="personas-h">
          <h2 id="personas-h">Simulated accounts</h2>
          <ul className="personas">
            {personas.map((p) => (
              <li key={p.researcher_id}>
                <strong>{p.display_name}</strong>{" "}
                <StatusPill ok={p.verified_researcher} label={p.verified_researcher ? "verified researcher" : "unverified"} />
                <div>{p.theme}</div>
                {p.public_scientific_inspiration && (
                  <div className="muted small">
                    Public research-theme inspiration: {p.public_scientific_inspiration.citation}{" "}
                    <a href={`https://doi.org/${p.public_scientific_inspiration.doi}`} target="_blank" rel="noreferrer">
                      doi:{p.public_scientific_inspiration.doi}
                    </a>
                  </div>
                )}
                <div className="muted small">{p.disclaimer}</div>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </>
  );
}
