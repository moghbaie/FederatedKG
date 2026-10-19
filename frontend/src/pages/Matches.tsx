import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import { api, ApiError, describe } from "../api";
import { useAuth } from "../auth";
import { Band, Empty, label, PageHeader, Pill, TopicChips, useToast } from "../components";
import type { ComparisonRequest, MatchResult } from "../types";

const LEARNED: Record<string, string> = {
  own_set_size: "Your set size, as seen by the other agent",
  intersection: "The overlap count",
  identifiers: "Your identifiers shared",
};

function MatchCard({ r, result, hidden }: { r: ComparisonRequest; result?: MatchResult; hidden: boolean }) {
  const { me } = useAuth();
  const toast = useToast();
  const other = r.requester.researcher_id === me!.researcher_id ? r.recipient : r.requester;
  const contact = useMutation({
    mutationFn: () => api(`/v1/requests/${r.id}/contact`, { method: "POST" }),
    onSuccess: () => toast(`${other.display_name} was notified in the app. Nothing is sent outside FederatedKG.`),
    onError: (e) => toast(describe(e), "bad"),
  });
  return (
    <li className="card" data-testid={`match-${other.researcher_id}`}>
      <div className="row between wrap">
        <h2>{other.display_name}</h2>
        {result && (
          <span className="row wrap">
            <Pill value={result.protocol === "psi_ca" ? "PSI-CA private matching" : "plaintext dev matcher"}
              tone={result.protocol === "psi_ca" ? "ok" : "bad"} testId="protocol-badge" />
            <span className="muted small">{label(result.disclosure)}</span>
          </span>
        )}
      </div>
      <TopicChips topics={r.requested_scope.topics} />
      {hidden && <p className="muted">The requester chose to keep this result to themselves.</p>}
      {result && (
        <>
          <div className="grid two">
            {Object.entries(result.results).map(([cls, res]) => (
              <div key={cls} className="result-box" data-testid={`result-${cls}`}>
                <span className="muted small">{cls === "Protein" ? "Protein overlap" : "Interaction overlap"}</span>
                <Band value={res.band} testId={`band-${cls}`} />
                {res.set_size_buckets && (
                  <span className="muted small">set sizes: you {res.set_size_buckets.own}, them {res.set_size_buckets.counterpart}</span>
                )}
              </div>
            ))}
          </div>
          {result.matched_public_topics && (
            <p className="small">Matched public topics: <TopicChips topics={result.matched_public_topics} /></p>
          )}
          <details>
            <summary>What each side learned, provenance and signature</summary>
            <ul className="plain small">
              {Object.entries(result.disclosed_to_counterpart).map(([k, v]) => (
                <li key={k}>{LEARNED[k] ?? label(k)}: <strong>{v}</strong></li>
              ))}
              <li>Method: <span className="mono">{result.method}</span> ({result.algorithm_version})</li>
              <li>Computed by your agent from <span className="mono">{result.input_provenance.graph}</span> v{result.input_provenance.graph_version} ({result.input_provenance.normalization})</li>
              <li>Signed by {result.signature.signer} ({result.signature.algorithm}); verified at release {new Date(result.released_at).toLocaleString()}</li>
              <li>Policy version: {result.policy_version ?? "one-to-one default"}</li>
            </ul>
            <p className="hint">{result.caveat}</p>
          </details>
          <div className="row wrap">
            <button onClick={() => contact.mutate()} disabled={contact.isSuccess} data-testid="contact">
              {contact.isSuccess ? "Contact requested" : "Request contact"}
            </button>
            <button disabled title="Evidence sharing needs a separate agreement and is planned for a later release">
              Request evidence (later release)
            </button>
          </div>
        </>
      )}
    </li>
  );
}

export function Matches() {
  const inbox = useQuery({ queryKey: ["inbox"], queryFn: () => api<{ requests: ComparisonRequest[] }>("/v1/requests/inbox"), refetchInterval: 4000 });
  const outbox = useQuery({ queryKey: ["outbox"], queryFn: () => api<{ requests: ComparisonRequest[] }>("/v1/requests/outbox"), refetchInterval: 4000 });
  const completed = [...(outbox.data?.requests ?? []), ...(inbox.data?.requests ?? [])].filter((r) => r.status === "COMPLETED");
  const results = useQueries({
    queries: completed.map((r) => ({
      queryKey: ["result", r.id],
      queryFn: () => api<MatchResult>(`/v1/requests/${r.id}/result`),
      retry: (n: number, e: unknown) => !(e instanceof ApiError && e.status === 403) && n < 2,
    })),
  });
  return (
    <>
      <PageHeader title="Matches">
        Authorized similarity results from completed comparisons. Results are coarse bands; exact counts stay inside
        the computing agent.
      </PageHeader>
      {completed.length === 0 && <Empty>No completed comparisons yet.</Empty>}
      <ul className="list">
        {completed.map((r, i) => (
          <MatchCard key={r.id} r={r} result={results[i]?.data}
            hidden={results[i]?.error instanceof ApiError && (results[i].error as ApiError).status === 403} />
        ))}
      </ul>
    </>
  );
}
