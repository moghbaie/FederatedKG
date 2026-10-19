import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import { Empty, ErrorBox, label, PageHeader, Pill } from "../components";
import type { AuditEvent } from "../types";

const TAB_TEXT = { all: "All", policy: "Channel & policy", comparison: "Requests & results", deny: "Denials" };

/** UUIDs are shortened for readability; readable ids (e.g. persona_a) are shown in full. */
const shortId = (id: string | null) => (id && /^[0-9a-f-]{36}$/.test(id) ? id.slice(0, 8) : id ?? "");

export function Audit() {
  const { me } = useAuth();
  const [filter, setFilter] = useState<"all" | "deny" | "policy" | "comparison">("all");
  const q = useQuery({ queryKey: ["audit"], queryFn: () => api<{ events: AuditEvent[] }>("/v1/audit"), refetchInterval: 5000 });
  const events = (q.data?.events ?? []).filter((e) =>
    filter === "all" ? true
      : filter === "deny" ? e.decision === "deny"
        : filter === "policy" ? e.action.startsWith("channel.")
          : e.action.startsWith("request.") || e.action.startsWith("result."));
  return (
    <>
      <PageHeader title="Audit trail">
        Your actions, plus events on your channels and on requests you are party to: policy versions, decisions,
        comparisons, releases, withholdings and revocations. No graph content is ever recorded.
      </PageHeader>
      {!me!.verified_researcher && (
        <p className="card warning" data-testid="unverified-notice">
          This account is not a verified researcher. It cannot discover research channels, request comparisons or see
          results. Denied attempts appear below.
        </p>
      )}
      <div className="tabs" role="tablist">
        {(["all", "policy", "comparison", "deny"] as const).map((f) => (
          <button key={f} role="tab" aria-selected={filter === f} className={filter === f ? "active" : ""} onClick={() => setFilter(f)}>
            {TAB_TEXT[f]}
          </button>
        ))}
      </div>
      <ErrorBox error={q.error} />
      {q.data && events.length === 0 && <Empty>No events.</Empty>}
      <ol className="timeline" data-testid="audit-timeline">
        {events.map((e) => (
          <li key={e.id} className={e.decision === "deny" ? "deny" : ""}>
            <span className="mono small">{new Date(e.timestamp).toLocaleString()}</span>
            <span><strong>{e.action}</strong> on {e.object_type} <span className="mono small" title={e.object_id ?? ""}>{shortId(e.object_id)}</span></span>
            <span className="row wrap">
              <Pill value={e.decision} />
              {e.reason_code && <span className="small">{label(e.reason_code)}</span>}
              {e.policy_version != null && <span className="muted small">policy v{e.policy_version}</span>}
              <span className="muted small">by {e.actor_id ?? "system"}</span>
            </span>
          </li>
        ))}
      </ol>
    </>
  );
}
