import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { Empty, ErrorBox, Meter, PageHeader, TopicChips } from "../components";
import { ScopeForm } from "../ScopeForm";
import type { DirectoryEntry } from "../types";

export function Directory() {
  const [open, setOpen] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["directory"], queryFn: () => api<{ researchers: DirectoryEntry[] }>("/v1/researchers") });
  const rows = (q.data?.researchers ?? []).filter((r) =>
    `${r.display_name} ${r.theme} ${r.published_topics.join(" ")}`.toLowerCase().includes(filter.toLowerCase()));
  return (
    <>
      <PageHeader title="Researcher directory">
        Verified researchers' public profiles, ranked by overlap of published topics. Requesting a comparison sends
        nothing until they approve.
      </PageHeader>
      <input className="search" placeholder="Search name, theme or topic" value={filter}
        onChange={(e) => setFilter(e.target.value)} aria-label="Search researchers" />
      <ErrorBox error={q.error} />
      {q.data && rows.length === 0 && <Empty>No researchers match.</Empty>}
      <ul className="list">
        {rows.map((r) => (
          <li key={r.researcher_id} className="card" data-testid={`directory-${r.researcher_id}`}>
            <div className="row between wrap">
              <div>
                <h2>{r.display_name}</h2>
                <p>{r.theme}</p>
              </div>
              <div className="stack-right">
                <span className="muted small">topic similarity</span>
                <Meter value={r.topic_match.score} />
              </div>
            </div>
            <TopicChips topics={r.published_topics} highlight={r.topic_match.matched_topics} />
            {r.public_scientific_inspiration && (
              <p className="muted small">Simulated account; research-theme inspiration: {r.public_scientific_inspiration.citation}</p>
            )}
            {open === r.researcher_id ? (
              <ScopeForm testId={`request-form-${r.researcher_id}`} allowedTopics={r.published_topics} maxDisclosure="summary"
                allowedVisibility={["requester_only", "both"]}
                onSubmit={(body) => api(`/v1/researchers/${r.researcher_id}/requests`, { method: "POST", body })}
                onDone={() => { setOpen(null); qc.invalidateQueries({ queryKey: ["outbox"] }); }} />
            ) : (
              <button onClick={() => setOpen(r.researcher_id)} data-testid={`request-${r.researcher_id}`}>
                Request comparison
              </button>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
