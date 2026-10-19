import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { Countdown, Empty, ErrorBox, label, Meter, PageHeader, TopicChips } from "../components";
import { ScopeForm } from "../ScopeForm";
import type { DiscoveryChannel } from "../types";

export function Discover() {
  const [open, setOpen] = useState<string | null>(null);
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["discover"],
    queryFn: () => api<{ channels: DiscoveryChannel[] }>("/v1/channels"),
    refetchInterval: 5000,
  });
  return (
    <>
      <PageHeader title="Discover open channels">
        Channels other researchers opened for verified researchers. You see published topics only — never graph
        content. The match score uses published topics alone.
      </PageHeader>
      <ErrorBox error={q.error} />
      {q.data && q.data.channels.length === 0 && <Empty>No open channels right now.</Empty>}
      <ul className="list">
        {q.data?.channels.map((c) => (
          <li key={c.id} className="card" data-testid={`channel-${c.owner.researcher_id}`}>
            <div className="row between wrap">
              <div>
                <h2>{c.owner.display_name}</h2>
                <p className="muted small">
                  Manual approval · max disclosure {label(c.max_disclosure)} · closes in <Countdown until={c.expires_at} />
                </p>
              </div>
              <div className="stack-right">
                <span className="muted small">topic match</span>
                <Meter value={c.topic_match.score} testId={`topic-match-${c.owner.researcher_id}`} />
              </div>
            </div>
            <TopicChips topics={c.topics} highlight={c.topic_match.matched_topics} />
            {open === c.id ? (
              <ScopeForm testId={`channel-form-${c.owner.researcher_id}`} allowedTopics={c.topics} maxDisclosure={c.max_disclosure}
                allowedVisibility={c.allowed_result_visibility}
                onSubmit={(body) => api(`/v1/channels/${c.id}/requests`, { method: "POST", body })}
                onDone={() => { setOpen(null); qc.invalidateQueries({ queryKey: ["outbox"] }); }} />
            ) : (
              <button onClick={() => setOpen(c.id)} data-testid={`channel-request-${c.owner.researcher_id}`}>
                Request detailed comparison
              </button>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
