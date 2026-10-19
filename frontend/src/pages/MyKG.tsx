import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import cytoscape from "cytoscape";
import { ownGraph } from "../api";
import { useAuth } from "../auth";
import { Empty, ErrorBox, label, PageHeader, Pill } from "../components";
import type { OwnerGraph } from "../types";

const LABEL_TONE: Record<string, string> = {
  supporting: "ok", contradictory_candidate: "bad", context_mismatch: "warn", insufficient_information: "neutral",
};

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function GraphView({ graph }: { graph: OwnerGraph }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const cy = cytoscape({
      container: ref.current,
      elements: [
        ...graph.nodes.map((n) => ({ data: { id: n.id, label: n.label, type: n.type, visibility: n.visibility } })),
        ...graph.edges.map((e, i) => ({ data: { id: `e${i}`, source: e.source, target: e.target, type: e.type } })),
      ],
      style: [
        { selector: "node", style: { label: "data(label)", "font-size": 9, color: cssVar("--fg"), "text-valign": "bottom",
          "text-margin-y": 3, width: 14, height: 14, "background-color": cssVar("--private") } },
        { selector: "node[visibility = 'public']", style: { "background-color": cssVar("--public"), shape: "diamond", width: 18, height: 18 } },
        { selector: "node[type = 'Method']", style: { shape: "round-rectangle" } },
        { selector: "node[type = 'Graph']", style: { shape: "star", width: 22, height: 22 } },
        { selector: "edge", style: { width: 1, "line-color": cssVar("--border"), "curve-style": "haystack" } },
        { selector: "edge[type = 'interactsWith']", style: { "line-color": cssVar("--muted"), width: 1.5 } },
      ],
      layout: { name: "cose", animate: false, randomize: false, nodeRepulsion: () => 6000 },
    });
    return () => cy.destroy();
  }, [graph]);
  return <div ref={ref} className="graph" data-testid="kg-graph" aria-label="Private knowledge graph visualization" />;
}

export function MyKG() {
  const { me } = useAuth();
  const q = useQuery({ queryKey: ["own-graph", me?.researcher_id], queryFn: () => ownGraph<OwnerGraph>(me!.researcher_id) });
  const g = q.data;
  const publicTopics = g?.nodes.filter((n) => n.visibility === "public").length ?? 0;
  return (
    <>
      <PageHeader title="My knowledge graph">
        Local-only view, served directly by your own agent. The registry and other researchers never receive it.
      </PageHeader>
      <ErrorBox error={q.error} />
      {g && (
        <>
          <div className="row wrap legend">
            <span><span className="dot public" /> public (published topic, {publicTopics})</span>
            <span><span className="dot private" /> private ({g.nodes.length - publicTopics})</span>
            <span className="muted small">{g.edges.length} relationships · all data synthetic</span>
          </div>
          <GraphView graph={g} />
          <div className="grid two">
            <section className="card">
              <h2>Synthetic hypotheses</h2>
              <ul className="plain">{g.hypotheses.map((h) => <li key={h.id}>{h.text}</li>)}</ul>
            </section>
            <section className="card">
              <h2>Local contradiction check</h2>
              <p className="muted small">Only on your own observations. A contradiction candidate is not proof that either observation is wrong.</p>
              {g.local_contradictions.length === 0 && <Empty>No comparable observation pairs.</Empty>}
              <table>
                <thead><tr><th>Observations</th><th>Classification</th></tr></thead>
                <tbody>
                  {g.local_contradictions.map((c) => (
                    <tr key={c.pair.join()} data-testid={`contradiction-${c.pair.join("-")}`}>
                      <td className="mono">{c.pair.join(" vs ")}</td>
                      <td><Pill value={c.label} tone={LABEL_TONE[c.label]} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
          <section className="card">
            <h2>Synthetic observations</h2>
            <div className="table-scroll">
              <table>
                <thead><tr><th>ID</th><th>Subject</th><th>Effect</th><th>Object</th><th>Context</th><th>Confidence</th></tr></thead>
                <tbody>
                  {g.observations.map((o) => (
                    <tr key={o.id}>
                      <td className="mono">{o.id}</td><td className="mono">{o.subject}</td><td>{label(o.effect)}</td>
                      <td className="mono">{o.object}</td>
                      <td>{o.context ? `${o.context.cell_type}, ${o.context.treatment}, ${o.context.timepoint}` : <span className="muted">missing</span>}</td>
                      <td>{o.confidence}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
