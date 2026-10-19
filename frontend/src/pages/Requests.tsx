import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, describe } from "../api";
import { Countdown, Empty, ErrorBox, label, PageHeader, Pill, TopicChips, useToast } from "../components";
import type { ComparisonRequest } from "../types";

/** Stable attributes for locating a specific request card (tests and assistive tooling). */
const cardAttrs = (r: ComparisonRequest) => ({
  "data-request-id": r.id,
  "data-topics": [...r.requested_scope.topics].sort().join(","),
  "data-classes": [...r.requested_scope.entity_classes].sort().join(","),
  "data-status": r.status,
});

function ScopeSummary({ r }: { r: ComparisonRequest }) {
  const s = r.requested_scope;
  return (
    <div className="scope-summary">
      <TopicChips topics={s.topics} />
      <span className="muted small">
        {s.entity_classes.join(" + ")} · {label(s.metric)} · {s.protocol === "psi_ca" ? "PSI-CA (private)" : "plaintext (dev only)"} ·
        disclosure {label(s.disclosure)} · result to {r.result_visibility === "both" ? "both parties" : "requester only"}
        {r.kind === "channel" ? " · via open channel" : " · one-to-one"}
      </span>
    </div>
  );
}

function useAction(onDone?: () => void) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: string }) => api<ComparisonRequest>(`/v1/requests/${id}/${action}`, { method: "POST" }),
    onSuccess: (r, { action }) => {
      toast(action === "run" ? "Comparison started: the agents are running PSI-CA." : `Request ${label(r.status).toLowerCase()}.`);
      qc.invalidateQueries({ queryKey: ["inbox"] });
      qc.invalidateQueries({ queryKey: ["outbox"] });
      onDone?.();
    },
    onError: (e) => toast(describe(e), "bad"),
  });
}

function InboxItem({ r }: { r: ComparisonRequest }) {
  const act = useAction();
  return (
    <li className="card" data-testid={`inbox-${r.requester.researcher_id}`} {...cardAttrs(r)}>
      <div className="row between wrap">
        <div className="row wrap">
          <strong>{r.requester.display_name}</strong>
          <Pill value={r.status} testId="request-status" />
          {r.status_reason && <span className="muted small">{label(r.status_reason)}</span>}
        </div>
        {r.status === "PENDING" && (
          <div className="row">
            <button className="primary" onClick={() => act.mutate({ id: r.id, action: "approve" })} data-testid="approve">Approve</button>
            <button className="danger" onClick={() => act.mutate({ id: r.id, action: "reject" })} data-testid="reject">Reject</button>
          </div>
        )}
      </div>
      <ScopeSummary r={r} />
      {r.status === "PENDING" && (
        <p className="hint">
          Approving lets both agents compute this similarity with PSI-CA. It does not share graph triples, observations or
          identifiers. Expires in <Countdown until={r.expires_at} />.
        </p>
      )}
    </li>
  );
}

function OutboxItem({ r }: { r: ComparisonRequest }) {
  const act = useAction();
  const blocked = r.status === "APPROVED" && r.execution_check && !r.execution_check.ok;
  return (
    <li className="card" data-testid={`outbox-${r.recipient.researcher_id}`} {...cardAttrs(r)}>
      <div className="row between wrap">
        <div className="row wrap">
          <strong>{r.recipient.display_name}</strong>
          <Pill value={r.status} testId="request-status" />
          {r.status_reason && <span className="muted small">{label(r.status_reason)}</span>}
        </div>
        <div className="row">
          {r.status === "APPROVED" && (
            <button className="primary" disabled={!!blocked} onClick={() => act.mutate({ id: r.id, action: "run" })} data-testid="run">
              Run comparison
            </button>
          )}
          {(r.status === "PENDING" || r.status === "APPROVED") && (
            <button className="ghost" onClick={() => act.mutate({ id: r.id, action: "cancel" })} data-testid="cancel">Cancel</button>
          )}
          {r.status === "COMPLETED" && <Link to="/matches" className="button">View match</Link>}
          {r.status === "RUNNING" && <span className="muted small">agents computing…</span>}
        </div>
      </div>
      <ScopeSummary r={r} />
      {blocked && <p className="hint" data-testid="blocked-reason">Cannot run now: {label(r.execution_check!.reason ?? "")}.</p>}
    </li>
  );
}

export function Requests() {
  const [tab, setTab] = useState<"inbox" | "outbox">("inbox");
  const inbox = useQuery({ queryKey: ["inbox"], queryFn: () => api<{ requests: ComparisonRequest[] }>("/v1/requests/inbox"), refetchInterval: 3000 });
  const outbox = useQuery({ queryKey: ["outbox"], queryFn: () => api<{ requests: ComparisonRequest[] }>("/v1/requests/outbox"), refetchInterval: 3000 });
  const pending = inbox.data?.requests.filter((r) => r.status === "PENDING").length ?? 0;
  const list = (tab === "inbox" ? inbox.data?.requests : outbox.data?.requests) ?? [];
  return (
    <>
      <PageHeader title="Requests">Every comparison needs the recipient's explicit approval. Decisions are final.</PageHeader>
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "inbox"} className={tab === "inbox" ? "active" : ""} onClick={() => setTab("inbox")} data-testid="tab-inbox">
          Inbox {pending > 0 && <span className="badge">{pending}</span>}
        </button>
        <button role="tab" aria-selected={tab === "outbox"} className={tab === "outbox" ? "active" : ""} onClick={() => setTab("outbox")} data-testid="tab-outbox">
          Sent
        </button>
      </div>
      <ErrorBox error={inbox.error || outbox.error} />
      {list.length === 0 && <Empty>{tab === "inbox" ? "No requests received." : "You have not sent any requests."}</Empty>}
      <ul className="list">
        {[...list].reverse().map((r) => (tab === "inbox" ? <InboxItem key={r.id} r={r} /> : <OutboxItem key={r.id} r={r} />))}
      </ul>
    </>
  );
}
